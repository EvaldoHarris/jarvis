import unittest
from unittest.mock import Mock, patch
from core import docker_startup as ds


class DockerStartupTests(unittest.TestCase):
    def test_running_engine_does_not_launch_desktop(self):
        with patch.object(ds.os, 'name', 'nt'), \
                patch.object(ds, 'engine_ready', return_value=True), \
                patch.object(ds.subprocess, 'Popen') as launch:
            ds.ensure_docker(Mock())
            launch.assert_not_called()

    def test_starts_installed_desktop_and_reports_ready(self):
        log = Mock()
        with patch.object(ds.os, 'name', 'nt'), \
                patch.object(ds, 'engine_ready', side_effect=[False, True]), \
                patch.object(ds, 'desktop_path', return_value='Docker Desktop.exe'), \
                patch.object(ds.subprocess, 'Popen') as launch:
            ds.ensure_docker(log)
        launch.assert_called_once()
        self.assertIn('Docker pronto', log.call_args.args[0])

    def test_missing_installation_and_startup_timeout_are_reported(self):
        log = Mock()
        with patch.object(ds.os, 'name', 'nt'), \
                patch.object(ds, 'engine_ready', return_value=False), \
                patch.object(ds, 'desktop_path', return_value=None):
            ds.ensure_docker(log)
        self.assertIn('não encontrado', log.call_args.args[0])
        with patch.object(ds.os, 'name', 'nt'), \
                patch.object(ds, 'engine_ready', return_value=False), \
                patch.object(ds, 'desktop_path', return_value='Docker Desktop.exe'), \
                patch.object(ds.subprocess, 'Popen'):
            ds.ensure_docker(log, timeout=0)
        self.assertIn('ainda indisponível', log.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
