"""Configure presence-aware assistant speech output."""
import json
from core import outcome
from core.speech_routing import settings, configure


def speech_destination(parameters=None, **context):
    p = parameters or {}
    action = p.get('action', 'status')
    if action not in ('status', 'enable', 'disable'):
        return outcome.failed('speech_destination', 'Use status, enable or disable')
    cfg = settings()
    if action != 'status':
        changes = {k: str(p[k]).strip() for k in ('owner', 'device_id') if k in p}
        if 'unknown_alerts' in p:
            changes['unknown_alerts'] = p['unknown_alerts'] is True
        cfg = configure(enabled=action == 'enable', **changes)
    from core.android_bridge import bridge
    return outcome.done('speech_destination', enabled=cfg['enabled'], camera_before_each_utterance=cfg['enabled']) + '\n' + outcome.untrusted('speech_destination_config', json.dumps({**cfg,
        'connected_phones': bridge.list_devices(), 'last_delivery_error': bridge.last_delivery_error}, ensure_ascii=False))


TOOL = {
    'name': 'speech_destination',
    'description': 'Presence-based speech routing. enable: before each assistant utterance check the webcam locally; '
        'play on PC only when the enrolled owner face matches, otherwise send to one connected paired Android. '
        'Unknown camera/face means phone. Offline/ambiguous phone means text-only, no PC fallback. '
        'disable restores previous output behavior; status shows the preference. Optional owner is an enrolled '
        'face profile name; device_id selects an exact paired phone. Needs updated connected Android app with voice enabled. '
        'unknown_alerts=true enables the user-requested warning and a 20-second webcam preview on that phone '
        'when a visible face cannot be confirmed as the owner. An empty camera or camera error does not trigger '
        'a person alert. The image is sent only to the selected paired device; the alert may be a recognition '
        'failure and does not prove unauthorized computer use. status includes phone capabilities and delivery errors. '
        'Use when user says look at webcam before speaking or speak on phone when I am away. '
        'The camera is checked per utterance, not continuously, and images stay local.',
    'brief': 'Voice destination by webcam presence: enable, disable, status; optional owner/device_id.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['enable', 'disable', 'status']},
        'owner': {'type': 'STRING'}, 'device_id': {'type': 'STRING'},
        'unknown_alerts': {'type': 'BOOLEAN'}}, 'required': ['action']},
    'handler': speech_destination,
}
