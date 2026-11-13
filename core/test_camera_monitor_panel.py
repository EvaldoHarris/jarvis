import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QBuffer, QIODevice
from core import camera_monitor as cm
from core.camera_monitor_panel import MonitorPanel, MonitorViewer, MonitorAlertWindow


class MonitorPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_viewer_reuses_feed_and_clears_missing_image_without_stopping_monitor(self):
        image = QImage(32, 18, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.blue)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'JPEG')
        state = dict(group='Sítio', group_id='site', state='observando', current_camera='Entrada',
                     checked_frames=12, alerts=1, running=True, events=[
                         dict(time='18:00', camera='Entrada', summary='Pessoa visível.')])
        with patch('core.camera_monitor_panel.hub') as hub:
            hub.status.return_value = [state]
            hub.preview.return_value = dict(camera='Entrada', jpeg=bytes(buffer.data()))
            viewer = MonitorViewer()
            viewer.show()
            viewer.refresh()
            self.assertFalse(viewer.image.pixmap().isNull())
            self.assertEqual(viewer.events.count(), 1)
            hub.preview.return_value = None
            viewer.refresh()
            self.assertIn('Aguardando', viewer.image.text())
            viewer.close()
            hub.start.assert_not_called()
            hub.stop.assert_not_called()

    def test_alert_window_shows_event_and_expires_image(self):
        image = QImage(320, 180, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.blue)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'JPEG')
        packet = dict(alert_id='monitor_test', group='Sítio', camera='Entrada', labels=['pessoa'],
                      time='18:00', image=bytes(buffer.data()), offset=-5., final=False)
        window = MonitorAlertWindow()
        window.begin(packet)
        window.receive(packet)
        self.assertFalse(window.image.pixmap().isNull())
        self.assertIn('-5.0', window.status.text())
        window.toggle()
        window.receive(dict(packet, offset=5.))
        self.assertEqual(window.position, -5.)
        self.assertFalse(window.playing)
        window.seek(0.)
        self.assertEqual(window.position, 0.)
        window.scrub(7000)
        self.assertEqual(window.position, 2.)
        window.latest()
        self.assertEqual(window.position, 5.)
        window.receive(dict(packet, final=True, image=b''))
        self.assertIn('encerrada', window.status.text())
        window.clear_image()
        self.assertEqual(window.status.text(), 'Imagem expirada.')
        window.close()

    def test_panel_creates_two_independent_groups_and_restores_camera_choices(self):
        catalog = [dict(name='Entrada', _settings_group='one', username='a', password='p', vendor='icsee', cloud_id='id'),
                   dict(name='Casa', _settings_group='two', username='', password='', vendor='icsee', cloud_id='id2')]
        with tempfile.TemporaryDirectory() as tmp, patch.object(cm, 'CONFIG', Path(tmp)/'groups.json'), \
                patch('core.camera_monitor_panel.camera_catalog', return_value=catalog):
            panel = MonitorPanel(Mock())
            panel.name.setText('Sitio')
            panel.cameras.item(0).setCheckState(Qt.CheckState.Checked)
            panel.save()
            panel.new_group()
            panel.name.setText('Casa')
            panel.cameras.item(1).setCheckState(Qt.CheckState.Checked)
            panel.save()
            groups = cm.load_groups()
            self.assertEqual(len(groups), 2)
            self.assertEqual(groups[0]['cameras'], ['one'])
            self.assertEqual(groups[1]['cameras'], ['two'])
            panel.selector.setCurrentIndex(0)
            self.assertEqual(panel.cameras.item(0).checkState(), Qt.CheckState.Checked)
            self.assertEqual(panel.cameras.item(1).checkState(), Qt.CheckState.Unchecked)
            panel.close()


if __name__ == '__main__': unittest.main()
