"""Visual launch regression tests; never interact with the real desktop."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from actions import open_app as apps


class VisualLaunchTests(unittest.TestCase):
    def setUp(self):
        self.mouse = Mock()
        self.mouse.size.return_value = (1920, 1080)
        self.find = Mock()
        self.candidate = SimpleNamespace(label="Example")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(apps, "_PYAUTOGUI", True))
        self.stack.enter_context(patch.object(apps, "pyautogui", self.mouse))
        self.stack.enter_context(patch.object(apps, "point_on_desktop",
            side_effect=lambda x, y: -1920 <= x < 1920 and 0 <= y < 1080))
        self.stack.enter_context(patch.dict("sys.modules", {
            "actions.computer_control": SimpleNamespace(_screen_find=self.find)
        }))
        self.stack.enter_context(patch.object(apps.appidentity, "running",
                                             return_value=[self.candidate]))
        self.stack.enter_context(patch.object(apps.appidentity, "focus",
                                             return_value=True))

    def test_taskbar_click_and_confirmation(self):
        self.find.return_value = (100, 1000)
        self.assertIs(apps._open_visible_app("Example"), self.candidate)
        self.mouse.click.assert_called_once_with(100, 1000, clicks=1, interval=0.12)

    def test_desktop_requires_double_click(self):
        self.find.side_effect = [None, (100, 100)]
        self.assertIs(apps._open_visible_app("Example"), self.candidate)
        self.mouse.click.assert_called_once_with(100, 100, clicks=2, interval=0.12)

    def test_missing_or_invalid_target_never_clicks(self):
        self.find.side_effect = [(1920, 100), None]
        self.assertIsNone(apps._open_visible_app("Example"))
        self.mouse.click.assert_not_called()

    def test_vision_failure_allows_fallback(self):
        self.find.side_effect = RuntimeError("vision unavailable")
        self.assertIsNone(apps._open_visible_app("Example"))
        self.mouse.click.assert_not_called()

    def test_click_without_confirmed_window_is_not_success(self):
        self.find.return_value = (100, 1000)
        with patch.object(apps.time, "monotonic", side_effect=[0, 5]):
            self.assertIsNone(apps._open_visible_app("Example"))
        self.assertEqual(self.find.call_count, 1)

    def test_existing_window_does_not_need_vision(self):
        with patch.object(apps, "_open_visible_app") as visual:
            apps.open_app({"app_name": "Example"})
        visual.assert_not_called()
        self.mouse.click.assert_not_called()

    def test_verified_visual_launch_skips_launcher(self):
        launcher = Mock()
        with patch.object(apps, "_open_visible_app", return_value=self.candidate), \
                patch.dict(apps._LAUNCHERS, {apps._SYSTEM: launcher}):
            apps._launch_and_verify(None, "Example", "example", set())
        launcher.assert_not_called()

    def test_unverified_visual_launch_uses_launcher(self):
        launcher = Mock(return_value=True)
        with patch.object(apps, "_open_visible_app", return_value=None), \
                patch.dict(apps._LAUNCHERS, {apps._SYSTEM: launcher}), \
                patch.object(apps.appidentity, "wait_for_launch",
                             return_value=self.candidate):
            apps._launch_and_verify(None, "Example", "example", set())
        launcher.assert_called_once_with("example")


if __name__ == "__main__":
    unittest.main()
