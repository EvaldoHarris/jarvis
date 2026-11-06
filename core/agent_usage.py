"""Account quota snapshots. No prompts, API keys, or conversation contents."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from core.cli_tools import executable, command

_claude_retry_at = 0.0


def claude_root():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))


def window(data, used_key, reset_key, label):
    if not isinstance(data, dict):
        return None
    used, reset = data.get(used_key), data.get(reset_key)
    if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
        return None
    if not isinstance(reset, (int, float)) or isinstance(reset, bool) or not math.isfinite(reset):
        reset = None
    return {"label": label, "remaining": round(100 - used, 1), "resets_at": reset}


def claude_usage():
    try:
        data = json.loads((claude_root() / "jarvis-usage.json").read_text(encoding="utf-8"))
        limits = data.get("rate_limits") or {}
        windows = [window(limits.get(key), "used_percentage", "resets_at", label)
                   for key, label in (("five_hour", "5h"), ("seven_day", "7d"))]
        valid = [w for w in windows if w]
        return {"windows": valid, "updated_at": float(data["updated_at"]),
                "source": data.get("source", "Claude statusLine"),
                "error": "" if valid else "Claude ainda não forneceu os limites"}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"windows": [], "error": "Aguardando consulta do uso do Claude", "updated_at": None}


def refresh_claude_usage():
    """Read subscription usage when the CLI/VS Code statusLine supplies no data.

    The account endpoint is not a public stable API. Reuse only the access
    token locally; never rotate credentials, log them, or send model prompts.
    """
    global _claude_retry_at
    import httpx
    cached = claude_usage()
    now = time.time()
    if cached["windows"] and now - (cached.get("updated_at") or 0) < 300:
        return cached
    if now < _claude_retry_at:
        return {**cached, "error": "Consulta do Claude em espera; nova tentativa automática"}
    # Apply a cooldown to every attempt, including missing/expired logins.
    _claude_retry_at = now + 300
    try:
        credentials = json.loads((claude_root() / ".credentials.json").read_text(encoding="utf-8"))
        auth = credentials.get("claudeAiOauth") or {}
        token = auth.get("accessToken")
        if not isinstance(token, str) or not token:
            return {**cached, "error": "Faça login da assinatura com claude auth login"}
        expires = auth.get("expiresAt")
        if isinstance(expires, (int, float)) and expires / 1000 <= now:
            return {**cached, "error": "Login do Claude expirado; abra o Claude Code para renová-lo"}
        response = httpx.get("https://api.anthropic.com/api/oauth/usage", headers={
            "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20"},
            timeout=10, follow_redirects=False)
        if response.status_code == 429:
            try:
                retry = float(response.headers.get("retry-after", 600))
            except (TypeError, ValueError):
                retry = 600
            _claude_retry_at = now + max(600, min(3600, retry))
            return {**cached, "error": "Claude limitou as consultas; nova tentativa automática"}
        if response.status_code in (401, 403):
            return {**cached, "error": "Confira o login da assinatura no Claude Code"}
        if response.status_code != 200:
            return {**cached, "error": "Serviço de uso do Claude indisponível"}
        data = response.json()
        limits = {}
        for key in ("five_hour", "seven_day"):
            raw = data.get(key)
            if not isinstance(raw, dict):
                continue
            reset = raw.get("resets_at")
            if isinstance(reset, str):
                try:
                    reset = datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    reset = None
            item = {"used_percentage": raw.get("utilization"), "resets_at": reset}
            if window(item, "used_percentage", "resets_at", key):
                limits[key] = item
        if not limits:
            return {**cached, "error": "Conta Claude sem limites de assinatura disponíveis"}
        # Persist percentages/times only, never the response or credentials.
        path = claude_root() / "jarvis-usage.json"
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"rate_limits": limits, "updated_at": now, "source": "Claude account usage"}, stream)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return claude_usage()
    except (OSError, ValueError, TypeError, AttributeError, httpx.HTTPError):
        return {**cached, "error": "Não foi possível consultar o uso; confira o login e a conexão do Claude"}


def codex_usage(timeout=20):
    exe = executable("codex")
    if not exe:
        raise ValueError("Codex CLI não instalado")
    proc = subprocess.Popen(command(exe, ["app-server"]), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    inbox = queue.Queue()

    def read():
        try:
            for line in proc.stdout:
                try:
                    inbox.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            inbox.put(None)

    reader = threading.Thread(target=read, daemon=True, name="codex-quota-reader")
    reader.start()
    deadline = time.monotonic() + timeout

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def receive(id):
        while True:
            try:
                msg = inbox.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                raise ValueError("Codex não respondeu à consulta de limites") from None
            if msg is None:
                raise ValueError("Codex encerrou a consulta de limites")
            if isinstance(msg, dict) and msg.get("id") == id:
                if "error" in msg:
                    raise ValueError("Limites indisponíveis; confira o login ChatGPT no Codex")
                return msg.get("result") or {}
            if time.monotonic() >= deadline:
                raise ValueError("Codex não respondeu à consulta de limites")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "jarvis_usage", "version": "1.0"}, "capabilities": {}}})
        receive(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "account/rateLimits/read"})
        result = receive(2)
        limits = result.get("rateLimits") or (result.get("rateLimitsByLimitId") or {}).get("codex") or {}
        windows = []
        for key in ("primary", "secondary"):
            data = limits.get(key) or {}
            minutes = data.get("windowDurationMins")
            label = {300: "5h", 10080: "7d"}.get(minutes, f"{minutes}min" if minutes else key)
            item = window(data, "usedPercent", "resetsAt", label)
            if item:
                windows.append(item)
        return {"windows": windows, "updated_at": time.time(), "source": "Codex app-server",
                "error": "" if windows else "Conta sem limites de assinatura disponíveis"}
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        reader.join(timeout=2)
        proc.stdin.close()
        proc.stdout.close()


def display(snapshot, now=None):
    """Expired observations are unknown, never an assumed 100% refill."""
    now = time.time() if now is None else now
    parts, details = [], []
    updated = snapshot.get("updated_at")
    stale = isinstance(updated, (int, float)) and now - updated > 600
    for item in snapshot.get("windows", []):
        reset = item.get("resets_at")
        expired = reset is not None and reset <= now
        value = "--" if expired else f"{item['remaining']:g}%"
        parts.append(f"{item['label']} {value}")
        if reset:
            details.append(f"{item['label']}: renova em {_date(reset)}")
    if stale:
        parts.append("desatualizado")
    if updated:
        details.append(f"Última leitura: {_date(updated)}")
    if snapshot.get("error"):
        details.append(snapshot["error"])
    if snapshot.get("source"):
        details.append(f"Fonte: {snapshot['source']}")
    return " · ".join(parts) if parts else "Indisponível", "\n".join(details)


def _date(timestamp):
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().strftime("%d/%m %H:%M:%S %Z")
    except (OSError, ValueError, OverflowError):
        return "horário indisponível"


class UsageMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._next = 0
        self._data = {engine: {"windows": [], "error": "Aguardando leitura"} for engine in ("claude", "codex")}

    def refresh(self, force=False):
        with self._lock:
            if self._running or (not force and time.monotonic() < self._next):
                return
            self._running = True

        def work():
            try:
                claude = refresh_claude_usage()
                with self._lock:
                    self._data["claude"] = claude
                try:
                    result = codex_usage()
                except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
                    result = {"windows": [], "error": "Confira a instalação e o login ChatGPT no Codex"}
                with self._lock:
                    self._data["codex"] = result
            finally:
                with self._lock:
                    self._running = False
                    self._next = time.monotonic() + 120
        threading.Thread(target=work, daemon=True, name="agent-usage").start()

    def snapshot(self):
        # Reading snapshots never performs network I/O on the UI thread.
        with self._lock:
            result = deepcopy(self._data)
        cached = claude_usage()
        if (cached.get("updated_at") or 0) > (result["claude"].get("updated_at") or 0):
            result["claude"] = cached
        return result
