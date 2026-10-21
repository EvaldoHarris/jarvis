import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from dashboard.server import DashboardServer


class RememberedDeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "devices.json"

    def server(self):
        return DashboardServer(device_store_path=self.path)

    def test_manual_pairing_survives_restart_and_renews_access(self):
        first = self.server()
        with TestClient(first.app) as client:
            key = first.new_key()
            response = client.post('/login', json={'pin': key})
            self.assertEqual(response.status_code, 200)
            device = response.json()['device_token']
            old_token = response.json()['token']
            self.assertNotIn(device, self.path.read_text())
        second = self.server()
        with TestClient(second.app) as client:
            self.assertEqual(client.get('/api/panel', headers={'Authorization': 'Bearer '+old_token}).status_code, 401)
            renewed = client.post('/api/device-login', json={'device_token': device})
            self.assertEqual(renewed.status_code, 200)
            self.assertEqual(renewed.json()['key'], key)
            headers = {'Authorization': 'Bearer '+renewed.json()['token']}
            self.assertEqual(client.get('/api/panel', headers=headers).status_code, 200)
            self.assertEqual(client.post('/api/revoke-devices', headers=headers).status_code, 200)
        third = self.server()
        with TestClient(third.app) as client:
            self.assertEqual(client.post('/api/device-login', json={'device_token':device}).status_code, 401)

    def test_qr_pairing_is_also_persisted_and_unknown_token_rejected(self):
        first = self.server()
        with TestClient(first.app) as client:
            response = client.get('/auto-login', params={'key':first.new_key()})
            device = re.search(r"jarvis_device_token','([^']+)'", response.text).group(1)
        with TestClient(self.server().app) as client:
            self.assertEqual(client.post('/api/device-login', json={'device_token':device}).status_code, 200)
            for invalid in ('x'*43, None, {}, 42):
                self.assertEqual(client.post('/api/device-login', json={'device_token':invalid}).status_code, 401)

    def test_corrupt_store_does_not_disable_server_or_accept_device(self):
        self.path.write_text('{broken')
        self.assertEqual(self.server()._device_sessions, {})


if __name__ == '__main__':
    unittest.main()
