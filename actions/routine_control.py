import json

from core import outcome
from core.routines import Routines


def routine_control(parameters=None, **context):
    params = parameters or {}
    try:
        store = Routines()
        action = params.get('action', 'list')
        if action == 'list':
            data = store.list()
        elif action == 'show':
            data = store.show(params.get('name'))
            if data is None:
                return outcome.ask('routine_control', 'Quais programas e paginas voce quer nessa rotina?', configured=False)
        elif action == 'save':
            data = store.save(params.get('name'), params.get('steps'), params.get('revision', 0))
        elif action == 'start':
            data = store.start(params.get('name'))
        elif action == 'next':
            data, observed = store.next(params.get('plan_id'), params.get('revision'), player=context.get('player'))
            if data['state'] != 'completed' and not observed.startswith('status=done '):
                return observed + '\n' + outcome.untrusted('routine checkpoint', json.dumps(data, ensure_ascii=False))
            return (outcome.done('routine_control', verified_scope='routine_step', plan_state=data['state']) + '\n' +
                    outcome.untrusted('routine checkpoint', json.dumps(data, ensure_ascii=False)) +
                    '\nCall next with the updated plan_id/revision only if still active and the user has not interrupted. Do not repeat completed steps.')
        else:
            return outcome.failed('routine_control', 'Use list, show, save, start or next')
        result = outcome.done('routine_control', verified_scope='routine_configuration_or_plan_only')
        result += '\n' + outcome.untrusted('saved user routine/plan data', json.dumps(data, ensure_ascii=False))
        if action == 'start':
            result += ('\nThe routine has NOT executed yet. Call routine_control next now with plan_id/revision from this plan. '
                       'next executes exactly one saved step with verified tool results and records its checkpoint. '
                       'Stop on a user interruption, safety stop, failure or unverified result. '
                       'Keep the checkpoint; do not restart completed steps. Never announce the routine complete just because its plan was created.')
        return result
    except Exception as exc:
        if params.get('action') == 'next':
            return outcome.unverified('routine_control', str(exc), recovery='task_plan status; inspect before resuming', retry_allowed=False)
        return outcome.failed('routine_control', str(exc), recovery='show routine and task_plan status', retry_allowed=False)


TOOL = {
    'name': 'routine_control',
    'description': 'User routines: list/show/save/start/next. save needs name and 2-20 steps (kind open_app or open_url, value); updates require current revision. Configure only user-requested apps/pages. start creates a task_plan; then call next repeatedly with exact plan_id/revision to execute one saved step and record verified progress. No external execution on save/list/show/start or startup. next serializes steps, waits for confirmed app windows, blocks on unverified results and respects pause/cancel. Resume via task_plan after user authorization and inspecting current apps. An unfinished task cannot be replaced. No scheduling.',
    'brief': 'User routines: list/show/save/start/next. start creates a plan, next executes one saved app/page step and records verified progress. Honor pause/cancel.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['list', 'show', 'save', 'start', 'next']},
        'plan_id': {'type': 'STRING'},
        'name': {'type': 'STRING'},
        'revision': {'type': 'INTEGER'},
        'steps': {'type': 'ARRAY', 'items': {'type': 'OBJECT', 'properties': {
            'kind': {'type': 'STRING', 'enum': ['open_app', 'open_url']},
            'value': {'type': 'STRING'}
        }, 'required': ['kind', 'value']}}
    }, 'required': ['action']},
    'handler': routine_control,
}
