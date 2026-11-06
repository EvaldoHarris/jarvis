import asyncio
import ast
import re
import time
import traceback
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.speech_routing import SpeechRouter, probe_presence


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.probe = Mock(return_value={'present': True})
        self.log = Mock()
        self.config = {'enabled': True, 'owner': 'owner', 'device_id': ''}
        self.router = SpeechRouter(self.log, self.probe, lambda: self.config)
        self.bridge = Mock()
        self.bridge.list_devices.return_value = [{'id': 'my-phone'}]
        self.bridge.begin_speech = AsyncMock(return_value=True)
        self.bridge.deliver_audio = AsyncMock(return_value=True)
        self.bridge.deliver_reply = AsyncMock(return_value=True)
        self.bridge.cancel_speech = AsyncMock(return_value=True)
        self.bridge.deliver_presence_frame = AsyncMock(return_value=True)

    async def test_camera_precedes_pcm_and_is_checked_again_for_next_utterance(self):
        self.assertTrue(await self.router.audio(b'one', self.bridge))
        self.assertTrue(await self.router.audio(b'two', self.bridge))
        self.probe.assert_called_once_with('owner')
        self.bridge.deliver_audio.assert_not_called()
        await self.router.finish('reply')
        self.probe.return_value = {'present': False}
        self.assertFalse(await self.router.audio(b'next', self.bridge))
        self.assertEqual(self.probe.call_count, 2)
        self.bridge.deliver_audio.assert_awaited_once()

    async def test_absence_phone_only_preserves_pcm_and_finishes_stream(self):
        self.probe.return_value = {'present': False}
        pcm = b'\x01\x00' * 200
        self.assertFalse(await self.router.audio(pcm, self.bridge))
        route = self.router.route
        self.bridge.deliver_audio.assert_awaited_once_with('my-phone', route['request'], pcm)
        await self.router.finish('the reply')
        self.bridge.deliver_reply.assert_awaited_once_with('my-phone', route['request'], '', audio_streamed=True)

    async def test_camera_failure_offline_ambiguous_or_wrong_phone_never_use_pc(self):
        self.probe.side_effect = RuntimeError('camera unavailable')
        for devices in ([], [{'id': 'a'}, {'id': 'b'}]):
            self.bridge.list_devices.return_value = devices
            self.assertFalse(await self.router.audio(b'pcm', self.bridge))
            self.assertEqual(self.router.route['destination'], 'silent')
            await self.router.finish()
        self.config['device_id'] = 'missing-phone'
        self.bridge.list_devices.return_value = [{'id': 'another-phone'}]
        self.assertFalse(await self.router.audio(b'pcm', self.bridge))
        self.bridge.begin_speech.assert_not_called()

    async def test_no_phone_playback_without_start_ack(self):
        self.probe.return_value = {'present': False}
        self.bridge.begin_speech.return_value = False
        self.assertFalse(await self.router.audio(b'pcm', self.bridge))
        self.bridge.deliver_audio.assert_not_called()

    async def test_disconnect_does_not_replay_on_pc_or_restart_stream(self):
        self.probe.return_value = {'present': False}
        self.bridge.deliver_audio.return_value = False
        self.assertFalse(await self.router.audio(b'one', self.bridge))
        self.assertFalse(await self.router.audio(b'two', self.bridge))
        self.bridge.deliver_audio.assert_awaited_once()
        self.bridge.begin_speech.assert_awaited_once()

    async def test_text_only_turn_uses_phone_voice(self):
        self.probe.return_value = {'present': False}
        await self.router.begin(self.bridge)
        request = self.router.route['request']
        await self.router.finish('text answer')
        self.bridge.deliver_reply.assert_awaited_once_with('my-phone', request, 'text answer', audio_streamed=False)

    async def test_interruption_during_presence_check_never_delivers_pcm(self):
        self.probe.side_effect = lambda owner: (self.router.interrupt() or {'present': False})
        self.assertFalse(await self.router.audio(b'old pcm', self.bridge))
        self.bridge.deliver_audio.assert_not_called()
        request = self.router.route['request']
        await self.router.cancel()
        self.bridge.cancel_speech.assert_awaited_once_with('my-phone', request)

    async def test_disabled_feature_preserves_legacy_phone_request(self):
        self.config['enabled'] = False
        request = {'reply_device': 'my-phone', 'reply_id': 'original-request'}
        self.assertTrue(await self.router.audio(b'pcm', self.bridge, request))
        self.probe.assert_not_called()
        self.assertTrue(self.router.legacy)
        self.assertTrue(request['audio_streamed'])

    async def test_unknown_visible_person_sends_image_notice_and_rate_limits(self):
        self.config['unknown_alerts'] = True
        self.probe.return_value = {'present': False, 'person_visible': True, 'image': b'jpeg'}
        with patch('core.presence_preview.preview', new=AsyncMock()):
            await self.router.begin(self.bridge)
            call = self.bridge.deliver_presence_frame.call_args
            self.assertEqual(call.args[0], 'my-phone')
            self.assertEqual(call.args[2], b'jpeg')
            self.assertEqual(call.kwargs['notice'], 'Evaldo, tem uma pessoa não identificada mexendo no seu computador')
            await self.router.finish()
            await self.router.begin(self.bridge)
            self.bridge.deliver_presence_frame.assert_awaited_once()
            await self.router.close()

    async def test_empty_camera_or_error_never_claims_unknown_person(self):
        self.config['unknown_alerts'] = True
        for observation in ({'present': False, 'person_visible': False}, {'present': False, 'reason': 'camera_error'}):
            self.probe.return_value = observation
            await self.router.begin(self.bridge)
            await self.router.finish()
        self.bridge.deliver_presence_frame.assert_not_called()


class PresenceTests(unittest.TestCase):
    def test_another_known_person_does_not_count_as_owner(self):
        with patch('core.person_identity.load_profiles', return_value={'owner': {'face': [1, 0]}, 'other': {'face': [0, 1]}}), \
             patch('core.person_identity.face_observation', return_value={'vectors': [[0, 1]], 'image': b'jpeg', 'face_count': 1}), \
             patch('memory.config_manager.load_api_keys', return_value={}):
            self.assertFalse(probe_presence('owner')['present'])

    def test_unknown_profile_is_not_silently_replaced(self):
        with patch('core.person_identity.load_profiles', return_value={'other': {'face': [1, 0]}}), \
             patch('core.person_identity.face_observation') as camera, \
             patch('memory.config_manager.load_api_keys', return_value={}):
            self.assertFalse(probe_presence('owner')['present'])
            camera.assert_not_called()

    def test_owner_full_name_duplicate_is_not_an_unknown_person(self):
        with patch('core.person_identity.load_profiles', return_value={'Evaldo': {'face': [1, 0]},
                   'Evaldo Full Name': {'face': [.99, .01]}, 'Other': {'face': [0, 1]}}), \
             patch('core.person_identity.face_observation', return_value={'vectors': [[.99, .02]], 'image': b'jpeg', 'face_count': 1}), \
             patch('memory.config_manager.load_api_keys', return_value={}):
            self.assertTrue(probe_presence('Evaldo')['present'])

    def test_owner_can_be_present_alongside_another_face(self):
        with patch('core.person_identity.load_profiles', return_value={'owner': {'face': [1, 0]}, 'other': {'face': [0, 1]}}), \
             patch('core.person_identity.face_observation', return_value={'vectors': [[0, 1], [1, 0]], 'image': b'jpeg', 'face_count': 2}), \
             patch('memory.config_manager.load_api_keys', return_value={}):
            self.assertTrue(probe_presence('owner')['present'])

    def test_no_face_is_distinct_from_unrecognized_face(self):
        with patch('core.person_identity.load_profiles', return_value={'owner': {'face': [1, 0]}}), \
             patch('core.person_identity.face_observation', return_value={'vectors': [], 'image': b'empty', 'face_count': 0}), \
             patch('memory.config_manager.load_api_keys', return_value={}):
            result = probe_presence('owner')
            self.assertFalse(result['person_visible'])
            self.assertEqual(result['reason'], 'no_person_visible')
            self.assertEqual(result['image'], b'')


class ReceiveRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def run_turn(self, present):
        # Exercise the real receive loop, including PC queueing and phone reply
        # completion, without importing/starting the desktop UI or an AI session.
        path = Path(__file__).parents[1] / 'main.py'
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == '_receive_audio')
        namespace = dict(asyncio=asyncio, time=time, traceback=traceback, datetime=datetime,
                         voice_health=Mock(), has_answer_progress=lambda r: True,
                         _CTRL_RE=re.compile('NEVER_MATCH'), _clean_transcript=lambda s, **kwargs: s,
                         _is_repeat_chunk=lambda *args: False, _REPEAT_MIN=20)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
        bridge = Mock(list_devices=Mock(return_value=[{'id': 'phone'}]), begin_speech=AsyncMock(return_value=True),
                      deliver_audio=AsyncMock(return_value=True), deliver_reply=AsyncMock(return_value=True),
                      cancel_speech=AsyncMock(return_value=True))
        router = SpeechRouter(probe=lambda owner: {'present': present},
                              config=lambda: {'enabled': True, 'owner': '', 'device_id': ''})
        finished = asyncio.Event()
        async def receive():
            yield SimpleNamespace(data=b'pcm' * 1600, tool_call=None, server_content=SimpleNamespace(
                output_transcription=SimpleNamespace(text='Resposta.'), input_transcription=None,
                turn_complete=True, waiting_for_input=True))
            finished.set()
            await asyncio.Event().wait()
        host = SimpleNamespace(session=SimpleNamespace(receive=receive), _last_answer_at=time.monotonic(),
            _clear_stall=Mock(), _resume_handle=None, _interrupted=False, _turn_done_event=asyncio.Event(),
            _speech_router=router, _android_reply={'reply_device': 'phone', 'reply_id': 'original-request'},
            _dashboard=SimpleNamespace(android_bridge=bridge, broadcast=AsyncMock()), audio_in_queue=asyncio.Queue(),
            ui=Mock(), set_speaking=Mock(), _asst_name='JARVIS', _engine=None, _visemes=Mock(),
            _session_log=[], _last_out_logged='', _vision_close_pending=False)
        from core.speech_announcements import SpeechAnnouncements
        host._speech_announcements = SpeechAnnouncements()
        with patch('core.continuity_runtime.remember_turn', Mock()):
            task = asyncio.create_task(namespace['_receive_audio'](host))
            try:
                await asyncio.wait_for(finished.wait(), 2)
                await asyncio.sleep(0)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        return host, bridge

    async def test_present_real_receive_loop_enqueues_only_pc_audio(self):
        host, bridge = await self.run_turn(True)
        self.assertFalse(host.audio_in_queue.empty())
        bridge.deliver_audio.assert_not_called()
        bridge.deliver_reply.assert_awaited_once()
        self.assertFalse(bridge.deliver_reply.call_args.kwargs['speak'])
        self.assertEqual(bridge.deliver_reply.call_args.args[2], '')

    async def test_absent_real_receive_loop_never_enqueues_pc_audio(self):
        host, bridge = await self.run_turn(False)
        self.assertTrue(host.audio_in_queue.empty())
        bridge.deliver_audio.assert_awaited_once()
        request = bridge.deliver_audio.call_args.args[1]
        self.assertTrue(request.startswith('presence_'))
        self.assertTrue(any(call.args[1] == request and call.kwargs.get('audio_streamed')
                            for call in bridge.deliver_reply.call_args_list))
