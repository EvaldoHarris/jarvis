"""Regression coverage for named visual targets, without real clicks/API calls."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from actions import computer_control as control
from core import gemini


class ScreenFindTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.mouse = Mock()
        self.mouse.screenshot.return_value = Image.new("RGB", (2000, 1000))
        self.mouse.size.return_value = (1000, 500)
        self.capture = stack.enter_context(patch.object(control, "capture_desktop",
            return_value=(Image.new("RGB", (2000, 1000)), 0, 0)))
        stack.enter_context(patch.object(control, "point_on_desktop", return_value=True))
        stack.enter_context(patch.object(control, "pyautogui", self.mouse))
        stack.enter_context(patch.object(control, "_PYAUTOGUI", True))
        stack.enter_context(patch.object(control, "_get_api_key", return_value="test"))
        self.accessible = stack.enter_context(patch.object(control, "_accessible_find", return_value=None))
        self.call = stack.enter_context(patch.object(gemini, "call"))

    def responses(self, box, check="MATCH"):
        self.call.side_effect = [SimpleNamespace(text=box), SimpleNamespace(text=check)]

    def test_normalized_box_maps_to_capture_pixels(self):
        self.responses('{"box": [100, 400, 300, 500]}')
        self.assertEqual(control._screen_find("GOTAB"), (400, 450))
        self.assertEqual(self.capture.call_count, 2)

    def test_monitor_left_of_primary_uses_negative_coordinates(self):
        self.capture.return_value = (Image.new("RGB", (2000, 1000)), -1000, -200)
        self.responses('{"box": [100, 400, 300, 500]}')
        self.assertEqual(control._screen_find("GOTAB"), (-600, 250))

    def test_monitor_right_of_primary_not_scaled_into_primary(self):
        self.responses('{"box": [700, 400, 900, 500]}')
        self.assertEqual(control._screen_find("GOTAB"), (1600, 450))

    def test_changed_target_region_rejected_without_click(self):
        self.responses('{"box": [100, 400, 300, 500]}')
        self.capture.side_effect = [(Image.new("RGB", (2000, 1000)), 0, 0),
                                   (Image.new("RGB", (2000, 1000), "white"), 0, 0)]
        result = control.computer_control({"action": "screen_click", "description": "GOTAB"})
        self.assertIn("not found", result)
        self.mouse.click.assert_not_called()

    def test_missing_ambiguous_and_invalid_boxes_rejected(self):
        for box in ('{"box": null}', '{"box": [-1, 0, 10, 10]}',
                    '{"box": [100, 500, 300, 400]}', '100,450'):
            with self.subTest(box=box):
                self.responses(box)
                self.assertIsNone(control._screen_find("GOTAB"))

    def test_verified_target_clicked(self):
        self.responses('{"box": [100, 400, 300, 500]}')
        control.computer_control({"action": "screen_click", "description": "GOTAB"})
        self.mouse.click.assert_called_once_with(400, 450, button="left", clicks=1)
        self.assertEqual(self.call.call_count, 1)

    def test_accessible_target_skips_model(self):
        self.accessible.return_value = (200, 225)
        control.computer_control({"action": "screen_click", "target": "GOTAB",
                                  "description": "WhatsApp group GOTAB"})
        self.accessible.assert_called_once_with("GOTAB")
        self.call.assert_not_called()
        self.mouse.click.assert_called_once_with(200, 225, button="left", clicks=1)

    def test_accessibility_matches_name_without_substituting_contact(self):
        def item(label, top):
            return SimpleNamespace(window_text=lambda: label, is_visible=lambda: True,
                                   is_enabled=lambda: True, rectangle=lambda: SimpleNamespace(
                                       left=80, right=350, top=top, bottom=top + 40))
        controls = [item("Mãe", 280), item("GOTAB Airsoft team It...", 430)]
        self.assertEqual(control._accessible_matches(controls, "GOTAB"), {(80, 430, 350, 470)})
        self.assertEqual(control._accessible_matches(controls, "GOTA"), set())
        controls.append(item("GOTAB Outro", 520))
        self.assertEqual(len(control._accessible_matches(controls, "GOTAB")), 2)


if __name__ == "__main__":
    unittest.main()
