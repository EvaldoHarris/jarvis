"""Authenticated, in-memory request/reply bridge to paired native Android clients."""
import asyncio
import base64
import concurrent.futures
import secrets
import time

ACTIONS = {"screen", "open_app", "tap", "swipe", "text", "click", "back", "home", "status"}


class AndroidBridge:
    def __init__(self):
        self.devices = {}
        self.pending = {}
        self.loop = None
        self.last_delivery_error = ''

    async def attach(self, websocket, device_id, name, authorized=lambda: True, presence_audio=False, presence_video=False, monitor_video=False):
        self.loop = asyncio.get_running_loop()
        previous = self.devices.get(device_id)
        self.devices[device_id] = {"socket": websocket, "name": name[:80], "connected_at": time.time(), "authorized": authorized,
                                   "presence_audio": presence_audio is True, 'presence_video': presence_video is True,
                                   'monitor_video': monitor_video is True}
        if previous:
            await previous["socket"].close(code=4000)

    def detach(self, websocket, device_id):
        if self.devices.get(device_id, {}).get("socket") is not websocket:
            return
        self.devices.pop(device_id, None)
        for (device, request), future in list(self.pending.items()):
            if device == device_id and not future.done():
                future.set_result({"ok": False, "error": "Android desconectado durante o comando."})

    def list_devices(self):
        return [{"id": key, "name": value["name"], "connected": True,
                 'presence_audio': value.get('presence_audio', False),
                 'presence_video': value.get('presence_video', False),
                 'monitor_video': value.get('monitor_video', False)}
                for key, value in list(self.devices.items()) if value["authorized"]()]

    async def deliver_monitor_frame(self, device_id, packet, image):
        device = self.devices.get(device_id)
        if not device or not device['authorized']() or not device.get('monitor_video') or len(image) > 700_000:
            return False
        try:
            await asyncio.wait_for(device['socket'].send_json(dict(packet,
                image=base64.b64encode(image).decode('ascii'))), 2)
            return True
        except Exception:
            return False

    def _resolve(self, device_id):
        """Aceita o ID exato, o nome do aparelho ou nenhum valor quando só há um Android online."""
        online = [key for key, value in list(self.devices.items()) if value["authorized"]()]
        wanted = str(device_id or "").strip()
        if wanted in self.devices:
            return wanted
        if wanted:
            by_name = [key for key in online if self.devices[key]["name"].strip().lower() == wanted.lower()]
            if len(by_name) == 1:
                return by_name[0]
        if len(online) == 1:
            return online[0]
        return wanted or None

    async def request(self, device_id, action, args=None):
        if action not in ACTIONS:
            return {"ok": False, "error": "Ação Android não suportada."}
        device_id = self._resolve(device_id)
        if device_id is None:
            return {"ok": False, "error": "Escolha um Android conectado usando list."}
        device = self.devices.get(device_id)
        if not device or not device["authorized"]():
            return {"ok": False, "error": "Android offline. Nenhum comando foi enfileirado."}
        request_id = secrets.token_hex(16)
        future = asyncio.get_running_loop().create_future()
        self.pending[(device_id, request_id)] = future
        try:
            await asyncio.wait_for(device["socket"].send_json({"type": "command", "id": request_id,
                "action": action, "args": args or {}, "expires_at": time.time() + 20}), 3)
            return await asyncio.wait_for(future, 25)
        except (asyncio.TimeoutError, OSError, RuntimeError):
            return {"ok": False, "error": "Android não confirmou o comando a tempo; não repita automaticamente."}
        finally:
            self.pending.pop((device_id, request_id), None)

    def reply(self, device_id, message):
        if not isinstance(message.get("id"), str):
            return
        future = self.pending.get((device_id, message.get("id")))
        result = message.get("result")
        if future is not None and not future.done() and isinstance(result, dict):
            future.set_result(result)

    async def deliver_audio(self, device_id, request_id, pcm):
        device = self.devices.get(device_id)
        if not device or not device["authorized"]():
            return False
        try:
            await asyncio.wait_for(device["socket"].send_json({"type": "assistant_audio", "request_id": request_id,
                "rate": 24000, "data": base64.b64encode(pcm).decode("ascii")}), .5)
            return True
        except Exception:
            return False

    async def begin_speech(self, device_id, request_id):
        device = self.devices.get(device_id)
        if not device or not device['authorized']() or not device.get('presence_audio'):
            self.last_delivery_error = 'phone_offline' if not device else 'phone_app_needs_update'
            return False
        future = asyncio.get_running_loop().create_future()
        self.pending[(device_id, request_id)] = future
        try:
            await asyncio.wait_for(device['socket'].send_json({'type': 'assistant_start',
                'request_id': request_id, 'ttl_ms': 5000, 'expires_at': time.time() + 5}), 1)
            result = await asyncio.wait_for(future, 5)
            self.last_delivery_error = '' if result.get('ok') is True else str(result.get('error') or 'phone_refused_audio')
            return not self.last_delivery_error
        except Exception as exc:
            self.last_delivery_error = 'phone_ack_' + type(exc).__name__
            return False
        finally:
            self.pending.pop((device_id, request_id), None)

    async def deliver_presence_frame(self, device_id, alert_id, image, notice='', final=False):
        device = self.devices.get(device_id)
        if not device or not device['authorized']() or not device.get('presence_video'):
            self.last_delivery_error = 'phone_video_needs_update_or_offline'
            return False
        if len(image) > 700_000:
            return False
        try:
            await asyncio.wait_for(device['socket'].send_json({'type': 'presence_alert' if notice else 'presence_frame',
                'alert_id': alert_id, 'image': base64.b64encode(image).decode('ascii'),
                'notice': notice, 'final': final}), 1)
            return True
        except Exception:
            self.last_delivery_error = 'presence_video_send_failed'
            return False

    async def cancel_speech(self, device_id, request_id):
        device = self.devices.get(device_id)
        if not device or not device['authorized']():
            return False
        try:
            await asyncio.wait_for(device['socket'].send_json({'type': 'assistant_cancel',
                                                              'request_id': request_id}), .5)
            return True
        except Exception:
            return False

    async def deliver_reply(self, device_id, request_id, text, audio_streamed=False, final_reply=True, speak=True):
        device = self.devices.get(device_id)
        if not device or not device["authorized"]():
            return False
        try:
            await asyncio.wait_for(device["socket"].send_json({"type": "assistant_reply", "request_id": request_id,
                                            "text": text, "audio_streamed": bool(audio_streamed), "final_reply": bool(final_reply),
                                            "speak": bool(speak)}), 1)
            return True
        except Exception:
            return False

    def request_sync(self, device_id, action, args=None):
        if self.loop is None or not self.loop.is_running():
            return {"ok": False, "error": "Ponte Android indisponível."}
        future = asyncio.run_coroutine_threadsafe(self.request(device_id, action, args), self.loop)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return {"ok": False, "error": "Android não respondeu. Resultado não confirmado."}


bridge = AndroidBridge()
