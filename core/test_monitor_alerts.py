import asyncio
from collections import deque
import io
import struct
import threading
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from core.camera_monitor import FrameFeed
from core.monitor_alerts import AlertDelivery
from core.android_bridge import AndroidBridge


class BufferTests(unittest.TestCase):
    def test_buffer_keeps_recent_frames_and_releases_them_on_close(self):
        feed = FrameFeed.__new__(FrameFeed)
        feed.condition = threading.Condition()
        feed.latest = None
        feed.buffer = deque()
        feed.buffer_bytes = feed.sequence = 0
        feed.closed = feed.cleaned = False
        feed.cleanup_lock = threading.Lock()
        jpeg = b'\xff\xd8test'
        feed.process = Mock(stdout=io.BytesIO((struct.pack('!I', len(jpeg)) + jpeg) * 15))
        with patch('core.camera_monitor.time.monotonic', side_effect=range(15)):
            feed._read()
        self.assertEqual(len(feed.recent()), 6)
        self.assertEqual(feed.recent()[0][2], 9)
        feed.close()
        self.assertEqual(feed.recent(), [])
        self.assertIsNone(feed.latest)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = patch('core.monitor_recordings.ROOT', Path(self.temp.name))
        self.store.start()
        self.addCleanup(self.store.stop)

    async def run_delivery(self, present, phone=True):
        ui = Mock()
        bridge = Mock()
        bridge.list_devices.return_value = [dict(id='phone', monitor_video=True)] if phone else []
        bridge.deliver_monitor_frame = AsyncMock(return_value=True)
        delivery = AlertDelivery(ui, lambda: bridge)
        now = time.monotonic()
        event = dict(group='Sítio', camera='Entrada', labels=['pessoa'], time='10:00', trigger=now)
        feed = Mock(closed=True)
        feed.recent.return_value = []
        with patch('core.speech_routing.settings', return_value=dict(enabled=False, device_id='')), \
                patch('core.monitor_alerts.pc_active', return_value=present), \
                patch('core.monitor_alerts.asyncio.sleep', new=AsyncMock()):
            await delivery.deliver(event, feed, [(1, b'\xff\xd8first', now-5), (2, b'\xff\xd8second', now)], threading.Event())
        return ui, bridge

    async def test_pc_receives_pre_event_images_in_order_and_end_marker(self):
        ui, bridge = await self.run_delivery(True)
        packets = [c.args[0] for c in ui.show_monitor_alert.call_args_list]
        self.assertEqual([p['offset'] for p in packets[:2]], [-5., 0.])
        self.assertEqual(packets[0]['type'], 'monitor_alert')
        self.assertTrue(packets[-1]['final'])
        bridge.deliver_monitor_frame.assert_not_awaited()

    async def test_absent_user_routes_to_paired_phone_and_offline_falls_back(self):
        ui, bridge = await self.run_delivery(False)
        self.assertEqual(bridge.deliver_monitor_frame.await_count, 3)
        ui.show_monitor_alert.assert_not_called()
        ui, bridge = await self.run_delivery(False, phone=False)
        self.assertEqual(ui.show_monitor_alert.call_count, 3)
        ui.write_log.assert_called()

    async def test_bridge_requires_authorized_device_and_feature_support(self):
        bridge = AndroidBridge()
        socket = Mock(send_json=AsyncMock())
        await bridge.attach(socket, 'phone', 'Phone', monitor_video=True)
        self.assertTrue(await bridge.deliver_monitor_frame('phone', {'type': 'monitor_alert'}, b'jpeg'))
        bridge.devices['phone']['authorized'] = lambda: False
        self.assertFalse(await bridge.deliver_monitor_frame('phone', {}, b'jpeg'))
        self.assertEqual(socket.send_json.await_count, 1)

    async def test_phone_send_failure_falls_back_to_pc(self):
        ui, bridge = Mock(), Mock()
        bridge.list_devices.return_value = [dict(id='phone', monitor_video=True)]
        bridge.deliver_monitor_frame = AsyncMock(return_value=False)
        delivery = AlertDelivery(ui, lambda: bridge)
        now = time.monotonic()
        event = dict(group='Sítio', camera='Entrada', labels=['carro'], time='10:00', trigger=now)
        feed = Mock(closed=True)
        feed.recent.return_value = []
        with patch('core.speech_routing.settings', return_value=dict(enabled=False, device_id='')), \
                patch('core.monitor_alerts.pc_active', return_value=False), \
                patch('core.monitor_alerts.asyncio.sleep', new=AsyncMock()):
            await delivery.deliver(event, feed, [(1, b'jpeg', now)], threading.Event())
        self.assertEqual(ui.show_monitor_alert.call_args_list[0].args[0]['type'], 'monitor_alert')
        self.assertIn('interrompido', ui.write_log.call_args.args[0])

    async def test_stopped_group_does_not_open_an_alert(self):
        ui = Mock()
        stop = threading.Event()
        stop.set()
        await AlertDelivery(ui).deliver(dict(group='Sítio'), Mock(), [(1, b'jpeg', 0)], stop)
        ui.show_monitor_alert.assert_not_called()


if __name__ == '__main__': unittest.main()
