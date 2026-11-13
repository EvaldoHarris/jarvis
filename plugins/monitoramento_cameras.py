"""Voice commands for explicitly configured camera monitoring groups."""
from core import outcome
from core.camera_monitor import hub, load_groups


def run(parameters, player=None):
    action = parameters.get('action', 'status')
    groups = load_groups()
    if action == 'list':
        return outcome.done('monitoramento_cameras', groups=[dict(name=g['name'], cameras=len(g['cameras'])) for g in groups])
    if action == 'status':
        return outcome.done('monitoramento_cameras', monitors=hub.status())
    name = str(parameters.get('group') or '').strip().casefold()
    if action == 'stop_all':
        hub.stop()
        return outcome.done('monitoramento_cameras', stopped=True)
    matches = [g for g in groups if g['name'].casefold() == name]
    if len(matches) != 1:
        return outcome.failed('monitoramento_cameras', 'Escolha um grupo salvo no painel de monitoramento. Use list para consultar os nomes.')
    group = matches[0]
    if action == 'stop':
        hub.stop(group['id'])
        return outcome.done('monitoramento_cameras', stopped=group['name'])
    if action == 'start':
        try:
            return outcome.done('monitoramento_cameras', **hub.start(group, player),
                                note='Rodízio de câmeras. Só pessoas/veículos detectados são enviados à IA para análise e aviso. Não garante cobertura de todos os instantes.')
        except ValueError as exc:
            return outcome.failed('monitoramento_cameras', str(exc))
    return outcome.failed('monitoramento_cameras', 'Use start, stop, stop_all, list ou status.')


PLUGIN = {
    'name': 'monitoramento_cameras', 'tier': 'core',
    'description': 'Start, stop and inspect saved security camera monitoring groups, e.g. Sitio or Casa. '
    'User configures multiple named groups and their cameras in the camera monitoring panel. '
    'start requires an explicit user request to monitor that group; list names first if needed. '
    'One camera per group is observed at a time in a rotation; no guaranteed full coverage. '
    'Local detection filters people and vehicles; only confirmed local detections send a still image '
    'to the configured AI for a short description and queued voice alert. Announce this image sharing '
    'when starting. No identity, criminal intent, theft conclusions, recordings or emergency dispatch. '
    'status reports actual checked frames, connection errors and events; starting does not prove camera availability. '
    'stop_all stops all groups; stopping live HUD video does not stop monitoring.',
    'brief': 'Camera monitoring groups: start, stop, stop_all, list, status. People/vehicle detection then AI analysis and voice alert. Groups configured in monitoring panel.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['start', 'stop', 'stop_all', 'list', 'status']},
        'group': {'type': 'STRING', 'description': 'Exact saved group name, e.g. Sítio.'}}, 'required': ['action']},
}
