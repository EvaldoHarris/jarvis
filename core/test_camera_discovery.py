import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import camera_discovery as discovery
from plugins import cameras_locais


class DiscoveryTests(unittest.TestCase):
    def test_only_active_physical_private_networks_and_bounded_scope(self):
        def address(ip, mask):
            return SimpleNamespace(family=socket.AF_INET, address=ip, netmask=mask)
        interfaces = {
            'Ethernet': [address('192.168.15.13', '255.255.255.0')],
            'Wi-Fi': [address('10.2.3.4', '255.255.0.0')],
            'vEthernet WSL': [address('192.168.144.1', '255.255.255.0')],
            'Disconnected': [address('192.168.99.2', '255.255.255.0')],
            'LinkLocal': [address('169.254.1.2', '255.255.0.0')],
            'Public': [address('8.8.8.8', '255.255.255.0')],
        }
        stats = {name: SimpleNamespace(isup=name != 'Disconnected') for name in interfaces}
        with patch.object(discovery.psutil, 'net_if_addrs', return_value=interfaces), \
                patch.object(discovery.psutil, 'net_if_stats', return_value=stats):
            self.assertEqual(discovery.local_networks(), [
                ('192.168.15.0/24', '192.168.15.13', False),
                ('10.2.3.0/24', '10.2.3.4', True)])

    def test_deduplicates_device_ports_and_does_not_claim_video_or_vendor_proof(self):
        def probe(target):
            host, port = target
            return (host, port, port == 554) if host == '192.168.1.2' and port in (554, 37777) else None
        with patch.object(discovery, 'local_networks', return_value=[('192.168.1.0/30', '192.168.1.1', False)]), \
                patch.object(discovery, '_probe', side_effect=probe) as scan:
            result = discovery.discover()
        self.assertEqual(scan.call_count, 4)
        self.assertEqual(len(result['devices']), 1)
        device = result['devices'][0]
        self.assertEqual(device['ports'], [554, 37777])
        self.assertTrue(device['rtsp_confirmed'])
        self.assertFalse(device['verified_video'])
        self.assertIn('Possível', device['hint'])

    def test_unavailable_network_reports_error(self):
        with patch.object(discovery, 'local_networks', return_value=[]):
            with self.assertRaises(ValueError):
                discovery.discover()

    def test_discover_action_never_captures_camera_or_starts_video(self):
        result = {'networks': ['192.168.1.0/24'], 'devices': [], 'limited_to_24': False, 'note': 'test'}
        with patch.object(discovery, 'discover', return_value=result), \
                patch.object(cameras_locais, 'snapshot') as capture:
            response = cameras_locais.run({'action': 'discover'})
            self.assertIn('192.168.1.0/24', response)
            capture.assert_not_called()

    def test_registry_passes_search_action_to_settings_ui(self):
        from core.plugin_loader import PluginRegistry
        record = SimpleNamespace(name='cameras_locais', settings=cameras_locais.PLUGIN_SETTINGS)
        registry = PluginRegistry({'cameras_locais': record}, lambda message: None)
        with patch('core.plugin_loader.get_plugin_enabled', return_value=True), \
                patch('core.plugin_loader.get_plugin_config', return_value={}):
            schema = registry.settings_schemas()[0]
        self.assertIs(schema['actions'][0]['run'], cameras_locais._search)
        self.assertIs(schema['action']['run'], cameras_locais._test)


if __name__ == '__main__':
    unittest.main()
