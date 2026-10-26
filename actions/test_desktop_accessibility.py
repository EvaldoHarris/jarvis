import unittest
from unittest.mock import patch

from actions import desktop_accessibility as desktop


class DesktopAccessibilityTests(unittest.TestCase):
    def setUp(self):
        desktop._snapshot = None
        self.row = {"name": "GOTAB", "role": "ListItem", "identity": (1, 2), "bounds": (20, 40, 100, 80)}
        self.read = patch.object(desktop, "_read", return_value=(7, "WhatsApp", [self.row])).start()
        patch.object(desktop, "_foreground", return_value=(7, None)).start()
        self.click = patch("actions.computer_control._click").start()
        self.addCleanup(patch.stopall)

    def observe(self):
        desktop.desktop_accessibility({"action": "inspect"})
        return next(iter(desktop._snapshot[2]))

    def test_click_uses_observed_rectangle_and_is_single_use(self):
        key = self.observe()
        result = desktop.desktop_accessibility({"action": "click", "element_id": key})
        self.click.assert_called_once_with(60, 60)
        self.assertIn("status=unverified", result)
        result = desktop.desktop_accessibility({"action": "click", "element_id": key})
        self.assertIn("status=failed", result)
        self.assertEqual(self.click.call_count, 1)

    def test_changed_focus_or_geometry_never_clicks(self):
        for value in [(8, "Other", [self.row]), (7, "WhatsApp", [{**self.row, "bounds": (0, 0, 20, 20)}])]:
            with self.subTest(value=value):
                self.read.return_value = (7, "WhatsApp", [self.row])
                key = self.observe()
                self.read.return_value = value
                self.assertIn("status=failed", desktop.desktop_accessibility({"action": "click", "element_id": key}))
                self.click.assert_not_called()

    def test_duplicate_contact_names_use_the_selected_observed_row(self):
        second = {**self.row, "name": "Luiz G", "identity": (2, 3), "bounds": (20, 140, 100, 180)}
        self.read.return_value = (7, "WhatsApp", [{**self.row, "name": "Luiz G"}, second])
        self.observe()
        key = list(desktop._snapshot[2])[1]
        result = desktop.desktop_accessibility({"action": "click", "element_id": key})
        self.click.assert_called_once_with(60, 160)
        self.assertIn("status=unverified", result)

    def test_expired_target_does_not_click(self):
        key = self.observe()
        handle, _, targets = desktop._snapshot
        desktop._snapshot = (handle, -100, targets)
        self.assertIn("status=failed", desktop.desktop_accessibility({"action": "click", "element_id": key}))
        self.click.assert_not_called()

    def test_new_expected_label_confirms_only_observed_evidence(self):
        key = self.observe()
        self.read.side_effect = [(7, "WhatsApp", [self.row]),
                                 (7, "WhatsApp", [self.row, {**self.row, "name": "Conversa GOTAB"}])]
        result = desktop.desktop_accessibility({"action": "click", "element_id": key, "expected_text": "Conversa GOTAB"})
        self.assertIn("status=done", result)
        self.assertIn("verified_label=", result)

    def test_existing_label_is_not_evidence_of_click_success(self):
        key = self.observe()
        with patch.object(desktop.time, "monotonic", side_effect=[1, 1, 4]):
            handle, _, targets = desktop._snapshot
            desktop._snapshot = (handle, 0, targets)
            result = desktop.desktop_accessibility({"action": "click", "element_id": key, "expected_text": "GOTAB"})
        self.assertIn("status=unverified", result)
        self.click.assert_called_once()

    def test_fail_safe_is_never_bypassed(self):
        key = self.observe()
        self.click.side_effect = type("FailSafeException", (Exception,), {})()
        result = desktop.desktop_accessibility({"action": "click", "element_id": key})
        self.assertIn("requires_user=true", result)
        self.assertIn("retry_allowed=false", result)


if __name__ == "__main__":
    unittest.main()
