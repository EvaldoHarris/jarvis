import base64
import io
import json
import struct
import threading
import unittest
from unittest.mock import Mock, patch

from core import rtsp_capture, xmeye_camera, xmeye_runtime
from core.rtsp_live import LiveCamera
from plugins import cameras_locais
from scripts.xmeye_sandbox.stream import jpeg_frames


DEVICE = dict(name='Sitio', cloud_id='abcdef1234567890', username='operator')


class CloudCameraTests(unittest.TestCase):
    def camera(self):
        return dict(DEVICE, vendor='icsee', password='private-device-password', channel=1, stream='1')

    def test_icsee_snapshot_uses_cloud_without_rtsp(self):
        jpeg = b'\xff\xd8test\xff\xd9'
        result = dict(status='video_verified', jpeg_base64=base64.b64encode(jpeg).decode())
        with patch.object(xmeye_camera, 'run_probe', return_value=result) as probe, \
                patch.object(rtsp_capture, 'build_url') as rtsp:
            self.assertEqual(rtsp_capture.snapshot(self.camera()), jpeg)
        rtsp.assert_not_called()
        payload = probe.call_args.args[0]
        self.assertEqual(payload['cloud_id'], DEVICE['cloud_id'])
        self.assertEqual(payload['channel'], 0)

    def test_cloud_error_does_not_echo_native_text(self):
        with patch.object(xmeye_camera, 'run_probe', return_value={
            'status': 'login_failed', 'sdk_error': 106, 'message': 'private-device-password'
        }):
            with self.assertRaisesRegex(RuntimeError, '106') as error:
                xmeye_camera.snapshot(self.camera())
        self.assertNotIn('private-device-password', str(error.exception))

    def test_saved_device_credentials_preserve_dvr_and_do_not_fill_other_cameras(self):
        config = {'camera2_password': 'dvr-secret', 'icsee_abcdef1234567891_password': 'other-secret'}
        request = xmeye_camera.request_for(self.camera())
        with patch.object(xmeye_runtime, 'load_devices', return_value=[DEVICE]), \
                patch('memory.config_manager.get_plugin_config', return_value=config), \
                patch('memory.config_manager.save_plugin_config') as save:
            xmeye_runtime.save_device_credentials(request)
        values = save.call_args.args[1]
        self.assertEqual(values['camera2_password'], 'dvr-secret')
        self.assertEqual(values['icsee_abcdef1234567891_password'], 'other-secret')
        self.assertEqual(values['icsee_abcdef1234567890_password'], 'private-device-password')
        self.assertEqual(config['camera2_password'], 'dvr-secret')

    def test_imported_devices_route_by_unique_name_and_configured_serial(self):
        devices = [DEVICE, dict(DEVICE, cloud_id='abcdef1234567891')]
        with patch.object(cameras_locais, 'load_devices', return_value=devices):
            cameras = cameras_locais._cameras({'icsee_abcdef1234567890_password': 'secret'})
        imported = [c for c in cameras if c['vendor'] == 'icsee']
        self.assertEqual(len(imported), 2)
        self.assertNotEqual(imported[0]['name'], imported[1]['name'])
        self.assertEqual(cameras_locais._resolve('Sitio (7890)', cameras)['cloud_id'], DEVICE['cloud_id'])
        self.assertEqual(imported[0]['password'], 'secret')
        self.assertEqual(imported[1]['password'], '')
        with self.assertRaises(ValueError):
            cameras_locais._resolve('icsee', cameras)

    def test_live_credentials_use_stdin_and_close_removes_its_container(self):
        process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
        process.poll.return_value = None
        with patch.object(xmeye_camera.subprocess, 'Popen', return_value=process) as popen, \
                patch.object(xmeye_camera.subprocess, 'run') as remove:
            owned = xmeye_camera.open_live(self.camera())
            owned.kill()
        argv = popen.call_args.args[0]
        self.assertNotIn('private-device-password', ' '.join(argv))
        self.assertIn('--cap-drop=ALL', argv)
        self.assertIn('--pull=never', argv)
        self.assertEqual(remove.call_args.args[0], ['docker', 'rm', '-f', owned.name])
        process.kill.assert_called_once()

    def test_cloud_stream_reaches_existing_hud_protocol(self):
        jpeg = b'\xff\xd8test\xff\xd9'
        process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(struct.pack('!I', len(jpeg)) + jpeg))
        process.stdin.close()
        process.poll.return_value = None
        events, ended = [], threading.Event()

        def emit(event):
            events.append(event)
            if event[1] == 'end':
                ended.set()

        with patch.object(xmeye_camera, 'open_live', return_value=process):
            LiveCamera().start(self.camera(), emit)
            self.assertTrue(ended.wait(2))
        self.assertEqual([event[1] for event in events], ['start', 'frame', 'end'])
        self.assertEqual(events[1][2], jpeg)
        process.kill.assert_called()

    def test_jpeg_stream_preserves_multiple_frames_and_discards_leading_noise(self):
        frames = [b'\xff\xd8first\xff\xd9', b'\xff\xd8second\xff\xd9']
        source = io.BufferedReader(io.BytesIO(b'noise' + b''.join(frames)))
        self.assertEqual(list(jpeg_frames(source)), frames)


if __name__ == '__main__':
    unittest.main()
