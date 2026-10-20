import ast
import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from google.genai import types
from core.turn_watchdog import MicrophoneTurn


def load_sender():
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_realtime")
    namespace = dict(asyncio=asyncio, time=time, types=types,
                     MicrophoneTurn=MicrophoneTurn, SEND_SAMPLE_RATE=16000, voice_health=Mock())
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_send_realtime"]


class RealtimeAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_paused_live_microphone_sends_end_marker_once(self):
        session = SimpleNamespace(send_realtime_input=AsyncMock())
        host = SimpleNamespace(out_queue=asyncio.Queue(), session=session, _engine=None,
                               _last_answer_at=0., _arm_stall=Mock())
        host.out_queue.put_nowait({"data": bytes(2048), "mime_type": "audio/pcm"})
        task = asyncio.create_task(load_sender()(host))
        try:
            await asyncio.sleep(1.1)
            self.assertEqual(session.send_realtime_input.call_count, 2)
            self.assertEqual(session.send_realtime_input.call_args.kwargs, {"audio_stream_end": True})
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_network_failure_reaches_session_recovery(self):
        session = SimpleNamespace(send_realtime_input=AsyncMock(side_effect=ConnectionError("offline")))
        host = SimpleNamespace(out_queue=asyncio.Queue(), session=session, _engine=None,
                               _last_answer_at=0., _arm_stall=Mock())
        host.out_queue.put_nowait({"data": bytes(2048)})
        with self.assertRaises(ConnectionError):
            await load_sender()(host)


if __name__ == "__main__":
    unittest.main()
