import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import outcome, task_plan
from core.routines import Routines
from core import routines
from core.action_loader import ActionRegistry, _validate
from actions import routine_control, open_app


class RoutineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plans = task_plan.TaskPlans(self.root / 'plans.db')
        self.store = Routines(self.root / 'routines.db', plans=self.plans)
        self.steps = [{'kind': 'open_app', 'value': name} for name in ('Discord', 'Visual Studio Code', 'Chrome')]

    def save(self):
        return self.store.save('Começar meu trabalho', self.steps)

    def test_save_and_reopen_do_not_start_a_plan(self):
        saved = self.save()
        self.assertIsNone(self.plans.read())
        self.assertEqual(Routines(self.root / 'routines.db').show('comecar meu trabalho'), saved)
        self.assertEqual(saved['steps'], self.steps)

    def test_case_accents_and_spaces_match_one_routine(self):
        saved = self.save()
        self.assertEqual(self.store.show('  COMEÇAR   MEU trabalho '), saved)
        self.assertEqual(len(self.store.list()), 1)

    def test_stale_save_preserves_configuration(self):
        saved = self.save()
        with self.assertRaises(ValueError):
            self.store.save(saved['name'], self.steps[:2])
        self.assertEqual(self.store.show(saved['name']), saved)
        updated = self.store.save(saved['name'], self.steps[:2], revision=saved['revision'])
        self.assertEqual(updated['revision'], 2)

    def test_invalid_steps_urls_and_embedded_credentials_rejected(self):
        for invalid in [[], [{'kind': 'command', 'value': 'arbitrary shell'}] * 2,
                        [{'kind': 'open_app', 'value': ''}] * 2,
                        *[[{'kind': 'open_url', 'value': url}] * 2 for url in (
                            'javascript:alert(1)', 'file:///C:/Windows', 'https://user:secret@example.com', 'not a URL')]]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.store.save('Invalid routine', invalid)
        self.assertEqual(self.store.list(), [])

    def test_start_creates_exact_ordered_plan_with_immutable_snapshot(self):
        saved = self.save()
        plan = self.store.start(saved['name'])
        self.assertEqual(plan['routine'], saved)
        self.assertEqual([step['state'] for step in plan['steps']], ['pending'] * 3)
        self.assertIn('Discord', plan['steps'][0]['title'])
        self.store.save(saved['name'], self.steps[:2], revision=saved['revision'])
        self.assertEqual(self.plans.read()['routine'], saved)

    def test_start_cannot_replace_a_running_or_paused_plan(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        with self.assertRaises(ValueError):
            self.store.start('Começar meu trabalho')
        self.plans.update({'action': 'pause', 'plan_id': plan['id'], 'revision': plan['revision'], 'reason': 'User pause'})
        with self.assertRaises(ValueError):
            self.store.start('Começar meu trabalho')

    def test_unknown_routine_does_not_create_plan(self):
        with self.assertRaises(ValueError):
            self.store.start('Unknown')
        self.assertIsNone(self.plans.read())

    def test_start_tool_does_not_claim_the_apps_have_opened(self):
        self.save()
        with patch.object(routine_control, 'Routines', return_value=self.store):
            reply = routine_control.routine_control({'action': 'start', 'name': 'Começar meu trabalho'})
        self.assertIn('has NOT executed yet', reply)
        self.assertIn('routine_control next', reply)
        self.assertIn('routine_configuration_or_plan_only', reply)

    def test_app_and_page_routine_supports_full_urls(self):
        steps = [self.steps[0], {'kind': 'open_url', 'value': 'https://example.com/work'}]
        self.store.save('Work pages', steps)
        plan = self.store.start('Work pages')
        self.assertEqual(plan['routine']['steps'], steps)

    def test_real_registry_receipts_complete_all_three_mocked_apps(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        record = _validate(open_app, 'open_app.py')
        registry = ActionRegistry({'open_app': record}, logger=lambda message: None)
        with patch.object(task_plan, '_path', return_value=self.plans.path), \
                patch.object(open_app.appidentity, 'running', return_value=[]), \
                patch.object(open_app.appidentity, 'snapshot', return_value=set()), \
                patch.object(open_app, '_launch_and_verify', side_effect=lambda player, spoken, *args:
                             outcome.done('open_app', app=spoken, focused=True, verified=True)) as launch:
            for step in self.steps:
                result = registry.run('open_app', {'app_name': step['value'], 'wait_until_ready': True})
                receipt = re.search(r'task_receipt=([a-f0-9]+)', result)[1]
                plan = self.plans.update({'action': 'complete_step', 'plan_id': plan['id'], 'revision': plan['revision'],
                    'receipt_id': receipt, 'evidence': f"Verified application window: {step['value']}"})
        self.assertEqual([call.args[1] for call in launch.call_args_list], [s['value'] for s in self.steps])
        self.assertEqual(plan['state'], 'completed')

    def test_next_executes_one_saved_app_and_records_progress(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        with patch.object(open_app, 'open_app', return_value=outcome.done('open_app', focused=True)) as launch:
            after, result = self.store.next(plan['id'], plan['revision'])
        launch.assert_called_once_with({'app_name': 'Discord', 'wait_until_ready': True}, player=None)
        self.assertEqual(after['steps'][0]['state'], 'done')
        self.assertEqual(after['steps'][1]['state'], 'pending')

    def test_next_blocks_on_unverified_app_and_does_not_advance(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        with patch.object(open_app, 'open_app', return_value=outcome.unverified('open_app', 'No window')) as launch:
            after, result = self.store.next(plan['id'], plan['revision'])
            with self.assertRaises(ValueError):
                self.store.next(after['id'], after['revision'])
        self.assertEqual(after['state'], 'blocked')
        self.assertTrue(all(step['state'] == 'pending' for step in after['steps']))
        self.assertEqual(launch.call_count, 1)

    def test_interrupt_during_launch_keeps_plan_paused_and_does_not_record_success(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        def launch(*args, **kwargs):
            routines.pause_running_routine()
            return outcome.done('open_app', focused=True)
        with patch.object(task_plan, '_path', return_value=self.plans.path), patch.object(open_app, 'open_app', side_effect=launch):
            after, result = self.store.next(plan['id'], plan['revision'])
        self.assertEqual(after['state'], 'paused')
        self.assertEqual(after['steps'][0]['state'], 'pending')
        self.assertIn('status=unverified', result)

    def test_next_cannot_execute_stale_plan_or_concurrent_step(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        with patch.object(open_app, 'open_app') as launch:
            with self.assertRaises(ValueError):
                self.store.next(plan['id'], plan['revision'] + 1)
            routines._execution_lock.acquire()
            try:
                with self.assertRaises(ValueError):
                    self.store.next(plan['id'], plan['revision'])
            finally:
                routines._execution_lock.release()
            launch.assert_not_called()

    def test_next_complete_sequence_and_rejects_repeat_after_completion(self):
        self.save()
        plan = self.store.start('Começar meu trabalho')
        with patch.object(open_app, 'open_app', return_value=outcome.done('open_app', focused=True)) as launch:
            for index in range(3):
                plan, _ = self.store.next(plan['id'], plan['revision'])
            self.assertEqual(plan['state'], 'completed')
            with self.assertRaises(ValueError):
                self.store.next(plan['id'], plan['revision'])
        self.assertEqual(launch.call_count, 3)


class SynchronousAppLaunchTests(unittest.TestCase):
    def test_wait_flag_returns_verified_result_without_background_thread(self):
        with patch.object(open_app.appidentity, 'running', return_value=[]), \
                patch.object(open_app.appidentity, 'snapshot', return_value=set()), \
                patch.object(open_app, '_launch_and_verify', return_value='status=done action=open_app') as verify, \
                patch.object(open_app.threading, 'Thread') as thread:
            result = open_app.open_app({'app_name': 'Discord', 'wait_until_ready': True})
        self.assertIn('status=done', result)
        verify.assert_called_once()
        thread.assert_not_called()

    def test_process_without_focusable_window_is_unverified(self):
        with patch.object(open_app, '_open_visible_app', return_value=None), \
                patch.dict(open_app._LAUNCHERS, {open_app._SYSTEM: lambda name: True}), \
                patch.object(open_app.appidentity, 'wait_for_launch', return_value=SimpleNamespace(label='Discord')), \
                patch.object(open_app.appidentity, 'focus', return_value=False):
            result = open_app._launch_and_verify(None, 'Discord', 'Discord', set())
        self.assertIn('status=unverified', result)

    def test_visible_icon_with_confirmed_window_returns_done(self):
        with patch.object(open_app, '_open_visible_app', return_value=SimpleNamespace(label='Discord')):
            result = open_app._launch_and_verify(None, 'Discord', 'Discord', set())
        self.assertIn('status=done', result)

    def test_failed_launch_never_reports_done(self):
        with patch.object(open_app, '_open_visible_app', return_value=None), \
                patch.dict(open_app._LAUNCHERS, {open_app._SYSTEM: lambda name: False}), \
                patch.object(open_app.appidentity, 'wait_for_launch', return_value=None):
            result = open_app._launch_and_verify(None, 'Unknown', 'Unknown', set())
        self.assertIn('status=unverified', result)


if __name__ == '__main__':
    unittest.main()
