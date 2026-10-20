"""Reuse the same fixed local scripts as Alexa/TRIGGERcmd."""
import platform
import subprocess
import threading
from pathlib import Path

from core import outcome

SCRIPTS = {"almoco": Path("C:/TRIGGERcmd/DiscordStatus/almoco.ps1"),
           "voltei": Path("C:/TRIGGERcmd/DiscordStatus/voltei.ps1")}
_lock = threading.Lock()


def run(parameters, player=None, session_memory=None):
    action = parameters.get("action", "")
    if action not in SCRIPTS:
        return outcome.failed("discord_status", "Use almoco ou voltei.")
    if platform.system() != "Windows":
        return outcome.failed("discord_status", "A automação instalada exige Windows.")
    script = SCRIPTS[action]
    if not script.is_file():
        return outcome.failed("discord_status", f"Script local não encontrado: {script}")
    if not _lock.acquire(blocking=False):
        return outcome.failed("discord_status", "Já há um comando de status do Discord em execução.")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script)], cwd=str(script.parent), timeout=90,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            return outcome.failed("discord_status", "A automação local falhou. Confira os logs em C:/TRIGGERcmd/DiscordStatus/logs.")
        return outcome.unverified(
            "discord_status", "O script terminou sem erro, mas o status não foi conferido visualmente.",
            command=action, script_completed=True, windows_return_timer=False,
        )
    except subprocess.TimeoutExpired:
        return outcome.unverified("discord_status", "O comando excedeu 90 segundos; a automação pode ainda estar ativa. Confira o Discord antes de repetir.")
    except OSError:
        return outcome.failed("discord_status", "Não foi possível iniciar o PowerShell da automação local.")
    finally:
        _lock.release()


PLUGIN = {
    "name": "discord_status", "tier": "core",
    "description": (
        "Change Discord status using the same installed local scripts as Alexa/TRIGGERcmd. "
        "action=almoco sets the existing lunch preset and native Discord one-hour expiry. "
        "action=voltei runs the existing immediate return-to-online preset. "
        "Use for 'vou almoçar', 'status de almoço no Discord', 'voltei', 'fique disponível no Discord' "
        "when clearly requesting this Discord automation. Do not run for a mere greeting or "
        "ambiguous 'voltei' without Discord/lunch context. No passwords, tokens or generated commands. "
        "The scripts operate the Discord UI; do not click elsewhere while they run. "
        "No Windows timer is created. On unverified, report script execution without claiming "
        "the visible status was confirmed. Never repeat automatically."
    ),
    "brief": "Discord lunch/return status through the existing Alexa scripts: almoco or voltei. Native expiry only, no Windows return timer. Do not repeat automatically.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["almoco", "voltei"]},
    }, "required": ["action"]},
}
