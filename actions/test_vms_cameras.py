import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from PIL import Image
from actions import vms_cameras as vms
from core import gemini


class VmsTests(unittest.TestCase):
    def test_show_only_focuses_window_without_sending_image(self):
        with patch.object(vms, "_window", return_value=Mock()), patch.object(gemini, "call") as call:
            result = vms.vms_cameras({"action": "show"})
        self.assertIn('status=done', result)
        call.assert_not_called()

    def test_window_must_be_foreground_before_capture(self):
        window = SimpleNamespace(handle=123)
        with patch.object(vms, "_foreground_handle", return_value=456):
            with self.assertRaises(RuntimeError):
                vms._capture_window(window)

    def test_capture_is_limited_to_vms_even_on_negative_monitor(self):
        rect = SimpleNamespace(left=-1200, top=100, right=-200, bottom=900)
        window = Mock(handle=123)
        window.rectangle.return_value = rect
        capture = MagicMock()
        capture.monitors = [dict(left=-1920, top=0, width=3840, height=1080)]
        capture.grab.return_value = SimpleNamespace(size=(1000, 800), rgb=bytes(1000*800*3))
        context = MagicMock()
        context.__enter__.return_value = capture
        with patch("mss.mss", return_value=context), patch.object(vms, "_foreground_handle", return_value=123):
            image = vms._capture_window(window)
        capture.grab.assert_called_once_with(dict(left=-1200, top=100, width=1000, height=800))
        self.assertEqual(Image.open(io.BytesIO(image)).size, (1000, 732))

    def test_analysis_passes_only_captured_window_and_question(self):
        with patch.object(vms, "_window", return_value=Mock()), \
                patch.object(vms, "_capture_window", return_value=b"window image"), \
                patch.object(vms.time, "sleep"), \
                patch.object(gemini, "call", return_value=SimpleNamespace(text="Há um portão visível.")) as call:
            result = vms.vms_cameras({"action": "analyze", "camera": "Adelita", "question": "O portão está aberto?"})
        self.assertIn("portão", result)
        inputs = call.call_args.args[0]
        self.assertEqual(inputs[0].inline_data.data, b"window image")
        self.assertIn("Adelita", inputs[1])

    def test_offline_or_unavailable_window_returns_failure(self):
        with patch.object(vms, "_window", side_effect=RuntimeError("Abra o VMS")):
            result = vms.vms_cameras({"action": "analyze"})
        self.assertIn('status=failed', result)
        self.assertIn("Abra o VMS", result)

    def test_camera_selection_requires_name(self):
        with patch.object(vms, "_window") as window:
            result = vms.vms_cameras({"action": "select"})
        self.assertIn('status=failed', result)
        window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
