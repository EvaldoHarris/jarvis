import time
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient
from dashboard.server import DashboardServer


class RemotePanelTests(unittest.TestCase):
    def setUp(self):
        self.server = DashboardServer()
        self.server._tokens["panel-test-token"] = time.time()
        self.client = TestClient(self.server.app)
        self.headers = {"Authorization": "Bearer panel-test-token"}
        self.control = Mock()
        self.server.set_panel_callbacks(lambda: {
            "name": "JARVIS", "connected": True, "state": "LISTENING",
            "muted": False, "level": .2, "cpu": 12, "memory": 45}, self.control)

    def test_state_and_avatar_require_pairing(self):
        self.assertEqual(self.client.get("/api/panel").status_code, 401)
        self.assertEqual(self.client.get("/api/avatar").status_code, 401)
        self.assertEqual(self.client.post("/api/control", json={"action": "interrupt"}).status_code, 401)
        self.control.assert_not_called()

    def test_state_is_real_callback_data_without_configuration_secrets(self):
        response = self.client.get("/api/panel", headers=self.headers)
        self.assertEqual(response.json()["state"], "LISTENING")
        self.assertEqual(response.json()["cpu"], 12)
        self.assertNotIn("key", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_controls_dispatch_only_allowed_typed_actions(self):
        response = self.client.post("/api/control", headers=self.headers,
                                    json={"action": "mute", "value": True})
        self.assertEqual(response.status_code, 200)
        self.control.assert_called_once_with("mute", True)
        self.control.reset_mock()
        self.assertEqual(self.client.post("/api/control", headers=self.headers,
                         json={"action": "mute", "value": "false"}).status_code, 400)
        self.assertEqual(self.client.post("/api/control", headers=self.headers,
                         json={"action": "shutdown"}).status_code, 400)
        self.control.assert_not_called()

    def test_avatar_reuses_desktop_mesh(self):
        from core.avatar_mesh import get_head_mesh
        response = self.client.get("/api/avatar", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["verts"]), len(get_head_mesh()["verts"]))
        self.assertEqual(len(response.json()["edges"]), len(get_head_mesh()["edges"]))

    def test_only_allowlisted_panel_assets_can_be_served(self):
        self.assertEqual(self.client.get("/assets/panel.css").status_code, 200)
        self.assertEqual(self.client.get("/assets/panel.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/api_keys.json").status_code, 404)

    def test_live_audio_requires_explicit_subscription_and_is_not_stored(self):
        with self.client as client:
            with client.websocket_connect("/ws?token=panel-test-token") as ws:
                self.assertFalse(self.server._audio_clients)
                ws.send_json({"type": "listen_audio", "enabled": True})
                self.assertEqual(ws.receive_json(), {"type": "audio_subscription", "enabled": True})
                client.portal.call(self.server.broadcast_audio, b"\x00\x01" * 10)
                message = ws.receive_json()
                self.assertEqual(message["type"], "audio")
                self.assertEqual(message["rate"], 24000)
                self.assertFalse(any(entry.get("type") == "audio" for entry in self.server._history))
                ws.send_json({"type": "listen_audio", "enabled": False})
                self.assertFalse(ws.receive_json()["enabled"])
                self.assertFalse(self.server._audio_clients)


if __name__ == "__main__":
    unittest.main()
