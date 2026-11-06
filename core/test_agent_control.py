import unittest
from unittest.mock import Mock, patch

from actions import agent_control as control
from core.action_loader import _validate


def view(**changes):
    result = dict(engine='codex', conversation='Fix appointment', pending=False, request='',
                  busy=False, draft='', input_label='Ask for changes', input_focused=True,
                  send_label='Send', approve_label='', reject_label='')
    result.update(changes)
    return result


class AgentControlTests(unittest.TestCase):
    def setUp(self):
        control._observations.clear()
        self.ui = Mock()
        self.ui.windows.return_value = [{'id': '42', 'title': 'project - Visual Studio Code'}]
        self.ui.observe.return_value = view()
        patcher = patch.object(control, 'AgentUI', return_value=self.ui)
        patcher.start()
        self.addCleanup(patcher.stop)

    def inspect(self, initial=None):
        if initial:
            self.ui.observe.return_value = initial
        result = control.agent_control({'action': 'inspect', 'engine': 'codex', 'window_id': '42'})
        self.assertIn('status=done', result)
        return next(iter(control._observations))

    def act(self, token, action='continue', **params):
        return control.agent_control(dict(action=action, engine='codex', observation_id=token, **params))

    def test_registration_and_continue_existing_conversation(self):
        self.assertTrue(_validate(control, 'agent_control.py').valid)
        token = self.inspect()
        self.ui.observe.side_effect = [view(), view(), view(draft='Pode continuar.'), view(busy=True)]
        result = self.act(token)
        self.assertIn('status=done', result)
        self.ui.type_message.assert_called_once_with('42', 'Pode continuar.')
        self.assertEqual(self.ui.click.call_count, 2)
        self.assertIn('status=failed', self.act(token))

    def test_ambiguous_window_no_focus(self):
        self.ui.windows.return_value *= 2
        result = control.agent_control({'action': 'inspect', 'engine': 'codex'})
        self.assertIn('status=failed', result)
        self.ui.focus.assert_not_called()

    def test_stale_wrong_engine_or_changed_conversation_never_send(self):
        token = self.inspect()
        self.ui.observe.return_value = view(conversation='Different task')
        self.assertIn('status=failed', self.act(token))
        self.ui.type_message.assert_not_called()
        self.ui.click.assert_not_called()

    def test_draft_busy_or_permission_blocks_continue(self):
        for change in (dict(draft='unsent draft'), dict(busy=True), dict(pending=True, request='run tests')):
            with self.subTest(change=change):
                self.ui.observe.side_effect = None
                token = self.inspect(view(**change))
                self.assertIn('status=failed', self.act(token))
                self.ui.type_message.assert_not_called()

    def test_one_time_permission_and_changed_request(self):
        pending = view(pending=True, request='python -m unittest', approve_label='Allow once', reject_label='Deny')
        token = self.inspect(pending)
        self.ui.observe.side_effect = [pending, view(busy=True)]
        self.assertIn('status=done', self.act(token, 'approve'))
        self.ui.click.assert_called_once_with('42', 'codex', 'Allow once', 'current permission dialog button')
        self.ui.observe.side_effect = None
        token = self.inspect(pending)
        self.ui.observe.return_value = view(pending=True, request='different command', approve_label='Allow once')
        self.assertIn('status=failed', self.act(token, 'approve'))
        self.assertEqual(self.ui.click.call_count, 1)

    def test_no_broad_approval_or_empty_permission(self):
        for label in ('Always allow', 'Allow for this session', 'Permitir sempre', ''):
            token = self.inspect(view(pending=True, request='test', approve_label=label))
            self.assertIn('status=failed', self.act(token, 'approve'))
        self.ui.click.assert_not_called()

    def test_unverified_paste_no_send_or_retry(self):
        token = self.inspect()
        self.ui.observe.side_effect = [view(), view(), view(draft='wrong')]
        self.assertIn('status=unverified', self.act(token, 'send', text='Run tests'))
        self.assertEqual(self.ui.click.call_count, 1)
        self.assertIn('status=failed', self.act(token, 'send', text='Run tests'))

    def test_unknown_outcome_after_click_is_unverified(self):
        pending = view(pending=True, request='test', approve_label='Allow once')
        token = self.inspect(pending)
        self.ui.click.side_effect = RuntimeError('focus changed after click')
        self.assertIn('status=unverified', self.act(token, 'approve'))

    def test_expired_token(self):
        token = self.inspect()
        with patch.object(control.time, 'monotonic', return_value=10**12):
            self.assertIn('status=failed', self.act(token))
        self.ui.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
