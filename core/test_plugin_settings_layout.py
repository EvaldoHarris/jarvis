import ast
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


def overlay_class():
    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('ui.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)
             and n.name in ('C', 'PluginSettingsOverlay')]
    namespace = {name: getattr(QtWidgets, name) for name in dir(QtWidgets)}
    namespace.update(Qt=Qt, pyqtSignal=pyqtSignal, QFont=QFont,
                     FONT_UI='Segoe UI', threading=threading)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'ui.py', 'exec'), namespace)
    return namespace['PluginSettingsOverlay']


def sections():
    return [dict(namespace='cameras', title='Câmeras',
                 groups=[dict(id='one', title='Entrada · iCSee'), dict(id='two', title='Casa · iCSee')],
                 fields=[dict(key='one_user', label='Usuário do dispositivo', group='one', default='admin'),
                         dict(key='one_password', label='Senha do dispositivo', group='one', type='password'),
                         dict(key='two_user', label='Usuário do dispositivo', group='two', default='admin'),
                         dict(key='two_password', label='Senha do dispositivo', group='two', type='password')]),
            dict(namespace='other', title='Outro plugin', fields=[dict(key='host', label='Servidor')])]


class SettingsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.Overlay = overlay_class()

    def setUp(self):
        self.overlay = self.Overlay(sections())
        self.overlay.resize(620, 650)
        self.overlay.show()
        self.app.processEvents()

    def tearDown(self):
        self.overlay.close()

    def test_only_selected_camera_fields_are_visible_and_edits_survive_switch(self):
        widgets = self.overlay._widgets
        widgets[('cameras', 'one_password')].setText('first-secret')
        self.assertTrue(widgets[('cameras', 'one_user')].isVisible())
        self.assertFalse(widgets[('cameras', 'two_user')].isVisible())
        self.overlay._group_selectors['cameras'].setCurrentIndex(1)
        self.app.processEvents()
        self.assertFalse(widgets[('cameras', 'one_user')].isVisible())
        self.assertTrue(widgets[('cameras', 'two_user')].isVisible())
        widgets[('cameras', 'two_password')].setText('second-secret')
        self.assertEqual(self.overlay._gather('cameras')['one_password'], 'first-secret')
        self.assertEqual(self.overlay._gather('cameras')['two_password'], 'second-secret')

    def test_save_current_preserves_unrendered_keys_and_does_not_save_other_plugins(self):
        with patch('memory.config_manager.get_plugin_config', return_value={'hidden_stream': '0'}), \
                patch('memory.config_manager.save_plugin_config') as save:
            self.overlay._save_current()
        save.assert_called_once()
        namespace, values = save.call_args.args
        self.assertEqual(namespace, 'cameras')
        self.assertEqual(values['hidden_stream'], '0')
        self.assertNotIn('host', values)

    def test_plugin_switch_hides_camera_form(self):
        self.overlay._plugin_selector.setCurrentIndex(1)
        self.app.processEvents()
        self.assertFalse(self.overlay._widgets[('cameras', 'one_user')].isVisible())
        self.assertTrue(self.overlay._widgets[('other', 'host')].isVisible())


if __name__ == '__main__':
    unittest.main()
