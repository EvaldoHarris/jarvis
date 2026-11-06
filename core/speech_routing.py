"""Check local webcam presence before each assistant utterance, then route PCM."""
import asyncio
import json
import secrets
import threading
import time

from memory.config_manager import get_base_dir

CONFIG = get_base_dir() / 'config' / 'speech_routing.json'
_camera_lock = threading.Lock()


def settings():
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        return {'enabled': data.get('enabled') is True, 'owner': str(data.get('owner') or ''),
                'device_id': str(data.get('device_id') or ''), 'unknown_alerts': data.get('unknown_alerts') is True}
    except (OSError, ValueError, AttributeError):
        return {'enabled': False, 'owner': '', 'device_id': '', 'unknown_alerts': False}


def configure(**changes):
    data = {**settings(), **changes}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(CONFIG)
    return data


def probe_presence(owner=''):
    """Face matching runs locally; unknown/missing camera never means present."""
    from core import person_identity as identity
    from memory.config_manager import load_api_keys
    if not _camera_lock.acquire(blocking=False):
        return {'present': False, 'reason': 'camera_check_busy'}
    try:
        profiles = identity.load_profiles()
        faces = {name: p for name, p in profiles.items() if 'face' in p}
        config = load_api_keys()
        wanted = owner or str(config.get('voice_owner') or config.get('user_name') or '')
        if wanted not in faces:
            if not owner and len(faces) == 1:
                wanted = next(iter(faces))
            else:
                return {'present': False, 'reason': 'owner_face_not_enrolled'}
        observed = None
        for attempt in range(2):
            if attempt:
                time.sleep(.55)  # allow a new preview frame/pose before retrying
            try:
                observed = identity.face_observation()
            except Exception:
                if observed is None:
                    return {'present': False, 'person_visible': False, 'reason': 'camera_unavailable'}
                break
            for vector in observed['vectors']:
                matched = identity.best_match(vector, faces, 'face', .45)
                if matched and (matched == wanted or identity.same_face_profile(matched, wanted, faces)):
                    return {'present': True, 'person_visible': True, 'reason': 'owner_confirmed'}
            # Retry a nonmatch with a fresh camera frame before alerting.
        person_visible = bool(observed and observed['face_count'])
        return {'present': False, 'person_visible': person_visible,
                'reason': 'owner_not_recognized' if person_visible else 'no_person_visible',
                'image': observed['image'] if person_visible else b''}
    finally:
        _camera_lock.release()


class SpeechRouter:
    def __init__(self, report=lambda message: None, probe=probe_presence, config=settings):
        self.report, self.probe, self.config = report, probe, config
        self.route = None
        self._lock = asyncio.Lock()
        self._generation = 0
        self._last_alert = {}
        self._preview_stop = None
        self._preview_task = None

    def interrupt(self):
        self._generation += 1

    @property
    def legacy(self):
        return self.route is not None and self.route['destination'] == 'legacy'

    async def begin(self, bridge=None, requested=None):
        async with self._lock:
            if self.route is not None:
                return self.route
            cfg = self.config()
            if not cfg['enabled']:
                self.route = {'destination': 'legacy'}
                return self.route
            try:
                presence = await asyncio.wait_for(asyncio.to_thread(self.probe, cfg.get('owner', '')), timeout=8)
            except Exception:
                presence = {'present': False, 'reason': 'camera_check_unavailable'}
            if presence.get('present') is True:
                self._last_alert.clear()
                if self._preview_stop:
                    self._preview_stop.set()
                self.route = {'destination': 'pc'}
                return self.route
            devices = bridge.list_devices() if bridge else []
            wanted = cfg.get('device_id') or (requested or {}).get('reply_device')
            if wanted:
                devices = [d for d in devices if d['id'] == wanted]
            # No broadcasting to several phones or guessing another user's phone.
            if len(devices) != 1:
                self.route = {'destination': 'silent'}
                self.report('SYS: Voz no PC suspensa: presença não confirmada e celular indisponível ou ambíguo. Resposta no histórico.')
                return self.route
            device = devices[0]['id']
            if (cfg.get('unknown_alerts') and presence.get('person_visible') is True and presence.get('image')
                    and time.monotonic() - self._last_alert.get(device, -1000) >= 120):
                alert_id = 'alert_' + secrets.token_hex(12)
                notice = 'Evaldo, tem uma pessoa não identificada mexendo no seu computador'
                if await bridge.deliver_presence_frame(device, alert_id, presence['image'], notice=notice):
                    self._last_alert[device] = time.monotonic()
                    if self._preview_stop:
                        self._preview_stop.set()
                    from core.presence_preview import preview
                    self._preview_stop = threading.Event()
                    self._preview_task = asyncio.create_task(preview(bridge, device, alert_id, self._preview_stop))
                    self.report('SYS: Pessoa visível sem confirmação do proprietário: aviso e prévia da webcam enviados ao celular.')
                else:
                    self.report('SYS: Não foi possível enviar a imagem de alerta ao celular; confira a versão do app e a conexão.')
            request = 'presence_' + secrets.token_hex(12)
            if not await bridge.begin_speech(device, request):
                self.route = {'destination': 'silent'}
                self.report('SYS: O celular não confirmou a saída de voz: ' + str(getattr(bridge, 'last_delivery_error', '') or 'sem confirmação') + '. Resposta no histórico.')
                return self.route
            self.route = {'destination': 'phone', 'bridge': bridge, 'device': device,
                          'request': request, 'streamed': False, 'failed': False}
            self.report('SYS: Presença não confirmada na webcam; resposta de voz direcionada ao celular.')
            return self.route

    async def audio(self, pcm, bridge=None, requested=None):
        generation = self._generation
        route = await self.begin(bridge, requested)
        if generation != self._generation or route is not self.route:
            return False
        destination = route['destination']
        if destination == 'legacy':
            if requested and bridge:
                sent = await bridge.deliver_audio(requested['reply_device'], requested['reply_id'], pcm)
                requested['audio_streamed'] = bool(sent) or requested.get('audio_streamed', False)
            return True
        if destination == 'phone' and not route['failed']:
            sent = await route['bridge'].deliver_audio(route['device'], route['request'], pcm)
            route['streamed'] |= bool(sent)
            if not sent:
                route['failed'] = True
                self.report('SYS: Áudio no celular interrompido pela conexão. Resposta no histórico; sem repetir no PC.')
        return destination == 'pc'

    async def finish(self, text=''):
        async with self._lock:
            route, self.route = self.route, None
            if route and route['destination'] == 'phone':
                # A text-only engine can let the phone synthesize the same answer.
                await route['bridge'].deliver_reply(route['device'], route['request'],
                    '' if route['streamed'] else text, audio_streamed=route['streamed'])

    async def cancel(self):
        async with self._lock:
            route, self.route = self.route, None
            if route and route['destination'] == 'phone':
                await route['bridge'].cancel_speech(route['device'], route['request'])

    async def close(self):
        if self._preview_stop:
            self._preview_stop.set()
        if self._preview_task and not self._preview_task.done():
            self._preview_task.cancel()
            try:
                await self._preview_task
            except asyncio.CancelledError:
                pass
        await self.cancel()
