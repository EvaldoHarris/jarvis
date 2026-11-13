import json
import subprocess
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.xmeye_sandbox import control
from scripts.xmeye_sandbox.entry import clean_video


class IsolationTests(unittest.TestCase):
    def test_device_list_preserves_duplicate_names_but_drops_duplicate_ids_and_secrets(self):
        data = [dict(name='Portão', cloud_id='abcdef1234567890', username='operator', password='secret'),
                dict(name='Portão', cloud_id='abcdef1234567891'),
                dict(name='Outra', cloud_id='abcdef1234567890'),
                dict(name='Inválida', cloud_id='https://host')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'devices.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            result = control.load_devices(path)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['username'], 'operator')
        self.assertNotIn('password', result[0])
        self.assertEqual(result[0]['name'], result[1]['name'])
        self.assertNotEqual(result[0]['cloud_id'], result[1]['cloud_id'])

    def test_invalid_local_list_falls_back_to_manual_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'devices.json'
            for text in ('invalid JSON', '{}', '[null, {"cloud_id":123}]'):
                path.write_text(text, encoding='utf-8')
                self.assertEqual(control.load_devices(path), [])

    def test_sdk_markers_are_removed_without_dropping_valid_nals(self):
        data = b'\x00\x00\x00\x01\x80private\x00\x00\x01\x65valid'
        self.assertEqual(clean_video(data), b'\x00\x00\x00\x01\x65valid')

    def test_untrusted_status_cannot_write_secrets_into_report(self):
        self.assertEqual(control.sanitize({'status': 'secret-camera-password',
                                          'sdk_error': 'secret'}), {'status': 'invalid_result'})

    def test_offline_checks_discard_credentials(self):
        for action in ('load', 'init'):
            self.assertEqual(control.validate(dict(action=action, password='secret')),
                             {'action': action})

    def test_credentials_use_stdin_and_no_host_paths_are_mounted(self):
        calls = []

        def run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, b'{"status":"login_failed","sdk_error":106}')

        secret = 'test-device-password'
        with patch.object(control.subprocess, 'run', side_effect=run):
            control.run_probe(dict(action='probe', cloud_id='abcdef1234567890',
                                   username='admin', password=secret))
        args, kwargs = calls[0]
        self.assertNotIn(secret, ' '.join(args))
        self.assertEqual(json.loads(kwargs['input'])['password'], secret)
        self.assertIn('--cap-drop=ALL', args)
        self.assertIn('--read-only', args)
        self.assertIn('--security-opt=no-new-privileges', args)
        self.assertIn('--log-driver=none', args)
        self.assertFalse(any(x in args for x in ('-v', '--volume', '--mount', '-p', '--publish', '--privileged')))
        self.assertEqual(calls[-1][0][:3], ['docker', 'rm', '-f'])

    def test_timeout_removes_only_named_container(self):
        with patch.object(control.subprocess, 'run', side_effect=[
            subprocess.TimeoutExpired('docker', 100), subprocess.CompletedProcess([], 0)
        ]) as run:
            self.assertEqual(control.run_probe({'action': 'init'}), {'status': 'timeout'})
        first, cleanup = run.call_args_list
        name = first.args[0][first.args[0].index('--name') + 1]
        self.assertEqual(cleanup.args[0], ['docker', 'rm', '-f', name])
        self.assertIn('--network=none', first.args[0])

    def test_invalid_device_never_launches_container(self):
        with patch.object(control.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                control.run_probe(dict(action='probe', cloud_id='http://host', username='admin'))
        run.assert_not_called()

    def test_record_drops_credentials_images_and_unknown_sdk_output(self):
        with patch.object(control, 'STATUS') as path:
            result = control.record({'status': 'video_verified', 'password': 'secret',
                                     'cloud_id': 'private', 'jpeg_base64': 'image', 'frames': 4})
        self.assertEqual(result, {'status': 'video_verified', 'frames': 4})
        self.assertNotIn('secret', path.write_text.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
