import io
import ast
from pathlib import Path
import struct
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from core.rtsp_live import LiveCamera, _read_exact
from plugins import cameras_locais


class LiveCameraTests(unittest.TestCase):
    def test_hud_rejects_stale_frames_after_close_or_channel_switch(self):
        tree = ast.parse(Path("ui.py").read_text(encoding="utf-8"))
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
        method = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == "_on_security_event")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "ui.py", "exec"), namespace)
        handle = namespace["_on_security_event"]
        ui = SimpleNamespace(_security_generation=3, _security_active=False,
                             _cam_stop=Mock(), _video_player=None, _cam_title=Mock(),
                             _hud_cam_stack=Mock(), _on_cam_frame=Mock(),
                             _on_cam_stream=Mock(), write_log=Mock())
        handle(ui, (2, "start", "old channel"))
        ui._hud_cam_stack.setCurrentIndex.assert_not_called()
        handle(ui, (4, "start", "DVR channel 4"))
        handle(ui, (4, "frame", b"live frame"))
        ui._on_cam_frame.assert_called_once_with(b"live frame")
        handle(ui, (3, "end", None))
        self.assertTrue(ui._security_active)
        handle(ui, (4, "end", None))
        self.assertFalse(ui._security_active)
        ui._on_cam_stream.assert_called_once_with(False)

    def test_partial_frames_are_reassembled_and_truncation_rejected(self):
        class Partial(io.BytesIO):
            def read(self, size):
                return super().read(min(size, 2))
        self.assertEqual(_read_exact(Partial(b"abcdef"), 6), b"abcdef")
        with self.assertRaises(EOFError):
            _read_exact(Partial(b"abc"), 6)

    def test_real_frame_required_and_credentials_not_in_process_arguments(self):
        live = LiveCamera()
        frame = b"\xff\xd8test-jpeg"
        process = Mock()
        process.stdin = io.BytesIO()
        process.stdout = io.BytesIO(struct.pack("!I", len(frame)) + frame)
        process.poll.return_value = None
        ended = threading.Event()
        events = []
        def emit(event):
            events.append(event)
            if event[1] == "end":
                ended.set()
        camera = dict(host="192.168.1.20", vendor="intelbras", username="test",
                      password="private-test-password", channel=3, name="DVR")
        with patch("core.rtsp_live.subprocess.Popen", return_value=process) as launch:
            live.start(camera, emit)
            self.assertTrue(ended.wait(2))
        self.assertEqual([e[1] for e in events], ["start", "frame", "end"])
        self.assertEqual(events[1][2], frame)
        self.assertNotIn(camera["password"], str(launch.call_args))
        process.kill.assert_called()

    def test_no_frame_never_reports_started(self):
        process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
        process.poll.return_value = None
        camera = dict(host="192.168.1.20", username="test", password="secret", channel=1, name="DVR")
        with patch("core.rtsp_live.subprocess.Popen", return_value=process):
            with self.assertRaises(RuntimeError):
                LiveCamera().start(camera, Mock())

    def test_offline_device_does_not_stop_existing_live_camera(self):
        live = LiveCamera()
        existing = Mock()
        existing.poll.return_value = None
        live._process = existing
        live._generation = 7
        failed = Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
        failed.poll.return_value = None
        camera = dict(host="192.168.1.20", username="test", password="secret", channel=1, name="Offline")
        with patch("core.rtsp_live.subprocess.Popen", return_value=failed):
            with self.assertRaises(RuntimeError):
                live.start(camera, Mock())
        self.assertIs(live._process, existing)
        self.assertEqual(live._generation, 7)
        existing.kill.assert_not_called()
        live.stop()

    def test_live_routes_selected_channel_without_snapshot_or_ai(self):
        camera = dict(name="DVR", host="192.168.1.20", channel=1, channel_count=8)
        player = Mock()
        with patch.object(cameras_locais, "_cameras", return_value=[camera]), \
                patch.object(cameras_locais, "snapshot") as snapshot:
            result = cameras_locais.run({"action": "live", "camera": "DVR", "channel": 4}, player)
        self.assertEqual(player.start_security_camera.call_args.args[0]["channel"], 4)
        snapshot.assert_not_called()
        self.assertIn("sent_to_ai=false", result)
        cameras_locais.run({"action": "stop"}, player)
        player.stop_security_camera.assert_called_once()


if __name__ == "__main__":
    unittest.main()
