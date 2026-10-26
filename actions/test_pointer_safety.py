"""Pointer regressions without moving or clicking the user's actual mouse."""
import unittest
from unittest.mock import Mock, patch
from actions import computer_control as control


class PointerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.mouse = Mock()
        self.mouse.FAILSAFE_POINTS = [(0, 0), (3439, 1439)]
        for item in (patch.object(control, 'pyautogui', self.mouse),
                     patch.object(control, '_PYAUTOGUI', True),
                     patch.object(control, 'point_on_desktop', return_value=True)):
            item.start(); self.addCleanup(item.stop)

    def test_missing_coordinates_never_move_to_origin(self):
        for args in ({'action': 'move'}, {'action': 'move', 'x': 639},
                     {'action': 'drag', 'x1': 200, 'y1': 300, 'x2': 639},
                     {'action': 'click', 'x': 639}):
            control.computer_control(args)
        self.mouse.moveTo.assert_not_called()
        self.mouse.click.assert_not_called()
        self.mouse.dragTo.assert_not_called()

    def test_corner_and_monitor_gap_rejected_before_mouse_moves(self):
        control.computer_control({'action': 'move', 'x': 0, 'y': 0})
        with patch.object(control, 'point_on_desktop', return_value=False):
            control.computer_control({'action': 'move', 'x': 4000, 'y': 100})
        self.mouse.moveTo.assert_not_called()

    def test_secondary_and_negative_coordinates_are_not_rescaled(self):
        control.computer_control({'action': 'move', 'x': 4000, 'y': 930})
        control.computer_control({'action': 'move', 'x': -600, 'y': 930})
        self.assertEqual(self.mouse.moveTo.call_args_list[0].args, (4000, 930))
        self.assertEqual(self.mouse.moveTo.call_args_list[1].args, (-600, 930))

    def test_active_fail_safe_stops_before_model_lookup_or_click(self):
        stopped = type('FailSafeException', (Exception,), {})
        self.mouse.failSafeCheck.side_effect = stopped('corner')
        with patch.object(control, '_screen_find') as vision, patch.object(control, '_accessible_find') as accessible:
            result = control.computer_control({'action': 'screen_click', 'description': 'Comentário'})
            self.assertIn('requires_user=true', result)
            self.assertIn('retry_allowed=false', result)
            vision.assert_not_called(); accessible.assert_not_called()
        self.mouse.click.assert_not_called()
        self.mouse.moveTo.assert_not_called()

    def test_reported_target_is_not_treated_as_a_corner(self):
        control.computer_control({'action': 'move', 'x': 639, 'y': 930})
        self.mouse.moveTo.assert_called_once_with(639, 930, duration=0.3)


if __name__ == '__main__':
    unittest.main()
