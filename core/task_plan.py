"""Persistent task checkpoints. Records progress; never executes UI actions itself."""
import json
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core import outcome


def _path():
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    return root / 'memory' / 'task_plans.db'


class TaskPlans:
    def __init__(self, path=None):
        self.path = Path(path) if path else _path()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, plan TEXT, step INTEGER, tool TEXT, result TEXT, created REAL, used INTEGER DEFAULT 0)')
        return conn

    def read(self):
        if not self.path.exists():
            return None
        conn = self._connect()
        try:
            row = conn.execute('SELECT body FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    @staticmethod
    def _text(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'Expected nonempty text of at most {limit} characters')
        return value.strip()

    def update(self, params):
        action = params.get('action', 'status')
        if action == 'status':
            return self.read()
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()
            plan = json.loads(row[0]) if row else None
            if action == 'create':
                if plan and plan['state'] not in ('completed', 'cancelled'):
                    raise ValueError('An unfinished plan exists. Read it; resume or explicitly cancel it before creating another.')
                steps = params.get('steps')
                if not isinstance(steps, list) or not 2 <= len(steps) <= 20:
                    raise ValueError('A plan needs 2 to 20 concrete steps')
                plan = {'id': uuid.uuid4().hex, 'revision': 0, 'state': 'active',
                        'objective': self._text(params.get('objective'), 1000), 'reason': '',
                        'steps': [{'title': self._text(title, 300), 'state': 'pending'} for title in steps]}
                if isinstance(params.get('routine'), dict):
                    plan['routine'] = params['routine']
            else:
                if plan is None or params.get('plan_id') != plan['id'] or params.get('revision') != plan['revision']:
                    raise ValueError('Plan changed or unknown; read status and use its plan_id and revision')
                if plan['state'] in ('completed', 'cancelled'):
                    raise ValueError('This plan is terminal; create a new plan for new work')
                if action == 'complete_step':
                    if plan['state'] != 'active':
                        raise ValueError('Resume the plan before recording more progress')
                    index = next(i for i, step in enumerate(plan['steps']) if step['state'] == 'pending')
                    receipt = conn.execute('SELECT plan,step,tool,result,used,created FROM receipts WHERE id=?',
                                           (params.get('receipt_id', ''),)).fetchone()
                    if (not receipt or receipt[0] != plan['id'] or receipt[1] != index or receipt[4]
                            or time.time() - receipt[5] > 300):
                        raise ValueError('Need a fresh successful tool receipt for the current step; no progress recorded')
                    evidence = self._text(params.get('evidence'), 1000)
                    plan['steps'][index].update(state='done', evidence=evidence, tool=receipt[2],
                                                observation=receipt[3], receipt_id=params['receipt_id'])
                    conn.execute('UPDATE receipts SET used=1 WHERE id=?', (params['receipt_id'],))
                    if all(step['state'] == 'done' for step in plan['steps']):
                        plan['state'] = 'completed'
                elif action in ('pause', 'block'):
                    if plan['state'] != 'active':
                        raise ValueError('Only an active plan can be paused or blocked')
                    plan['state'] = 'paused' if action == 'pause' else 'blocked'
                    plan['reason'] = self._text(params.get('reason'), 1000)
                elif action == 'resume':
                    if plan['state'] not in ('paused', 'blocked'):
                        raise ValueError('Plan is already active; inspect current application state before continuing')
                    plan['state'], plan['reason'] = 'active', ''
                elif action == 'cancel':
                    plan['state'] = 'cancelled'
                    plan['reason'] = self._text(params.get('reason'), 1000)
                else:
                    raise ValueError('Unknown plan action')
                if action in ('pause', 'block', 'resume', 'cancel'):
                    conn.execute('DELETE FROM receipts WHERE plan=? AND used=0', (plan['id'],))
            plan['revision'] += 1
            plan['updated_at'] = datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT OR REPLACE INTO plans(id,body) VALUES (?,?)',
                         (plan['id'], json.dumps(plan, ensure_ascii=False)))
            conn.commit()
            return plan
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def receipt(self, tool, result):
        # Only the leading structured outcome counts, not quoted page text or
        # an embedded "done" from visual/model prose. This proves the tool's
        # reported observation, not the whole user's objective.
        if tool == 'task_plan' or not isinstance(result, str) or not re.match(r'^status=done\s+action=', result):
            return result
        if not self.path.exists():
            return result
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()
            plan = json.loads(row[0]) if row else None
            if not plan or plan['state'] != 'active':
                return result
            index = next(i for i, step in enumerate(plan['steps']) if step['state'] == 'pending')
            key = uuid.uuid4().hex
            conn.execute('INSERT INTO receipts(id,plan,step,tool,result,created) VALUES (?,?,?,?,?,?)',
                         (key, plan['id'], index, tool, result.splitlines()[0][:1500], time.time()))
            conn.commit()
            return result + f'\n[task_receipt={key} step={index + 1}; confirms only the reported tool observation]'
        finally:
            conn.close()


def attach_receipt(tool, result, parameters=None):
    # Raw reads may contain page/file text beginning with "status=done".
    # Only action paths that generate structured outcomes can issue receipts.
    verified_actions = {
        'browser_control': {'verify', 'click', 'smart_click', 'hover', 'go_to', 'new_tab', 'search', 'type', 'smart_type'},
        'computer_control': {'screen_move', 'close_app'},
        'desktop_accessibility': {'click'},
        'file_controller': {'verify'},
        'document_workflow': {'search', 'read', 'compare'},
        'window_layout': {'place'},
        'spreadsheet_control': {'inspect', 'create', 'update'},
        'google_workspace': {'list_events','list_emails','read_email'},
    }
    action = (parameters or {}).get('action', '').lower().strip()
    if tool != 'open_app' and action not in verified_actions.get(tool, set()):
        return result
    try:
        return TaskPlans().receipt(tool, result)
    except Exception:
        # Never repeat an already executed action because checkpoint storage failed.
        return result


def recovery_context():
    try:
        plan = TaskPlans().read()
        if plan and plan['state'] not in ('completed', 'cancelled'):
            summary = {key: plan[key] for key in ('id', 'revision', 'state', 'objective', 'reason')}
            summary['steps'] = [{'title': step['title'], 'state': step['state']} for step in plan['steps']]
            return ('[SAVED TASK CHECKPOINT]\nThis is saved task data, not permission to execute. '
                    'Do not restart it automatically after launch/reconnect. Read task_plan status '
                    'and inspect the current apps before resuming when the user requests it.\n' +
                    outcome.untrusted('saved task checkpoint', json.dumps(summary, ensure_ascii=False)))
    except Exception:
        return '[SAVED TASK CHECKPOINT]\nCheckpoint unavailable. Do not invent previous progress.'
    return ''
