import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
from core.android_bridge import AndroidBridge
from dashboard.server import DashboardServer


class AndroidBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_desktop_pcm_is_forwarded_unchanged_to_requested_phone(self):
        import base64
        bridge = AndroidBridge()
        socket = Mock(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(socket, 'phone-one', 'Phone')
        pcm = b'\x00\x01\xff\x02' * 10
        self.assertTrue(await bridge.deliver_audio('phone-one', 'request-123', pcm))
        message = socket.send_json.call_args.args[0]
        self.assertEqual(base64.b64decode(message['data']), pcm)
        self.assertEqual(message['rate'], 24000)
        self.assertEqual(message['request_id'], 'request-123')

    async def test_assistant_reply_only_goes_to_requested_authorized_android(self):
        bridge = AndroidBridge()
        first = Mock(send_json=AsyncMock(), close=AsyncMock())
        second = Mock(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(first, 'phone-one', 'One')
        await bridge.attach(second, 'phone-two', 'Two')
        self.assertTrue(await bridge.deliver_reply('phone-two', 'request-123', 'Resposta para falar no celular.'))
        first.send_json.assert_not_called()
        self.assertEqual(second.send_json.call_args.args[0]['type'], 'assistant_reply')
        self.assertFalse(await bridge.deliver_reply('offline', 'request-123', 'No'))

    async def test_only_matching_device_reply_completes_request(self):
        bridge = AndroidBridge()
        socket = Mock(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(socket, 'phone-one', 'My phone')
        task = asyncio.create_task(bridge.request('phone-one', 'open_app', {'app':'WhatsApp'}))
        await asyncio.sleep(.01)
        message = socket.send_json.call_args.args[0]
        bridge.reply('other-phone', {'id':message['id'], 'result':{'ok':True}})
        self.assertFalse(task.done())
        bridge.reply('phone-one', {'id':message['id'], 'result':{'ok':True, 'launched':'example'}})
        self.assertTrue((await task)['ok'])
        self.assertEqual(bridge.pending, {})

    async def test_offline_unsupported_and_revoked_never_send(self):
        bridge = AndroidBridge()
        self.assertFalse((await bridge.request(None, 'tap'))['ok'])
        socket = Mock(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(socket, 'phone-one', 'Phone', lambda:False)
        self.assertFalse((await bridge.request('phone-one', 'tap'))['ok'])
        self.assertFalse((await bridge.request('phone-one', 'shell'))['ok'])
        socket.send_json.assert_not_called()

    async def test_disconnect_releases_pending_and_old_socket_cannot_remove_replacement(self):
        bridge = AndroidBridge()
        old = Mock(send_json=AsyncMock(), close=AsyncMock())
        new = Mock(send_json=AsyncMock(), close=AsyncMock())
        await bridge.attach(old, 'phone-one', 'Old')
        await bridge.attach(new, 'phone-one', 'New')
        bridge.detach(old, 'phone-one')
        self.assertEqual(bridge.list_devices()[0]['name'], 'New')
        task = asyncio.create_task(bridge.request('phone-one', 'status'))
        await asyncio.sleep(.01)
        bridge.detach(new, 'phone-one')
        self.assertFalse((await task)['ok'])


class AndroidWebSocketTests(unittest.TestCase):
    def test_mobile_config_exports_require_auth_and_only_include_selected_fields(self):
        from unittest.mock import patch
        from core.mobile_export import home_config, memories
        camera = {'name': 'DVR teste', 'host': '192.168.1.9', 'vendor': 'intelbras',
                  'username': 'admin', 'password': 'fake-camera-secret', 'channel_count': '16'}
        with tempfile.TemporaryDirectory() as directory, \
                patch('plugins.cameras_locais._cameras', return_value=[camera]), \
                patch('core.mobile_export.get_plugin_config', return_value={'api_key': 'fake-id', 'api_secret': 'fake-tuya-secret', 'region': 'us', 'unrelated': 'never-export'}), \
                patch('memory.memory_manager.all_entries_for_ui', return_value=[{'category': 'notes', 'key': 'project', 'value': 'Test'}]):
            server = DashboardServer(device_store_path=Path(directory)/'devices.json')
            server._tokens['test-bearer'] = time.time()
            headers = {'Authorization': 'Bearer test-bearer'}
            with TestClient(server.app) as client:
                for path in ('/api/android/home-config', '/api/android/memories'):
                    self.assertEqual(client.post(path).status_code, 401)
                response = client.post('/api/android/home-config', headers=headers)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertEqual(response.json(), home_config())
                self.assertNotIn('never-export', response.text)
                self.assertEqual(response.json()['cameras'][0]['channel_count'], 16)
                self.assertEqual(client.post('/api/android/memories', headers=headers).json(), memories())

    def test_native_command_keeps_phone_reply_address_and_rejects_offline_target(self):
        with tempfile.TemporaryDirectory() as directory:
            server = DashboardServer(device_store_path=Path(directory)/'devices.json')
            server.android_bridge = AndroidBridge()
            server._tokens['test-bearer'] = time.time()
            headers = {'Authorization':'Bearer test-bearer'}
            with TestClient(server.app) as client:
                body = {'text':'Pedido de teste', 'reply_device':'phone-123', 'reply_id':'request-123'}
                self.assertEqual(client.post('/api/command',headers=headers,json=body).status_code,409)
                self.assertTrue(server._command_queue.empty())
                with client.websocket_connect('/ws/android',headers=headers) as socket:
                    socket.send_json({'type':'hello','device_id':'phone-123','name':'Android'})
                    socket.receive_json()
                    self.assertEqual(client.post('/api/command',headers=headers,json=body).status_code,200)
                    self.assertEqual(server._command_queue.get_nowait(),body)

    def test_apk_download_requires_pairing_and_fixed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            server = DashboardServer(device_store_path=Path(directory)/'devices.json')
            server._android_apk_path = Path(directory)/'app.apk'
            server._tokens['test-bearer'] = time.time()
            headers = {'Authorization':'Bearer test-bearer'}
            with TestClient(server.app) as client:
                self.assertEqual(client.get('/api/android/apk').status_code,401)
                self.assertEqual(client.get('/api/android/apk',headers=headers).status_code,404)
                server._android_apk_path.write_bytes(b'test-apk')
                response = client.get('/api/android/apk',headers=headers)
                self.assertEqual(response.content,b'test-apk')
                self.assertEqual(response.headers['cache-control'],'no-store')

    def test_paired_phone_request_reply_flow_and_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            server = DashboardServer(device_store_path=Path(directory)/'devices.json')
            server.android_bridge = AndroidBridge()
            server._tokens['test-bearer'] = time.time()
            headers = {'Authorization':'Bearer test-bearer'}
            with TestClient(server.app) as client:
                self.assertEqual(client.get('/api/android/devices').status_code,401)
                with client.websocket_connect('/ws/android',headers=headers) as socket:
                    socket.send_json({'type':'hello','device_id':'test-phone-123','name':'Test Android'})
                    self.assertEqual(socket.receive_json()['type'],'ready')
                    self.assertEqual(len(client.get('/api/android/devices',headers=headers).json()['devices']),1)
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        request = pool.submit(server.android_bridge.request_sync,'test-phone-123','status')
                        message = socket.receive_json()
                        socket.send_json({'type':'result','id':message['id'],'result':{'ok':True,'accessibility':True}})
                        self.assertTrue(request.result(timeout=5)['accessibility'])
