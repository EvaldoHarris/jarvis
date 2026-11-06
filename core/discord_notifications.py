"""Read new Discord messages from the Discord desktop app's Windows notifications.

Discord gives bots no access to a person's DMs, and automating a user account
breaks its terms. The desktop app already shows a Windows toast for every
message you would be notified about, so this reads those toasts locally through
the Windows notification API. Whatever Discord notifies, Jarvis can announce;
muted channels stay silent here too.
"""
import asyncio
import platform

_INVISIBLE = dict.fromkeys(map(ord, "⁨⁩‌​"), None)


def _is_discord(app_id: str, name: str) -> bool:
    return "discord" in (app_id or "").lower() or (name or "").strip().lower() == "discord"


class DiscordNotificationWatcher:
    """Returns only notifications that appeared after the first poll."""

    def __init__(self):
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
            if not info or not _is_discord(info.app_user_model_id, info.display_info.display_name):
                continue
            binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
            texts = [t.text.translate(_INVISIBLE).strip() for t in binding.get_text_elements()] if binding else []
            texts = [t for t in texts if t]
            if texts:
                out.append({"id": n.id, "author": texts[0], "text": "\n".join(texts[1:])})
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
        if self._seen is None:   # first poll: skip the backlog already in the action center
            self._seen = {n["id"] for n in current}
            return []
        new = [n for n in current if n["id"] not in self._seen]
        self._seen = {n["id"] for n in current} | {n["id"] for n in new}
        return new


def summarize(messages: list[dict], limit: int = 400) -> str:
    """Group messages by sender into one compact text block."""
    grouped: dict[str, list[str]] = {}
    for m in messages:
        grouped.setdefault(m["author"], []).append(m["text"])
    lines = []
    for author, texts in grouped.items():
        body = " | ".join(t.replace("\n", " ") for t in texts if t)
        lines.append(f"{author}: {body[:limit]}")
    return "\n".join(lines)


if __name__ == "__main__":
    async def _demo():
        w = DiscordNotificationWatcher()
        await w.poll()
        print("Aguardando mensagens do Discord... (Ctrl+C para sair)", w.error)
        while True:
            await asyncio.sleep(5)
            new = await w.poll()
            if new:
                print(summarize(new))
    asyncio.run(_demo())
