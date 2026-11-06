"""Delega programação ao Claude Code ou ao Codex, rodando sem janela.

Os dois já estão logados neste PC, então nenhuma chave passa pelo Jarvis.
Cada pedido:
  1. mostra na tela o que vai acontecer e espera CONFIRMAR;
  2. roda o agente em segundo plano, numa pasta de projeto;
  3. ao terminar, fala o resumo e mostra no painel o que mudou.

Modos:
  plan  - só lê e propõe (Claude em modo plan, Codex read-only). Não confirma.
  build - cria/edita arquivos e roda comandos dentro da pasta.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from core import outcome

PROJECTS_DIR = Path.home() / "Desktop" / "JarvisProjects"
TIMEOUT_SECONDS = 45 * 60
LOG_NAME = ".jarvis-agent.log"

# Regras passadas aos dois agentes em todo pedido.
GUIDE = (
    "Você foi chamado pelo assistente de voz JARVIS a pedido do usuário. Trabalhe só dentro "
    "da pasta atual. Em Python, use um ambiente virtual .venv na própria pasta do projeto, "
    "nunca o Python global. Escreva testes para o que construir e rode-os. Não faça push, "
    "não publique nada e não apague arquivos fora do que a tarefa exige. Termine com um "
    "resumo curto em português: o que foi feito, como rodar e o resultado dos testes."
)

_lock = threading.Lock()
_job: dict | None = None        # {"engine", "folder", "proc", "started", "task"}


def _exe(name: str) -> str | None:
    if name == "codex":
        # O Codex da extensão do VS Code se atualiza sozinho e entende o
        # config.toml atual; o do npm costuma ficar para trás.
        ext = Path.home() / ".vscode" / "extensions"
        bundled = sorted(ext.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"), reverse=True)
        if bundled:
            return str(bundled[0])
        npm = Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd"
        if npm.exists():
            return str(npm)
    return shutil.which(name + ".cmd") or shutil.which(name)


def _git(folder: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip()
    except Exception:
        return ""


def _resolve_folder(params: dict) -> tuple[Path | None, str, bool]:
    """(pasta, erro, é_nova)."""
    raw = str(params.get("project_path", "")).strip().strip('"')
    if raw:
        folder = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not folder.is_dir():
            return None, f"Pasta não encontrada: {folder}", False
        if folder.resolve() in (Path.home().resolve(), Path(folder.anchor).resolve()):
            return None, "Escolha a pasta de um projeto, não a pasta do usuário ou a raiz do disco.", False
        return folder, "", False
    name = re.sub(r"[^\w\-]+", "_", str(params.get("project_name") or "").strip()).strip("_")
    if not name:
        name = "projeto_" + time.strftime("%Y%m%d_%H%M%S")
    return PROJECTS_DIR / name, "", True


def _command(engine: str, mode: str, folder: Path) -> list[str]:
    if engine == "claude":
        cmd = [_exe("claude"), "-p", "--output-format", "json",
               "--permission-mode", "plan" if mode == "plan" else "auto"]
        model = os.environ.get("JARVIS_CLAUDE_MODEL", "").strip()
        return cmd + (["--model", model] if model else [])
    cmd = [_exe("codex"), "exec", "-C", str(folder), "--skip-git-repo-check",
           "--sandbox", "read-only" if mode == "plan" else "workspace-write",
           "-o", str(folder / ".jarvis-codex-last.txt"), "-"]
    return cmd


def _summary(engine: str, folder: Path, stdout: str) -> str:
    if engine == "claude":
        try:
            data = json.loads(stdout.strip().splitlines()[-1])
            text = str(data.get("result") or "")
            if data.get("is_error"):
                text = "ERRO: " + text
            return text
        except Exception:
            return stdout[-3000:]
    last = folder / ".jarvis-codex-last.txt"
    try:
        return last.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return stdout[-3000:]


def _run(engine: str, mode: str, folder: Path, task: str, is_new: bool, player) -> str:
    global _job
    folder.mkdir(parents=True, exist_ok=True)
    if mode == "build" and not (folder / ".git").exists():
        # Um repositório local deixa cada mudança do agente revisável e reversível.
        _git(folder, "init", "-q")
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text(".venv/\n__pycache__/\nnode_modules/\n.jarvis-*\n", encoding="utf-8")
    before = _git(folder, "rev-parse", "HEAD")
    prompt = f"{GUIDE}\n\nTarefa:\n{task}"
    started = time.time()
    proc = subprocess.Popen(_command(engine, mode, folder), cwd=folder, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with _lock:
        _job = {"engine": engine, "folder": str(folder), "proc": proc, "started": started, "task": task[:200]}
    try:
        out, err = proc.communicate(prompt, timeout=TIMEOUT_SECONDS)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        timed_out = True
    finally:
        with _lock:
            _job = None

    minutes = (time.time() - started) / 60
    summary = _summary(engine, folder, out or "").strip()
    changes = _git(folder, "status", "--short")
    log = (f"[{time.strftime('%Y-%m-%d %H:%M')}] {engine} {mode} ({minutes:.1f} min, exit {proc.returncode})\n"
           f"Tarefa: {task}\n\nResumo:\n{summary}\n\nArquivos alterados:\n{changes or '(nenhum)'}\n"
           + (f"\nErros:\n{err[-2000:]}\n" if proc.returncode and err else "") + "\n" + "-" * 60 + "\n")
    try:
        with open(folder / LOG_NAME, "a", encoding="utf-8") as fh:
            fh.write(log)
    except OSError:
        pass

    if timed_out:
        status = outcome.failed("coding_agent", f"parou após {TIMEOUT_SECONDS // 60} minutos", folder=str(folder))
    elif proc.returncode:
        status = outcome.failed("coding_agent", f"{engine} terminou com erro {proc.returncode}", folder=str(folder))
    else:
        status = outcome.done("coding_agent", engine=engine, folder=str(folder),
                              changed_files=len(changes.splitlines()), minutes=round(minutes, 1))

    if player:
        if hasattr(player, "show_content"):
            try:
                player.show_content(f"{engine.upper()} — {folder.name}", log)
            except Exception:
                pass
        if hasattr(player, "request_say"):
            try:
                player.request_say(
                    "The coding agent finished. Tell the user in two or three short sentences, in their "
                    "language, what happened, based only on this report (the summary is the agent's own "
                    "claim, not independently verified): " + status + "\n" + summary[:1500])
            except Exception:
                pass
    return status


def coding_agent(parameters=None, player=None, **context):
    p = parameters or {}
    action = str(p.get("action", "run")).lower().strip()

    if action == "status":
        with _lock:
            job = dict(_job) if _job else None
        if not job:
            return outcome.done("coding_agent", running=False)
        return outcome.done("coding_agent", running=True, engine=job["engine"], folder=job["folder"],
                            minutes=round((time.time() - job["started"]) / 60, 1), task=job["task"])
    if action == "cancel":
        with _lock:
            job = _job
        if not job:
            return outcome.done("coding_agent", running=False)
        job["proc"].kill()
        return outcome.done("coding_agent", cancelled=True, folder=job["folder"])

    task = str(p.get("task", "")).strip()
    if not task:
        return outcome.failed("coding_agent", "descreva a tarefa em task")
    engine = str(p.get("engine", "claude")).lower().strip()
    if engine not in ("claude", "codex"):
        engine = "claude"
    if not _exe(engine):
        other = "codex" if engine == "claude" else "claude"
        if not _exe(other):
            return outcome.failed("coding_agent", "nem Claude Code nem Codex estão instalados")
        engine = other
    mode = "plan" if str(p.get("mode", "build")).lower() == "plan" else "build"
    folder, error, is_new = _resolve_folder(p)
    if error:
        return outcome.failed("coding_agent", error)
    with _lock:
        if _job:
            return outcome.failed("coding_agent", "já há um agente trabalhando; use status ou cancel",
                                  folder=_job["folder"])

    def start() -> str:
        hook = p.get("_on_start")     # interno: ex. kbgen aprende produto -> pasta
        if callable(hook):
            try:
                hook()
            except Exception as exc:
                print(f"[CodingAgent] on_start: {exc}")
        threading.Thread(target=_run, args=(engine, mode, folder, task, is_new, player),
                         daemon=True, name="coding-agent").start()
        return f"{engine} started in {folder}"

    if mode == "plan" and not is_new:
        # Só leitura: nada muda no disco, então não precisa de confirmação.
        start()
        return outcome.started("coding_agent", engine=engine, mode=mode, folder=str(folder))

    from core import confirm
    if confirm.pending_title():
        return outcome.ask("coding_agent", "there is already a confirmation waiting on screen - the user has to answer that one first")
    name = "Claude Code" if engine == "claude" else "Codex"
    return confirm.request(
        key="coding-agent",
        title=f"{name} vai programar em {folder.name}",
        detail=(f"Pasta: {folder}{' (nova)' if is_new else ''}\nModo: {mode}\n\nTarefa:\n{task}\n\n"
                f"O agente pode criar e editar arquivos e rodar comandos (testes, instalar pacotes no .venv) "
                f"dentro dessa pasta. As mudanças ficam registradas no git local da pasta."),
        run=start,
    )


TOOL = {
    "name": "coding_agent",
    "description": (
        "Delegate real programming work to Claude Code (default) or OpenAI Codex running headless on this PC: "
        "build new projects, change or fix EXISTING projects, add tests, refactor, explain a codebase. "
        "Prefer this over dev_agent and code_helper for anything beyond a tiny snippet. "
        "action=run with task (the user's request, detailed, in their words), optional project_path (existing "
        "folder) or project_name (new folder under Desktop/JarvisProjects), engine claude|codex (only if the user "
        "names one), mode build|plan (plan = read-only analysis/proposal). "
        "build asks the user to CONFIRM on the HUD first: on [CONFIRMATION_PENDING] ask them to confirm. "
        "It runs in the background for minutes; on status=started say it is working and that you will report "
        "when done - never claim results before the report arrives. action=status shows progress; "
        "action=cancel stops it. One job at a time."
    ),
    "brief": "Delegate coding to Claude Code or Codex (run/status/cancel); build mode needs HUD confirmation.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["run", "status", "cancel"]},
        "task": {"type": "STRING", "description": "What to build or change, as specific as the user said"},
        "project_path": {"type": "STRING", "description": "Existing project folder"},
        "project_name": {"type": "STRING", "description": "Name for a new project folder"},
        "engine": {"type": "STRING", "enum": ["claude", "codex"]},
        "mode": {"type": "STRING", "enum": ["build", "plan"]},
    }, "required": ["action"]},
    "handler": coding_agent,
}
