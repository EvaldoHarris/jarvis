import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.speech_announcements import SpeechAnnouncements, MESSAGE


def method(name, **extra):
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
    node = next(node for node in cls.body if getattr(node, "name", "") == name)
    namespace = dict(asyncio=asyncio, time=time, **extra)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace[name]


class SpeechAnnouncementsTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_finishes_before_agent_then_pending_messages_take_priority(self):
        queue = SpeechAnnouncements()
        send = AsyncMock()
        ready = Mock(return_value=True)
        queue.enqueue("Discord: primeira mensagem", MESSAGE)
        await queue.dispatch(ready, send)
        queue.enqueue("Codex terminou")
        queue.enqueue("Claude terminou")
        queue.enqueue("Discord: segunda mensagem", MESSAGE)
        self.assertFalse(await queue.dispatch(ready, send))
        send.assert_awaited_once_with("Discord: primeira mensagem")

        queue.turn_finished()  # generation ended, but speakers still playing
        ready.return_value = False
        self.assertFalse(await queue.dispatch(ready, send))
        ready.return_value = True  # audio drained
        await queue.dispatch(ready, send)
        self.assertEqual(send.await_args.args, ("Discord: segunda mensagem",))
        queue.turn_finished()
        await queue.dispatch(ready, send)
        self.assertEqual(send.await_args.args, ("Codex terminou",))
        queue.turn_finished()
        await queue.dispatch(ready, send)
        self.assertEqual(send.await_args.args, ("Claude terminou",))

    async def test_no_second_send_before_first_audio_or_during_network_send(self):
        queue = SpeechAnnouncements()
        entered, release = asyncio.Event(), asyncio.Event()

        async def send(text):
            entered.set()
            await release.wait()

        queue.enqueue("mensagem", MESSAGE)
        first = asyncio.create_task(queue.dispatch(lambda: True, send))
        await entered.wait()
        queue.enqueue("agente terminou")
        self.assertFalse(await queue.dispatch(lambda: True, send))
        release.set()
        await first
        self.assertFalse(await queue.dispatch(lambda: True, send))

    async def test_failure_retains_notice_and_message_priority_on_retry(self):
        queue = SpeechAnnouncements()
        queue.enqueue("agente terminou")
        with self.assertRaises(ConnectionError):
            await queue.dispatch(lambda: True, AsyncMock(side_effect=ConnectionError()))
        queue.enqueue("mensagem", MESSAGE)
        send = AsyncMock()
        await queue.dispatch(lambda: True, send)
        send.assert_awaited_once_with("mensagem")
        queue.turn_finished()
        await queue.dispatch(lambda: True, send)
        self.assertEqual(send.await_args.args, ("agente terminou",))

    async def test_real_plugin_channel_only_enqueues(self):
        queue = SpeechAnnouncements()
        session = SimpleNamespace(send_client_content=AsyncMock())
        host = SimpleNamespace(_loop=SimpleNamespace(call_soon_threadsafe=lambda fn, *args: fn(*args)),
                               session=session, _speech_announcements=queue)
        method("plugin_say")(host, "Claude terminou")
        session.send_client_content.assert_not_called()
        send = AsyncMock()
        await queue.dispatch(lambda: True, send)
        send.assert_awaited_once_with("Claude terminou")

    async def test_real_ready_gate_waits_for_generation_audio_tail_and_user(self):
        host = SimpleNamespace(session=object(), _awake=True, _phone_active=False,
                               _speech_turn_pending=False, _is_speaking=False,
                               _rx_deadline=None,
                               _tail_active=lambda: False, audio_in_queue=asyncio.Queue(),
                               _last_user_speech=time.monotonic() - 10)
        ready = method("_announcement_ready")
        self.assertTrue(ready(host))
        host._rx_deadline = time.monotonic() + 30
        self.assertFalse(ready(host))
        host._rx_deadline = None
        for field in ("_speech_turn_pending", "_is_speaking", "_phone_active"):
            setattr(host, field, True)
            self.assertFalse(ready(host))
            setattr(host, field, False)
        host.audio_in_queue.put_nowait(b"audio")
        self.assertFalse(ready(host))
        host.audio_in_queue.get_nowait()
        host._tail_active = lambda: True
        self.assertFalse(ready(host))
        host._tail_active = lambda: False
        host._last_user_speech = time.monotonic()
        self.assertFalse(ready(host))

    async def test_real_notification_watcher_queues_message_while_speaking(self):
        from core import alerts
        queue = SpeechAnnouncements()
        queue.enqueue("Codex terminou")
        watcher = SimpleNamespace(available=True, error="")

        async def poll():
            watcher.available = False
            return [{"app": "Discord", "title": "Ana", "body": "Olá"}]

        watcher.poll = poll
        host = SimpleNamespace(_discord_watcher=watcher, session=object(), _is_speaking=True,
                               _speech_announcements=queue)
        with patch.object(alerts, "load", return_value={}), \
                patch.object(alerts, "classify", return_value=(True, "message")), \
                patch.object(alerts, "should_speak", return_value=True), \
                patch.object(alerts, "remember"), \
                patch.object(alerts, "summarize", return_value="Discord Ana: Olá"), \
                patch.object(asyncio, "sleep", new=AsyncMock()):
            await method("_run_discord_watch", load_memory=lambda: {})(host)
        send = AsyncMock()
        await queue.dispatch(lambda: True, send)
        self.assertIn("Discord Ana: Olá", send.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
