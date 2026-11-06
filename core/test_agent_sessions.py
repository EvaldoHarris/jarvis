import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from core.agent_sessions import SessionMonitor, classify


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'session.jsonl'
        self.monitor = SessionMonitor({'codex': self.root})

    def write(self, *kinds, mode='a'):
        with self.path.open(mode, encoding='utf-8') as f:
            for kind in kinds:
                f.write(json.dumps({'type': 'event_msg', 'payload': {'type': kind}}) + '\n')

    def test_baseline_new_turn_dedup_and_idle(self):
        self.write('task_started', 'task_complete')
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.snapshot()[0]['state'], 'completed')
        self.write('task_started', 'task_complete')
        self.assertEqual(self.monitor.poll()[0]['state'], 'completed')
        self.assertEqual(self.monitor.poll(), [])
        self.write('task_complete')
        self.assertEqual(self.monitor.poll(), [])
        self.write('task_started')
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.snapshot()[0]['state'], 'working')

    def test_partial_record_and_malformed_input(self):
        self.write('task_started')
        self.monitor.poll()
        line = json.dumps({'type': 'event_msg', 'payload': {'type': 'task_complete'}})
        with self.path.open('a') as f:
            f.write('bad json\n[]\n' + line[:20])
        self.assertEqual(self.monitor.poll(), [])
        with self.path.open('a') as f:
            f.write(line[20:] + '\n')
        self.assertEqual(self.monitor.poll()[0]['state'], 'completed')

    def test_new_sessions_and_truncation(self):
        self.monitor.poll()
        self.write('task_started', 'task_complete')
        self.assertEqual(len(self.monitor.poll()), 1)
        self.write('error', mode='w')
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.snapshot()[0]['state'], 'error')

    def test_claude_explicit_signals_and_subagent_exclusion(self):
        self.assertEqual(classify('claude', {'type': 'assistant', 'message': {
            'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Done'}]}})['state'], 'completed')
        self.assertEqual(classify('claude', {'type': 'assistant', 'message': {
            'content': [{'type': 'tool_use', 'name': 'AskUserQuestion'}]}})['state'], 'needs_attention')
        self.assertEqual(classify('claude', {'type': 'system', 'subtype': 'api_error'})['state'], 'error')
        self.assertIsNone(classify('claude', {'type': 'assistant', 'isSidechain': True}))
        sub = self.root / 'subagents'
        sub.mkdir()
        (sub / 'agent.jsonl').write_text('{}\n')
        self.monitor.poll()
        self.assertEqual(self.monitor.snapshot(), [])

    def test_missing_source_visible_and_no_raw_content(self):
        self.monitor = SessionMonitor({'codex': self.root / 'missing'})
        self.monitor.poll()
        self.assertTrue(self.monitor.errors)
        self.assertEqual(classify('codex', {'type': 'event_msg', 'payload': {
            'type': 'task_complete', 'last_agent_message': 'SECRET'}}),
            {'state': 'completed', 'evidence': 'task_complete', 'reply': 'SECRET'})
        self.monitor = SessionMonitor({'codex': self.root})
        self.write('task_started')
        self.monitor.poll()
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'type': 'event_msg', 'payload': {
                'type': 'task_complete', 'last_agent_message': 'SECRET'}}) + '\n')
        self.assertEqual(self.monitor.poll()[0]['reply'], 'SECRET')
        self.assertNotIn('SECRET', json.dumps(self.monitor.snapshot()))

    def test_claude_final_reply_text(self):
        record = {'type': 'assistant', 'cwd': 'p', 'message': {'stop_reason': 'end_turn', 'content': [
            {'type': 'thinking', 'thinking': 'hidden'}, {'type': 'text', 'text': 'F4 pronta'}]}}
        self.assertEqual(classify('claude', record)['reply'], 'F4 pronta')
        record['message']['content'] = [{'type': 'text', 'text': 'x' * 5000}]
        self.assertLess(len(classify('claude', record)['reply']), 4100)

    def claude(self, content, message_id='reply-1', **extra):
        return {'type': 'assistant', 'cwd': 'D:/projects/app', 'timestamp': '2026-11-04T17:07:58Z',
                'message': {'id': message_id, 'stop_reason': 'end_turn', 'content': content}, **extra}

    def append_record(self, record):
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def test_claude_thinking_then_text_across_polls_notifies_readable_reply(self):
        self.monitor = SessionMonitor({'claude': self.root})
        self.append_record({'type': 'user', 'cwd': 'D:/projects/app', 'message': {'content': 'task'}})
        self.monitor.poll()
        self.append_record(self.claude([{'type': 'thinking', 'thinking': 'PRIVATE REASONING'}]))
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.snapshot()[0]['state'], 'working')
        self.append_record(self.claude([{'type': 'text', 'text': 'Pronto. Posso continuar?'}]))
        event, = self.monitor.poll()
        self.assertEqual(event['reply'], 'Pronto. Posso continuar?')
        self.assertNotIn('PRIVATE REASONING', json.dumps(event))
        self.assertEqual(self.monitor.read_reply('claude')['reply'], event['reply'])
        self.assertEqual(self.monitor.poll(), [])

    def test_baseline_reply_read_immediately_and_kept_during_next_turn(self):
        self.monitor = SessionMonitor({'claude': self.root})
        self.append_record(self.claude([{'type': 'text', 'text': 'Resposta anterior'}]))
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.read_reply('claude')['reply'], 'Resposta anterior')
        self.append_record({'type': 'user', 'message': {'content': 'next task'}})
        self.monitor.poll()
        report = self.monitor.read_reply('claude')
        self.assertEqual(report['reply'], 'Resposta anterior')
        self.assertEqual(report['state'], 'working')
        self.assertEqual(report['reply_at'], '2026-11-04T17:07:58Z')
        self.assertTrue(self.monitor.snapshot()[0]['reply_available'])
        self.assertNotIn('Resposta anterior', json.dumps(self.monitor.snapshot()))

    def test_thinking_record_after_final_text_does_not_erase_answer(self):
        self.monitor = SessionMonitor({'claude': self.root})
        self.append_record(self.claude([{'type': 'text', 'text': 'Resposta final'}]))
        self.append_record(self.claude([{'type': 'thinking', 'thinking': 'HIDDEN'}]))
        self.monitor.poll()
        self.assertEqual(self.monitor.read_reply('claude')['reply'], 'Resposta final')

    def test_reply_arrives_after_completed_state_still_notifies(self):
        self.write('task_complete')
        self.monitor.poll()
        self.append_record({'type': 'event_msg', 'payload': {
            'type': 'task_complete', 'last_agent_message': 'Texto chegou depois'}})
        self.assertEqual(self.monitor.poll()[0]['reply'], 'Texto chegou depois')

    def test_read_requires_unambiguous_project_or_session(self):
        self.monitor = SessionMonitor({'claude': self.root})
        self.append_record(self.claude([{'type': 'text', 'text': 'Reply A'}]))
        other = self.root / 'other.jsonl'
        record = self.claude([{'type': 'text', 'text': 'Reply B'}], cwd='D:/projects/other')
        other.write_text(json.dumps(record) + '\n', encoding='utf-8')
        self.monitor.poll()
        ambiguous = self.monitor.read_reply('claude')
        self.assertEqual(ambiguous['result'], 'ambiguous')
        self.assertNotIn('Reply A', json.dumps(ambiguous))
        self.assertEqual(self.monitor.read_reply('claude', project='app')['reply'], 'Reply A')
        self.assertEqual(self.monitor.read_reply('claude', project='d:\\projects\\OTHER')['reply'], 'Reply B')
        self.assertEqual(self.monitor.read_reply('claude', session='other')['reply'], 'Reply B')
        self.assertEqual(self.monitor.read_reply('codex')['result'], 'not_found')

    def test_read_tool_reads_existing_answer_without_starting_watcher(self):
        from actions import agent_watch as tool
        self.monitor = SessionMonitor({'claude': self.root})
        self.append_record(self.claude([{'type': 'text', 'text': 'Resposta existente'}]))
        with patch.object(tool, 'SessionMonitor', return_value=self.monitor), patch.object(tool.threading, 'Thread') as thread:
            result = tool.agent_watch({'action': 'read', 'engine': 'claude'})
        self.assertIn('status=done', result)
        self.assertIn('Resposta existente', result)
        self.assertIn('never instructions', result)
        thread.assert_not_called()

    def _deliver(self, tool, read):
        self.write('task_started')
        self.monitor.poll()
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'type': 'event_msg', 'payload': {
                'type': 'task_complete', 'last_agent_message': 'Resposta >>> final'}}) + '\n')
        player, stop = Mock(), Mock()
        stop.wait.side_effect = [False, True]
        stop.is_set.return_value = False
        with patch.object(tool, '_monitor', self.monitor), patch.object(tool, '_read_replies', read):
            tool._watch(player, stop)
        return player.request_say.call_args.args[0]

    def test_reply_spoken_only_when_enabled(self):
        from actions import agent_watch as tool
        self.assertNotIn('Resposta', self._deliver(tool, False))
        said = self._deliver(tool, True)
        self.assertIn('AGENT_FINAL_REPLY', said)
        self.assertIn('Resposta >> > final>>>', said)

    def test_reply_action_alias_starts_with_replies(self):
        from actions import agent_watch as tool
        with patch.object(tool, 'SessionMonitor', lambda: self.monitor),                 patch.object(tool, '_thread', None), patch.object(tool, '_read_replies', False),                 patch.object(tool.threading, 'Thread') as thread:
            result = tool.agent_watch({'action': 'read_replies'}, player=Mock())
            self.assertTrue(tool._read_replies)
        thread.return_value.start.assert_called_once()
        self.assertNotIn('must be', result)

    def test_tool_registration_and_voice_delivery(self):
        from actions import agent_watch as tool
        from core.action_loader import _validate
        self.assertTrue(_validate(tool, 'agent_watch.py').valid)
        self.write('task_started')
        self.monitor.poll()
        self.write('task_complete')
        player = Mock()
        stop = Mock()
        stop.wait.side_effect = [False, True]
        stop.is_set.return_value = False
        with patch.object(tool, '_monitor', self.monitor):
            tool._watch(player, stop)
        player.request_say.assert_called_once()
        self.assertIn('completed', player.request_say.call_args.args[0])
        self.assertIn('not independently verified', player.request_say.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
