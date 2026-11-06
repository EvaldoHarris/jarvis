"""Railway/Netlify operations using the user's existing CLI login."""
from pathlib import Path
import json
import os
import re
import subprocess
import threading

from core import confirm, outcome
from core.cli_tools import executable, command

INSTALL = {"railway": "npm install -g @railway/cli", "netlify": "npm install -g netlify-cli"}


def _value(p, key, required=False):
    value = str(p.get(key) or "").strip()
    if (required and not value) or (value and not re.fullmatch(r"[\w .:/@-]+", value)) or value.startswith("-"):
        raise ValueError(f"Valor inválido para {key}")
    return value


def build_args(provider, action, p):
    if provider == "railway":
        base = {"login": ["login"], "status": ["status", "--json"],
                "projects": ["list", "--json"], "logs": ["logs", "--lines", "100"],
                "deployments": ["deployment", "list", "--json"],
                "deploy": ["up", "--detach"], "link": ["link", "--project", _value(p, "project", action == "link")]}
        args = base[action][:]
        if action in ("logs", "deployments", "deploy", "link"):
            for key in ("service", "environment"):
                if _value(p, key):
                    args += ["--" + key, _value(p, key)]
        # Refuse Railway's implicit project/service selection during publication.
        if action == "deploy" and not _value(p, "service"):
            raise ValueError("Informe service para publicar no Railway")
        return args
    base = {"login": ["login"], "status": ["status", "--json"],
            "projects": ["sites:list", "--json"], "link": ["link", "--id", _value(p, "project", action == "link")]}
    if action == "deploy":
        site = _value(p, "project", True)
        raw = str(p.get("directory") or "").strip()
        if not raw:
            raise ValueError("Informe directory com a pasta de saída do build")
        directory = (Path(p["project_path"]) / raw).resolve()
        root = Path(p["project_path"]).resolve()
        if not directory.is_dir() or not directory.is_relative_to(root):
            raise ValueError("directory deve ser uma pasta dentro de project_path")
        args = ["deploy", "--site", site, "--dir", str(directory), "--no-build", "--json"]
        if p.get("production") is True:
            args.append("--prod")
        return args
    if action not in base:
        raise ValueError("Esta operação não está disponível para Netlify")
    return base[action]


def _run(provider, action, cmd, folder):
    try:
        result = subprocess.run(cmd, cwd=folder, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=300 if action == "login" else 180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report = (result.stdout + "\n" + result.stderr).strip()
        facts = {}
        if action == "projects" and result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    projects = []
                    for row in data[:100]:
                        if not isinstance(row, dict):
                            continue
                        item = {key: row[key] for key in ("id", "name", "url") if key in row}
                        if isinstance(row.get("workspace"), dict):
                            item["workspace"] = row["workspace"].get("name")
                        for key in ("services", "environments"):
                            if isinstance(row.get(key), dict):
                                item[key] = [edge["node"]["name"] for edge in row[key].get("edges", [])
                                             if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
                                             and edge["node"].get("name")]
                        projects.append(item)
                    facts["project_count"] = len(data)
                    report = json.dumps({"projects": projects, "total": len(data),
                                         "omitted": max(0, len(data) - 100)}, ensure_ascii=False)
            except (ValueError, TypeError, KeyError):
                pass
        if len(report) > 16000:
            report = report[:16000] + "\n[CLI output truncated]"
        status = (outcome.done("cloud_cli", provider=provider, operation=action) if result.returncode == 0
                  else outcome.failed("cloud_cli", "O CLI retornou erro", exit_code=result.returncode))
        if facts:
            status = outcome.done("cloud_cli", provider=provider, operation=action, **facts)
        if action == "deploy" and result.returncode == 0:
            status = outcome.unverified("cloud_cli", "Publicação enviada; consulte o status do deploy", provider=provider)
        return status + "\n" + outcome.untrusted("CLI output (may contain project logs)", report)
    except subprocess.TimeoutExpired:
        return outcome.failed("cloud_cli", "Tempo esgotado; consulte status antes de repetir uma publicação")
    except (OSError, ValueError):
        return outcome.failed("cloud_cli", "Não foi possível iniciar o CLI")


def cloud_cli(parameters=None, player=None, **context):
    p = dict(parameters or {})
    provider = str(p.get("provider", "")).lower().strip()
    action = str(p.get("action", "status")).lower().strip()
    if provider not in INSTALL:
        return outcome.failed("cloud_cli", "Escolha railway ou netlify")
    exe = executable(provider)
    if action == "available":
        return outcome.done("cloud_cli", provider=provider, installed=bool(exe), install=INSTALL[provider])
    if not exe:
        return outcome.failed("cloud_cli", "CLI não instalado", install=INSTALL[provider])
    try:
        if action not in ("login", "status", "projects", "logs", "deployments", "link", "deploy"):
            raise ValueError("Operação inválida")
        raw = str(p.get("project_path") or "").strip()
        if action not in ("login", "projects") and not raw:
            raise ValueError("Informe project_path com a pasta do projeto")
        folder = (Path.home() if action in ("login", "projects") else
                  Path(os.path.expandvars(os.path.expanduser(raw))).resolve())
        if not folder.is_dir():
            raise ValueError("Pasta do projeto não encontrada")
        p["project_path"] = str(folder)
        args = build_args(provider, action, p)
        cmd = command(exe, args)
    except ValueError as exc:
        return outcome.failed("cloud_cli", str(exc))

    def start():
        def work():
            report = _run(provider, action, cmd, folder)
            if player and hasattr(player, "show_content"):
                player.show_content(f"{provider.upper()} / {action}", report)
            if player and hasattr(player, "request_say"):
                player.request_say("Report the CLI result in the user's language, based only on: " + report)
        threading.Thread(target=work, daemon=True, name="cloud-cli").start()
        return outcome.started("cloud_cli", provider=provider, operation=action)

    if action == "deploy":
        if confirm.pending_title():
            return outcome.ask("cloud_cli", "Responda à confirmação pendente no painel")
        return confirm.request("cloud-deploy", f"Publicar no {provider}",
            f"Pasta: {folder}\nComando: {subprocess.list2cmdline(args)}\n"
            "Envia arquivos para o provedor e pode alterar o serviço publicado.", start)
    if action == "login":
        return start()
    report = _run(provider, action, cmd, folder)
    if action == "projects" and player and hasattr(player, "show_content"):
        player.show_content(f"{provider.upper()} / Projetos", report)
    return report


TOOL = {
    "name": "cloud_cli",
    "description": "Access Railway/Netlify accounts directly through local CLIs. For 'conectar ao CLI/CI do Railway' "
        "or 'listar meus projetos', call provider=railway action=projects FIRST to check existing access. "
        "No folder, API key or coding agent is needed to list projects. Do not claim access is impossible without trying. "
        "available checks installation; login opens browser authentication (user completes login); projects lists projects. "
        "status, link, logs (Railway, last 100 lines), deployments (Railway), deploy require project_path. "
        "link requires project ID; deploy Railway requires service; deploy Netlify requires project/site ID and directory "
        "(built output inside project_path), production=true only when user asks to publish to production, otherwise draft. "
        "deploy needs HUD confirmation. Never claim a deployment is healthy until verified. No arbitrary shell commands.",
    "brief": "Access Railway/Netlify directly. Connect/list projects: action=projects, no folder needed. login only if unauthenticated. link/status/logs/deployments/deploy.",
    "parameters": {"type": "OBJECT", "properties": {
        "provider": {"type": "STRING", "enum": ["railway", "netlify"]},
        "action": {"type": "STRING", "enum": ["available", "login", "projects", "status", "link", "logs", "deployments", "deploy"]},
        "project_path": {"type": "STRING"}, "project": {"type": "STRING"},
        "service": {"type": "STRING"}, "environment": {"type": "STRING"},
        "directory": {"type": "STRING"}, "production": {"type": "BOOLEAN"}},
        "required": ["provider", "action"]},
    "handler": cloud_cli,
}
