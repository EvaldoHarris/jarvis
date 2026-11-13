"""Bounded, ephemeral camera-event replay over the existing authenticated bridge."""
import asyncio
import os
import secrets
import time


def pc_active():
    """Recent input on the unlocked Windows desktop is a presence fallback."""
    if os.name != 'nt':
        return False
    import ctypes as C
    from ctypes import wintypes as W
    class LastInput(C.Structure):
        _fields_ = [('size', W.UINT), ('tick', W.DWORD)]
    user = C.WinDLL('user32', use_last_error=True)
    user.OpenInputDesktop.restype = W.HANDLE
    desktop = user.OpenInputDesktop(0, False, 0x100)  # DESKTOP_SWITCHDESKTOP
    if not desktop:
        return False
    user.SwitchDesktop.argtypes = [W.HANDLE]
    user.CloseDesktop.argtypes = [W.HANDLE]
    try:
        if not user.SwitchDesktop(desktop):
            return False
    finally:
        user.CloseDesktop(desktop)
    value = LastInput(C.sizeof(LastInput), 0)
    if not user.GetLastInputInfo(C.byref(value)):
        return False
    kernel = C.WinDLL('kernel32')
    kernel.GetTickCount.restype = W.DWORD
    return ((kernel.GetTickCount() - value.tick) & 0xffffffff) < 120_000


def compact_image(jpeg):
    if len(jpeg) <= 700_000:
        return jpeg
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return b''
    h, w = image.shape[:2]
    image = cv2.resize(image, (max(1, int(w * min(1, 960 / w))), max(1, int(h * min(1, 960 / w)))))
    ok, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return data.tobytes() if ok and len(data) <= 700_000 else b''


class AlertDelivery:
    def __init__(self, ui, bridge=lambda: None):
        self.ui, self.bridge = ui, bridge
        self.active = set()

    async def deliver(self, event, feed, history, stopped):
        key = event['group']
        if key in self.active or len(self.active) >= 3 or stopped.is_set() or not history:
            return
        self.active.add(key)
        alert = 'monitor_' + secrets.token_hex(12)
        phone = None
        bridge = self.bridge()
        try:
            from core.speech_routing import settings, probe_presence
            cfg = settings()
            if cfg['enabled']:
                try:
                    presence = await asyncio.wait_for(asyncio.to_thread(probe_presence, cfg['owner']), 8)
                    present = presence.get('present') is True
                except Exception:
                    present = False
            else:
                present = await asyncio.to_thread(pc_active)
            if stopped.is_set():
                return
            if not present and bridge:
                devices = [d for d in bridge.list_devices() if d.get('monitor_video')]
                if cfg.get('device_id'):
                    devices = [d for d in devices if d['id'] == cfg['device_id']]
                if len(devices) == 1:
                    phone = devices[0]['id']
            if not present and not phone:
                self.ui.write_log('MONITOR: Celular indisponível ou sem suporte a alertas; imagem mantida no PC.')
            first = True

            async def send(jpeg=b'', offset=0., final=False):
                nonlocal first, phone
                packet = dict(type='monitor_alert' if first else 'monitor_frame', alert_id=alert,
                              group=event['group'], camera=event['camera'], labels=event['labels'],
                              time=event['time'], offset=round(offset, 1), final=final)
                image = await asyncio.to_thread(compact_image, jpeg) if jpeg else b''
                if stopped.is_set() and not final:
                    return
                try:
                    from core.monitor_recordings import append
                    await asyncio.to_thread(append, packet, image)
                except OSError:
                    self.ui.write_log('MONITOR: Não foi possível salvar a gravação local; entrega continua.')
                if phone and not await bridge.deliver_monitor_frame(phone, packet, image):
                    self.ui.write_log('MONITOR: Envio ao celular interrompido; exibindo alerta no PC.')
                    phone = None
                    packet['type'] = 'monitor_alert'
                if not phone:
                    self.ui.show_monitor_alert(dict(packet, image=image))
                first = False

            trigger = event.get('trigger', time.monotonic())
            # Replay at most five seconds of pre-event images, then follow the
            # same feed for up to 60 seconds. No new camera session is opened.
            last = 0
            for seq, jpeg, received in history:
                if stopped.is_set():
                    break
                await send(jpeg, received - trigger)
                last = seq
                await asyncio.sleep(.5)
            deadline = time.monotonic() + 60
            while not stopped.is_set() and time.monotonic() < deadline:
                recent = feed.recent()
                if recent and recent[-1][0] > last:
                    seq, jpeg, received = recent[-1]
                    if time.monotonic() - received < 3:
                        await send(jpeg, received - trigger)
                        last = seq
                if feed.closed:
                    break
                await asyncio.sleep(.5)
            if not first:
                await send(final=True)
        except Exception:
            self.ui.write_log('MONITOR: Falha ao exibir ou enviar as imagens do alerta.')
        finally:
            self.active.discard(key)
