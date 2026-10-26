"""Reusable user-defined app/page sequences, instantiated as task checkpoints."""
import json
import sqlite3
import threading
import re
import unicodedata
from urllib.parse import urlsplit

from core.task_plan import TaskPlans, _path

_execution_lock = threading.Lock()


def routine_path():
    return _path().with_name('routines.db')


def name_key(name):
    name = TaskPlans._text(name, 100)
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', name.casefold())
                           if not unicodedata.combining(c)).split())


class Routines:
    def __init__(self, path=None, plans=None):
        self.path = path or routine_path()
        self.plans = plans or TaskPlans()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute('CREATE TABLE IF NOT EXISTS routines (key TEXT PRIMARY KEY, body TEXT NOT NULL)')
        return conn

    def list(self):
        if not self.path.exists():
            return []
        conn = self._connect()
        try:
            return [json.loads(row[0]) for row in conn.execute('SELECT body FROM routines ORDER BY key')]
        finally:
            conn.close()

    def show(self, name):
        key = name_key(name)
        return next((item for item in self.list() if name_key(item['name']) == key), None)

    def save(self, name, steps, revision=0):
        key = name_key(name)
        if not isinstance(steps, list) or not 2 <= len(steps) <= 20:
            raise ValueError('A routine needs 2 to 20 app/page steps')
        validated = []
        for step in steps:
            if not isinstance(step, dict) or step.get('kind') not in ('open_app', 'open_url'):
                raise ValueError('Supported kinds: open_app, open_url')
            value = TaskPlans._text(step.get('value'), 2000 if step['kind'] == 'open_url' else 100)
            if step['kind'] == 'open_url':
                url = urlsplit(value)
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                    raise ValueError('Use a full http/https page address without embedded credentials')
            validated.append({'kind': step['kind'], 'value': value})
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM routines WHERE key=?', (key,)).fetchone()
            current = json.loads(row[0]) if row else None
            if type(revision) is not int or revision != (current['revision'] if current else 0):
                raise ValueError('Routine changed; show it and use the current revision before saving')
            routine = {'name': name.strip(), 'revision': revision + 1, 'steps': validated}
            conn.execute('INSERT OR REPLACE INTO routines(key,body) VALUES (?,?)', (key, json.dumps(routine, ensure_ascii=False)))
            conn.commit()
            return routine
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def start(self, name):
        routine = self.show(name)
        if routine is None:
            raise ValueError('Routine not configured. Ask which apps/pages the user wants, then save it.')
        titles = []
        for step in routine['steps']:
            if step['kind'] == 'open_app':
                titles.append(f"Abrir e confirmar janela: {step['value']}")
            else:
                titles.append(f"Abrir e conferir pagina: {step['value']}"[:300])
        # create is atomic and refuses to replace an unfinished task. The saved
        # sequence is copied so later edits do not change a running routine.
        return self.plans.update({'action': 'create', 'objective': f"Executar rotina: {routine['name']}",
                                  'steps': titles, 'routine': routine})

    def next(self, plan_id, revision, player=None):
        """Execute exactly the next saved step; never a model-invented command."""
        from core import outcome
        if not _execution_lock.acquire(blocking=False):
            raise ValueError('A routine step is already executing. Read status; do not repeat.')
        try:
            plan = self.plans.read()
            if (not plan or plan['id'] != plan_id or plan['revision'] != revision
                    or plan['state'] != 'active' or not plan.get('routine')):
                raise ValueError('Routine is stale, paused, blocked or terminal; read task_plan status')
            index = next(i for i, step in enumerate(plan['steps']) if step['state'] == 'pending')
            step = plan['routine']['steps'][index]
            if step['kind'] == 'open_app':
                from actions.open_app import open_app
                tool = 'open_app'
                result = open_app({'app_name': step['value'], 'wait_until_ready': True}, player=player)
            elif step['kind'] == 'open_url':
                from actions.browser_control import browser_control
                tool = 'browser_control'
                result = browser_control({'action': 'go_to', 'url': step['value']}, player=player)
            else:
                raise ValueError('Unsupported saved step; no action sent')
            # A pause/cancel may arrive while this one action is in flight.
            current = self.plans.read()
            if current['id'] != plan_id or current['revision'] != revision or current['state'] != 'active':
                return current, outcome.unverified('routine_step',
                    'Routine changed/interrupted while this action was running. The action may have happened; inspect before resuming. No further step executed.',
                    retry_allowed=False)
            if not result.startswith('status=done '):
                blocked = self.plans.update({'action': 'block', 'plan_id': plan_id, 'revision': revision,
                    'reason': ('Step result not confirmed: ' + result.splitlines()[0])[:1000]})
                return blocked, result
            receipt = self.plans.receipt(tool, result)
            key = re.search(r'\[task_receipt=([a-f0-9]+)', receipt)
            if not key:
                return plan, outcome.unverified('routine_step', 'Action returned but no checkpoint receipt could be stored; inspect before retrying.', retry_allowed=False)
            updated = self.plans.update({'action': 'complete_step', 'plan_id': plan_id, 'revision': revision,
                'receipt_id': key[1], 'evidence': f"{step['kind']} confirmed by {tool}: {step['value']}"[:1000]})
            return updated, result
        finally:
            _execution_lock.release()


def routine_context():
    try:
        names = [row['name'] for row in Routines().list()]
        if names:
            from core import outcome
            return ('[AVAILABLE ROUTINES]\nSaved names only; do not run until requested by the user.\n' +
                    outcome.untrusted('user routine names', json.dumps(names, ensure_ascii=False)))
    except Exception:
        return '[AVAILABLE ROUTINES]\nSaved routines unavailable; do not invent a routine.'
    return ''


def pause_running_routine():
    """Called by the existing user interrupt button; never undo an action."""
    plans = TaskPlans()
    for attempt in range(2):
        plan = plans.read()
        if not plan or not plan.get('routine') or plan['state'] != 'active':
            return
        try:
            plans.update({'action': 'pause', 'plan_id': plan['id'], 'revision': plan['revision'],
                          'reason': 'User interrupted the routine; inspect the current app before resuming.'})
            return
        except ValueError:
            if attempt:
                raise
