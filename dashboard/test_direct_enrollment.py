import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from core.test_direct_secure import DirectSecureTests
from dashboard.server import DashboardServer


class DirectEnrollmentRoutes(DirectSecureTests):
    def test_https_mode_bootstrap_accepts_sealed_request_without_redirect(self):
        reply, request = self.enroll()
        instance = DashboardServer.__new__(DashboardServer)
        instance._ip = "192.168.15.13"
        with patch("core.direct_secure.authority", self.ca):
            with TestClient(instance._build_redirect_app(), client=("192.168.15.20", 1234)) as client:
                response = client.post("/api/direct/enroll", json=request, follow_redirects=False)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("data", response.json())
                ca_response=client.get("/api/direct/ca",follow_redirects=False)
                self.assertEqual(ca_response.status_code,200)
                from core.direct_secure import compact_invitation,pem
                import base64,zlib,json,hashlib
                qr=compact_invitation(self.ca.ticket('http://127.0.0.1:8000/api/direct/enroll','https://127.0.0.1:9443'))
                compact=json.loads(zlib.decompress(base64.urlsafe_b64decode(qr.split(':',2)[2])))
                self.assertNotIn('ca',compact)
                self.assertEqual(compact['ca_sha256'],hashlib.sha256(ca_response.json()['ca'].encode()).hexdigest())
                self.assertLess(len(qr),500)
                self.assertEqual(client.get("/login", follow_redirects=False).status_code, 307)
                self.ca.tickets.clear()
                response = client.post("/api/direct/enroll", json=request)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "invitation_expired")
            with TestClient(instance._build_redirect_app(), client=("8.8.8.8", 1234)) as client:
                self.assertEqual(client.post("/api/direct/enroll", json=request).json()["code"], "local_network_required")
