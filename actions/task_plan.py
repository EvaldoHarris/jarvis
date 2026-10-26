"""Model-facing planning action; UI execution remains in the existing tools."""
import json

from core import outcome
from core.task_plan import TaskPlans


def task_plan(parameters=None, player=None, **context):
    params = parameters or {}
    try:
        plan = TaskPlans().update(params)
        if player and params.get('action', 'status') != 'status' and plan:
            done = sum(step['state'] == 'done' for step in plan['steps'])
            try:
                player.write_log(f"SYS: Plano: {done}/{len(plan['steps'])} etapas | {plan['state']}")
            except Exception:
                pass
        return outcome.done('task_plan', verified_scope='checkpoint_record_only') + '\n' + outcome.untrusted(
            'task plan data', json.dumps(plan, ensure_ascii=False))
    except Exception as exc:
        return outcome.failed('task_plan', str(exc), recovery='status', retry_allowed=False)


TOOL = {
    'name': 'task_plan',
    'description': 'Persist a multi-step task objective and ordered checkpoints. Use for complex PC tasks, not simple clicks. create needs objective and 2-20 steps. Read status before resuming. Mutations need exact plan_id/revision. complete_step requires receipt_id from a successful actual tool result plus evidence explaining how the observation satisfies the current step. Navigation-only receipts never prove booking/payment/sending. Only the next pending step can complete; the last completes the plan. pause/block/cancel require reason. Pause/cancel only at user request; block when genuinely stuck. resume only when the user authorizes continuation. A saved plan does not execute tools or undo actions; cancellation is not undo. Never save credentials in the plan.',
    'brief': 'Persistent ordered task checkpoints: create/status/complete_step/pause/block/resume/cancel. Record actual tool receipt and evidence; never invent completion.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['create', 'status', 'complete_step', 'pause', 'block', 'resume', 'cancel']},
        'objective': {'type': 'STRING'},
        'steps': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'plan_id': {'type': 'STRING'},
        'revision': {'type': 'INTEGER'},
        'receipt_id': {'type': 'STRING'},
        'evidence': {'type': 'STRING'},
        'reason': {'type': 'STRING'}
    }, 'required': ['action']},
    'handler': task_plan,
}
