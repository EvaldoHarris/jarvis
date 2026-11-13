import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from core import monitor_recordings as store


class RecordingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(store, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def packet(self, suffix='a'):
        return dict(alert_id='monitor_' + suffix * 24, group='Sítio', camera='Entrada',
                    labels=['carro'], time='2026-11-13T12:00:00-03:00', offset=-5., final=False)

    def test_persists_timed_frames_and_lists_recording(self):
        packet = self.packet()
        store.append(packet, b'\xff\xd8first')
        store.append(dict(packet, offset=2.), b'\xff\xd8second')
        store.append(dict(packet, final=True), b'')
        self.assertEqual(store.load(packet['alert_id']), [(-5., b'\xff\xd8first'), (2., b'\xff\xd8second')])
        self.assertEqual(store.list_recordings()[0]['camera'], 'Entrada')

    def test_expiry_deletes_pair_and_quota_evicts_oldest(self):
        old = self.packet()
        store.append(old, b'\xff\xd8first')
        for file in self.root.iterdir():
            os.utime(file, (time.time()-90000, time.time()-90000))
        store.prune()
        self.assertEqual(list(self.root.iterdir()), [])
        store.append(old, b'\xff\xd8first')
        for file in self.root.iterdir():
            os.utime(file, (time.time()-5, time.time()-5))
        new = self.packet('b')
        store.append(new, b'\xff\xd8second')
        new_size = sum(p.stat().st_size for p in self.root.glob(new['alert_id'] + '.*'))
        with patch.object(store, 'MAX_TOTAL', new_size):
            store.prune()
        self.assertFalse((self.root / (old['alert_id'] + '.frames')).exists())
        self.assertTrue((self.root / (new['alert_id'] + '.frames')).exists())

    def test_rejects_paths_and_keeps_complete_frames_of_partial_write(self):
        with self.assertRaises(ValueError): store.load('../outside')
        packet = self.packet()
        store.append(packet, b'\xff\xd8first')
        with (self.root / (packet['alert_id'] + '.frames')).open('ab') as stream:
            stream.write(b'partial')
        self.assertEqual(len(store.load(packet['alert_id'])), 1)

    def test_per_event_size_limit(self):
        with patch.object(store, 'MAX_EVENT', 20):
            packet = self.packet()
            store.append(packet, b'\xff\xd8first')
            store.append(dict(packet, offset=1), b'\xff\xd8second')
            self.assertEqual(len(store.load(packet['alert_id'])), 1)


if __name__ == '__main__': unittest.main()
