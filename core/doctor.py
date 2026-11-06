"""Diagnóstico do Jarvis: `python main.py doctor`.

Só lê e testa; nunca instala nada nem mostra segredos. Sai com código 1
quando há algum erro, para poder ser usado em scripts.
"""
from __future__ import annotations

import importlib.metadata as md
import json
import platform
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "api_keys.json"

OK, WARN, FAIL = "OK", "AVISO", "ERRO"
_results: list[tuple[str, str, str]] = []


def _add(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))


def _requirements() -> list[str]:
    """Pacotes de requirements.txt que valem para este sistema."""
    names = []
    for raw in (BASE / "requirements.txt").read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        spec, _, marker = line.partition(";")
        m = re.search(r'sys_platform\s*==\s*"(\w+)"', marker)
        if m and m.group(1) != sys.platform:
            continue
        name = re.split(r"[<>=!\[ ]", spec.strip(), 1)[0]
        if name:
            names.append(name)
    return names


def check_python() -> None:
    v = sys.version_info
    detail = f"{platform.python_version()} ({sys.executable})"
    _add(OK if (3, 10) <= v[:2] <= (3, 13) else WARN, "Python", detail)


def check_packages() -> None:
    missing = []
    for name in _requirements():
        try:
            md.version(name)
        except md.PackageNotFoundError:
            missing.append(name)
    if missing:
        _add(FAIL, "Dependências", "faltando: " + ", ".join(missing)
             + "  →  pip install -r requirements.txt")
    else:
        _add(OK, "Dependências", "todas de requirements.txt instaladas")


def _config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        _add(FAIL, "Configuração", f"{CONFIG} ilegível: {e}")
        return {}


def check_config(cfg: dict) -> None:
    if not CONFIG.exists():
        _add(FAIL, "Configuração", f"{CONFIG} não existe; abra o Jarvis para configurar")
        return
    key = str(cfg.get("gemini_api_key", "")).strip()
    _add(OK if key else FAIL, "Chave Gemini", "presente" if key else "vazia em api_keys.json")


def check_audio(cfg: dict) -> None:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception as e:  # PortAudio ausente, driver etc.
        _add(FAIL, "Áudio", f"sounddevice falhou: {e}")
        return
    ins = [d["name"] for d in devices if d["max_input_channels"] > 0]
    outs = [d["name"] for d in devices if d["max_output_channels"] > 0]
    _add(OK if ins else FAIL, "Microfone", f"{len(ins)} entrada(s)")
    _add(OK if outs else FAIL, "Saída de áudio", f"{len(outs)} saída(s)")
    for key, pool, label in (("input_device", ins, "Microfone escolhido"),
                             ("output_device", outs, "Saída escolhida")):
        wanted = str(cfg.get(key, "")).strip()
        if wanted and not any(wanted.lower() in n.lower() for n in pool):
            _add(WARN, label, f"'{wanted}' não está conectado; será usado o padrão")


def check_internet() -> None:
    try:
        import httpx
        httpx.head("https://generativelanguage.googleapis.com", timeout=5)
        _add(OK, "Internet / Gemini", "alcançável")
    except Exception as e:
        _add(FAIL, "Internet / Gemini", f"sem acesso: {type(e).__name__}")


def check_playwright() -> None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = Path(p.chromium.executable_path)
        if exe.exists():
            _add(OK, "Navegador Playwright", "Chromium instalado")
        else:
            _add(WARN, "Navegador Playwright", "rode: python -m playwright install chromium")
    except Exception as e:
        _add(WARN, "Navegador Playwright", f"indisponível: {type(e).__name__}")


def check_ollama(cfg: dict) -> None:
    url = str(cfg.get("llm_url") or "http://localhost:11434").rstrip("/")
    try:
        import httpx
        r = httpx.get(url + "/api/tags", timeout=2)
        models = [m.get("name") for m in r.json().get("models", [])]
        _add(OK, "Ollama (opcional)", f"{len(models)} modelo(s): " + ", ".join(models[:5]))
    except Exception:
        _add(WARN if cfg.get("llm_provider") == "ollama" else OK,
             "Ollama (opcional)", "não está rodando" + ("" if cfg.get("llm_provider") == "ollama" else " (não usado)"))


def check_optional() -> None:
    extras = {"faster_whisper": "Whisper local", "piper": "Voz Piper",
              "kokoro": "Voz Kokoro", "openwakeword": "Palavra de ativação"}
    import importlib.util
    have = [label for mod, label in extras.items() if importlib.util.find_spec(mod)]
    _add(OK, "Extras locais", ", ".join(have) if have else "nenhum instalado")
    _add(OK if shutil.which("ffmpeg") else WARN, "ffmpeg",
         "no PATH" if shutil.which("ffmpeg") else "ausente (alguns áudios/vídeos falham)")


def check_discord_status() -> None:
    folder = Path("C:/TRIGGERcmd/DiscordStatus")
    if sys.platform != "win32" or not folder.exists():
        return
    missing = [f for f in ("almoco.ps1", "voltei.ps1", "config.ini") if not (folder / f).exists()]
    if missing:
        _add(WARN, "Status do Discord", "faltando: " + ", ".join(missing))
        return
    try:
        ini = (folder / "config.ini").read_text(encoding="utf-16")
        calibrated = "Calibrated=1" in ini
    except (OSError, UnicodeError):
        calibrated = False
    _add(OK if calibrated else WARN, "Status do Discord",
         "scripts e calibração presentes" if calibrated else "rode configurar.ahk para calibrar")


def run() -> int:
    cfg = _config()
    for check in (check_python, check_packages, lambda: check_config(cfg),
                  lambda: check_audio(cfg), check_internet, check_playwright,
                  lambda: check_ollama(cfg), check_optional, check_discord_status):
        try:
            check()
        except Exception as e:  # um teste quebrado não derruba os outros
            _add(WARN, getattr(check, "__name__", "teste"), f"falhou: {e}")

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print("\nJARVIS DOCTOR\n" + "─" * 60)
    for status, name, detail in _results:
        print(f"[{status:^5}] {name:<22} {detail}")
    errors = sum(1 for s, *_ in _results if s == FAIL)
    warns = sum(1 for s, *_ in _results if s == WARN)
    print("─" * 60 + f"\n{errors} erro(s), {warns} aviso(s)\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(run())
