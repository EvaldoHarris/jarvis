"""Shared task panel state and revision-checked human controls."""
from core.task_plan import TaskPlans


def panel_state():
    plan = TaskPlans().read()
    if not plan:
        return {'plan': None}
    return {'plan': {key: plan[key] for key in ('id', 'revision', 'state', 'objective', 'reason', 'updated_at')} |
            {'steps': [{'title': step['title'], 'state': step['state']} for step in plan['steps']],
             'completed': sum(step['state'] == 'done' for step in plan['steps']), 'total': len(plan['steps'])}}


def control(data):
    if not isinstance(data, dict) or data.get('action') not in ('pause', 'resume', 'cancel'):
        raise ValueError('Use pause, resume or cancel')
    if not isinstance(data.get('plan_id'), str) or type(data.get('revision')) is not int:
        raise ValueError('Current plan_id and integer revision required')
    return TaskPlans().update({'action': data['action'], 'plan_id': data['plan_id'], 'revision': data['revision'],
                              'reason': 'Solicitado pelo usuario no painel de tarefas.'})
