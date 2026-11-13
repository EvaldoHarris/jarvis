import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from core import camera_monitor as cm


def group(name='Sítio', camera='one'):
    return cm.group_config(dict(name=name, cameras=[camera]))


class MonitorTests(unittest.TestCase):
    def test_two_observations_required_and_stationary_object_does_not_spam(self):
        gate = cm.EventGate(30)
        self.assertEqual(gate.observe('a', ['pessoa'], 0), [])
        self.assertEqual(gate.observe('a', ['pessoa'], 2), ['pessoa'])
        self.assertEqual(gate.observe('a', ['pessoa'], 100), [])
        self.assertEqual(gate.observe('a', [], 101), [])
        self.assertEqual(gate.observe('a', [], 112), [])
        self.assertEqual(gate.observe('a', ['pessoa'], 113), [])
        self.assertEqual(gate.observe('a', ['pessoa'], 115), ['pessoa'])

    def test_cooldown_and_camera_classes_are_independent(self):
        gate = cm.EventGate(180)
        gate.observe('a', ['carro'], 0)
        self.assertEqual(gate.observe('a', ['carro'], 2), ['carro'])
        gate.observe('a', [], 3); gate.observe('a', [], 14)
        gate.observe('a', ['carro'], 15)
        self.assertEqual(gate.observe('a', ['carro'], 17), [])
        gate.observe('b', ['carro'], 17)
        self.assertEqual(gate.observe('b', ['carro'], 19), ['carro'])

    def test_group_config_persists_multiple_groups_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cm, 'CONFIG', Path(tmp)/'groups.json'):
            groups = cm.save_groups([dict(group(), password='secret'), group('Casa', 'two')])
            self.assertEqual(len(cm.load_groups()), 2)
            self.assertNotIn('secret', cm.CONFIG.read_text())
            with self.assertRaises(ValueError):
                cm.save_groups([groups[0], dict(groups[1], name=groups[0]['name'])])
            self.assertEqual(len(cm.load_groups()), 2)

    def test_detection_reaches_ai_then_voice_once_and_stops_feed(self):
        closed = threading.Event()
        spoken = threading.Event()
        class Feed:
            closed = False
            def __init__(self, camera): self.seq = 0
            def next(self, previous):
                time.sleep(.01)
                self.seq += 1
                return self.seq, b'jpeg', time.monotonic()
            def close(self): self.closed = True; closed.set()
        settings = group(); settings['interval'] = .001
        detector = Mock(); detector.detect.return_value = [dict(label='pessoa', score=.9, box=[.2, .2, .1, .4])]
        player = Mock(); player.request_say.side_effect = lambda text: spoken.set()
        analyze = Mock(return_value='Uma pessoa está visível.')
        monitor = cm.Monitor(settings, [dict(name='Entrada', _settings_group='one')], player,
                             lambda threshold: detector, Feed, analyze)
        monitor.start()
        self.assertTrue(spoken.wait(2))
        time.sleep(.05)
        monitor.stop(); monitor.thread.join(timeout=2)
        analyze.assert_called_once()
        player.request_say.assert_called_once()
        player.request_monitor_alert.assert_called_once()
        self.assertEqual(player.request_monitor_alert.call_args.args[0]['labels'], ['pessoa'])
        self.assertTrue(closed.is_set())
        self.assertFalse(monitor.status()['running'])

    def test_empty_frames_do_not_call_ai(self):
        detector = Mock(); detector.detect.return_value = []
        class Feed:
            closed = False
            def __init__(self, camera): self.seq = 0
            def next(self, previous):
                time.sleep(.01); self.seq += 1
                return self.seq, b'jpeg', time.monotonic()
            def close(self): self.closed = True
        settings = group(); settings['interval'] = .001
        analyze = Mock()
        monitor = cm.Monitor(settings, [dict(name='Entrada', _settings_group='one')], Mock(),
                             lambda threshold: detector, Feed, analyze)
        monitor.start(); time.sleep(.08); monitor.stop(); monitor.thread.join(timeout=2)
        analyze.assert_not_called()

    def test_stop_during_analysis_suppresses_late_announcement(self):
        entered, release = threading.Event(), threading.Event()
        def analyze(*args): entered.set(); release.wait(2); return 'Uma pessoa.'
        player = Mock()
        monitor = cm.Monitor(group(), [], player, Mock(), analyzer=analyze)
        monitor.events.put(('Entrada', b'jpeg', ['pessoa'], '2026-11-12T10:00:00-03:00'))
        thread = threading.Thread(target=monitor._analyze); thread.start()
        self.assertTrue(entered.wait(1)); monitor.stop(); release.set(); thread.join(timeout=2)
        player.request_say.assert_not_called()

    def test_two_disjoint_groups_allowed_but_same_camera_rejected(self):
        catalog = [dict(_settings_group=key, name=key, vendor='icsee', cloud_id='123', username='a', password='p')
                   for key in ('one','two')]
        class FakeMonitor:
            def __init__(self, group, cameras, *args):
                self.group, self.cameras = group, cameras
                self.thread = Mock(); self.thread.is_alive.return_value = False
            def start(self): self.thread.is_alive.return_value = True
            def stop(self, **kwargs): self.thread.is_alive.return_value = False
        hub = cm.Hub()
        with patch.object(cm, 'camera_catalog', return_value=catalog), patch.object(cm, 'Monitor', FakeMonitor):
            hub.start(group(), Mock()); hub.start(group('Casa','two'), Mock())
            self.assertEqual(len(hub.monitors), 2)
            with self.assertRaises(ValueError): hub.start(group('Outro','one'), Mock())
            hub.stop()


if __name__ == '__main__': unittest.main()
