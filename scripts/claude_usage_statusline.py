"""Official Claude statusLine adapter; stores quota fields only.

Run with --install to connect. Existing statusLine output is preserved.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def atomic_json(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root=None):
    root = Path(root or os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    root.mkdir(parents=True, exist_ok=True)
    settings = root / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    existing = data.get("statusLine") or {}
    if not isinstance(existing, dict):
        raise ValueError("Linha de status existente não reconhecida; configure manualmente.")
    if "claude_usage_statusline.py" in str(existing.get("command", "")):
        # Refresh an installed adapter when Jarvis itself has been updated.
        adapter = root / "claude_usage_statusline.py"
        if Path(__file__).resolve() != adapter.resolve():
            shutil.copyfile(Path(__file__), adapter)
        return "Adaptador do terminal configurado. Isso não confirma a leitura dos limites; o painel consulta a conta também."
    if existing and (existing.get("type") != "command" or not isinstance(existing.get("command"), str)):
        raise ValueError("Linha de status existente não reconhecida; configure manualmente.")
    # Copy adapter next to the cache: it keeps working if the repo is moved.
    adapter = root / "claude_usage_statusline.py"
    shutil.copyfile(Path(__file__), adapter)
    previous = base64.b64encode(existing.get("command", "").encode("utf-8")).decode("ascii")
    # Claude runs statusLine in a shell; forward slashes work in Windows Git Bash.
    python = sys.executable.replace("\\", "/")
    script = str(adapter).replace("\\", "/")
    cache = str(root / "jarvis-usage.json").replace("\\", "/")
    cmd = f'"{python}" "{script}" --cache "{cache}"'
    if previous:
        cmd += " --previous " + previous
    if settings.exists():
        backup = root / f"settings.jarvis-backup-{time.time_ns()}.json"
        shutil.copyfile(settings, backup)
    data["statusLine"] = {**existing, "type": "command", "command": cmd}
    atomic_json(settings, data)
    return "Claude conectado. Abra ou reinicie uma sessão do Claude Code; os limites chegam após a primeira resposta."


def capture(raw, cache):
    data = json.loads(raw)
    limits = data.get("rate_limits") or {}
    # Never persist tokens, transcripts, prompts, cwd, or account identifiers.
    filtered = {key: {field: value for field, value in limits[key].items()
                     if field in ("used_percentage", "resets_at")}
                for key in ("five_hour", "seven_day") if isinstance(limits.get(key), dict)}
    if filtered:
        atomic_json(Path(cache), {"rate_limits": filtered, "updated_at": time.time()})
    return filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--cache")
    parser.add_argument("--previous", default="")
    args = parser.parse_args()
    if args.install:
        print(install())
        return
    raw = sys.stdin.read()
    try:
        limits = capture(raw, args.cache)
    except (OSError, ValueError, TypeError, AttributeError):
        limits = {}
    if args.previous:
        # This is the user's PREEXISTING shell command, never model or stdin text.
        cmd = base64.b64decode(args.previous).decode("utf-8")
        try:
            if os.name == "nt":
                # Claude's statusLine uses Git Bash, even when Jarvis uses PowerShell.
                candidates = [os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", ""),
                              str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"),
                              shutil.which("bash") or ""]
                bash = next((p for p in candidates if p and Path(p).is_file()), None)
                if not bash:
                    return
                previous_cmd, use_shell = [bash, "-c", cmd], False
            else:
                previous_cmd, use_shell = cmd, True
            subprocess.run(previous_cmd, input=raw, text=True, shell=use_shell, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        parts = []
        for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
            used = limits.get(key, {}).get("used_percentage")
            if isinstance(used, (int, float)) and 0 <= used <= 100:
                parts.append(f"{label}: {100-used:g}% restante")
        print(" | ".join(parts) or "JARVIS · limites aguardando resposta")


if __name__ == "__main__":
    main()
