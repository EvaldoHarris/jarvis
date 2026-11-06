"""Avisos proativos a partir das notificações do Windows de QUALQUER app.

Outlook, Teams, WhatsApp, Discord, Gmail/Agenda no navegador, GitHub: todos já
mostram uma notificação do Windows. Lemos essas notificações localmente
(sem senha, sem API de terceiros) e decidimos:

  importante -> o Jarvis fala na hora
  normal     -> fica guardado para "o que eu perdi?"

Importante = cita o seu nome, é mensagem direta, vem de uma pessoa VIP,
contém palavra de alerta (urgente, falhou, reunião...) ou vem de um app de
agenda. Respeita "não perturbe" e horário de silêncio.

As regras ficam em config/alerts.json e podem ser mudadas por voz.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections import deque
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "alerts.json"

DEFAULTS = {
    "mode": "important",            # important | all | off
    "keywords": ["urgente", "urgent", "falhou", "failed", "falha", "erro", "error", "caiu", "down",
                 "incidente", "incident", "fora do ar", "reuniao", "meeting", "comeca em", "starts in",
                 "lembrete", "reminder", "socorro", "help"],
    "vip": [],                      # nomes de pessoas sempre importantes
    "muted_apps": ["PC Manager", "Adobe"],   # apps nunca anunciados
    "calendar_apps": ["outlook", "calendar", "agenda", "teams", "meet", "zoom"],
    "quiet_hours": ["22:30", "07:00"],
    "snooze_until": 0,
}

# Notificações do próprio Jarvis e do sistema não viram aviso.
_IGNORED_APPS = re.compile(r"(?i)^(python|pythonw|jarvis|windows (security|update)|microsoft store|settings|configura)")
# Inclui o enchimento invisível que e-mails promocionais põem no resumo.
_INVISIBLE = dict.fromkeys(map(ord, "⁨⁩‌​͏­‍﻿"), None)
_MAIL_APPS = re.compile(r"outlook|mail|gmail|thunderbird")
_REMINDER = re.compile(r"comeca (em|agora)|starts (in|now)|em \d+ ?min|in \d+ ?min|\blembrete\b|\breminder\b|"
                       r"agora mesmo|esta comecando|is starting|participar|join now")

_lock = threading.Lock()
_missed: deque = deque(maxlen=200)
_last_missed_read = 0.0


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def load() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_names() -> list[str]:
    try:
        keys = json.loads((BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
        name = str(keys.get("user_name", "")).strip()
    except (OSError, ValueError):
        name = ""
    parts = [p for p in re.split(r"\s+", name) if len(p) >= 3]
    return [_plain(p) for p in parts[:2]]


def _in_quiet_hours(cfg: dict, now: datetime | None = None) -> bool:
    try:
        start, end = (datetime.strptime(t, "%H:%M").time() for t in cfg["quiet_hours"])
    except Exception:
        return False
    t = (now or datetime.now()).time()
    return (start <= t or t < end) if start > end else (start <= t < end)


def classify(note: dict, cfg: dict | None = None) -> tuple[bool, str]:
    """(importante?, motivo)."""
    cfg = cfg or load()
    app, title, text = _plain(note.get("app", "")), _plain(note.get("title", "")), _plain(note.get("text", ""))
    blob = f"{title} {text}"
    if any(_plain(m) in app for m in cfg["muted_apps"] if m):
        return False, "app silenciado"
    for vip in cfg["vip"]:
        if vip and _plain(vip) in title:
            return True, f"VIP: {vip}"
    # E-mail de marketing chama você pelo nome; em e-mail o nome não conta.
    is_mail = bool(_MAIL_APPS.search(app))
    if not is_mail:
        for name in _user_names():
            if re.search(r"(?<!\w)@?" + re.escape(name) + r"(?!\w)", text):
                return True, "citou você"
    if any(_plain(a) in app for a in cfg["calendar_apps"] if a) and _REMINDER.search(blob):
        return True, "agenda"
    for word in cfg["keywords"]:
        if word and re.search(r"(?<!\w)" + re.escape(_plain(word)) + r"(?!\w)", blob):
            return True, f"palavra: {word}"
    # Discord: canal aparece como "Autor (#canal, servidor)"; sem '#' é mensagem direta.
    if "discord" in app and "#" not in note.get("title", ""):
        return True, "mensagem direta"
    return False, "normal"


def should_speak(important: bool, cfg: dict | None = None) -> bool:
    cfg = cfg or load()
    if cfg["mode"] == "off" or time.time() < float(cfg.get("snooze_until") or 0):
        return False
    if cfg["mode"] == "all":
        return not _in_quiet_hours(cfg)
    return important and not _in_quiet_hours(cfg)


def remember(note: dict, important: bool, reason: str, spoken: bool) -> None:
    with _lock:
        _missed.append({**note, "important": important, "reason": reason, "spoken": spoken, "at": time.time()})


def missed(since_last_read: bool = True) -> list[dict]:
    """Avisos não falados desde a última consulta."""
    global _last_missed_read
    with _lock:
        cutoff = _last_missed_read if since_last_read else 0
        rows = [m for m in _missed if not m["spoken"] and m["at"] > cutoff]
        _last_missed_read = time.time()
    return rows


def summarize(notes: list[dict], limit: int = 300) -> str:
    lines = []
    for n in notes:
        when = datetime.fromtimestamp(n["at"]).strftime("%H:%M") if "at" in n else ""
        body = n.get("text", "").replace("\n", " ")[:limit]
        lines.append(f"[{when} {n.get('app', '')}] {n.get('title', '')}: {body}".strip())
    return "\n".join(lines)


class NotificationWatcher:
    """Devolve só as notificações que surgiram depois da primeira leitura."""

    def __init__(self):
        import platform
        self._seen: set[int] | None = None
        self.available = platform.system() == "Windows"
        self.error = ""

    async def _read(self) -> list[dict]:
        from winrt.windows.ui.notifications.management import (
            UserNotificationListener, UserNotificationListenerAccessStatus)
        from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
        listener = UserNotificationListener.current
        if await listener.request_access_async() != UserNotificationListenerAccessStatus.ALLOWED:
            raise PermissionError("Windows negou acesso às notificações "
                                  "(Configurações > Privacidade > Notificações).")
        out = []
        for n in await listener.get_notifications_async(NotificationKinds.TOAST):
            info = n.app_info
            app = info.display_info.display_name if info else ""
            if not app or _IGNORED_APPS.search(app):
                continue
            binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
            texts = [t.text.translate(_INVISIBLE).strip() for t in binding.get_text_elements()] if binding else []
            texts = [t for t in texts if t]
            if texts:
                body = re.sub(r"[ \t]{2,}", " ", "\n".join(texts[1:]))
                out.append({"id": n.id, "app": app, "title": texts[0][:200], "text": body[:1500]})
        return out

    async def poll(self) -> list[dict]:
        if not self.available:
            return []
        try:
            current = await self._read()
            self.error = ""
        except ImportError:
            self.available, self.error = False, "Pacotes winrt não instalados."
            return []
        except Exception as exc:
            self.error = str(exc)
            return []
        if self._seen is None:      # primeira leitura: ignora o que já estava na central
            self._seen = {n["id"] for n in current}
            return []
        new = [n for n in current if n["id"] not in self._seen]
        self._seen = {n["id"] for n in current} | {n["id"] for n in new}
        return new
