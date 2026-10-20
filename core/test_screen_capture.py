import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.screen_capture import capture_desktop, point_on_desktop
from actions import screen_processor


class DesktopCaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = MagicMock()
        self.capture.monitors = [
            dict(left=-2, top=0, width=4, height=2),
            dict(left=0, top=0, width=2, height=2),
            dict(left=-2, top=0, width=2, height=1),
        ]
        self.capture.grab.return_value = SimpleNamespace(size=(4, 2), rgb=bytes(24))
        context = MagicMock()
        context.__enter__.return_value = self.capture
        self.patch = patch("mss.mss", return_value=context)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_capture_includes_all_screens_and_origin(self):
        image, left, top = capture_desktop()
        self.assertEqual((image.size, left, top), ((4, 2), -2, 0))
        self.capture.grab.assert_called_once_with(self.capture.monitors[0])

    def test_negative_coordinates_allowed_but_monitor_gap_rejected(self):
        self.assertTrue(point_on_desktop(-1, 0))
        self.assertTrue(point_on_desktop(1, 1))
        self.assertFalse(point_on_desktop(-1, 1))
        self.assertFalse(point_on_desktop(2, 0))

    def test_conversation_capture_uses_virtual_desktop(self):
        with patch.object(screen_processor, "_MSS", True), \
                patch.object(screen_processor, "_compress", return_value=(b"image", "image/jpeg")) as compress:
            self.assertEqual(screen_processor._capture_screen(), (b"image", "image/jpeg"))
        self.capture.grab.assert_called_once_with(self.capture.monitors[0])
        self.assertEqual(compress.call_args.kwargs["max_size"], (2560, 1440))


if __name__ == "__main__":
    unittest.main()
