"""Encontra a pasta local do código de um produto, sem configuração fixa.

1. Descobre repositórios git nas pastas de código do usuário.
2. Pontua cada um contra pistas (nome do produto, host da issue, palavras do título)
   olhando o nome da pasta, a pasta-mãe e o remote do git.
3. Lembra a escolha confirmada pelo usuário (config/code_projects.json) e a usa
   primeiro da próxima vez.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MEMORY = BASE / "config" / "code_projects.json"
_cache: tuple[float, list[dict]] | None = None


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _norm(text)) if len(t) >= 3}


def roots() -> list[Path]:
    home = Path.home()
    found = [BASE.parent, home / "Documents" / "GitHub", home / "Documentos" / "GitHub",
             home / "source" / "repos", home / "projects", home / "dev", home / "Desktop"]
    extra = os.environ.get("JARVIS_CODE_ROOTS", "")
    found += [Path(p) for p in extra.split(os.pathsep) if p.strip()]
    out, seen = [], set()
    for r in found:
        try:
            key = r.resolve()
        except OSError:
            continue
        if r.is_dir() and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def discover(max_age: float = 3600) -> list[dict]:
    """Repositórios git até 3 níveis abaixo de cada raiz (cache de 1 h)."""
    global _cache
    if _cache and time.time() - _cache[0] < max_age:
        return _cache[1]
    repos, seen = [], set()
    skip = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build"}
    for root in roots():
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if ".git" in dirnames:
                path = Path(dirpath)
                if path.resolve() not in seen:
                    seen.add(path.resolve())
                    repos.append({"path": str(path), "remote": _remote(path)})
                dirnames[:] = []           # não entra em repositórios aninhados
                continue
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")] if depth < 3 else []
    _cache = (time.time(), repos)
    return repos


def _remote(path: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"], capture_output=True,
                           text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip()
    except Exception:
        return ""


def _load() -> dict:
    try:
        return json.loads(MEMORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember(product: str, path: str) -> None:
    data = _load()
    data[_norm(product).strip()] = path
    MEMORY.parent.mkdir(parents=True, exist_ok=True)
    MEMORY.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find(product: str, hints: str = "") -> tuple[str | None, list[str]]:
    """(pasta escolhida ou None, candidatas em ordem). None = ambíguo/sem pista."""
    learned = _load().get(_norm(product).strip())
    if learned and Path(learned).is_dir():
        return learned, [learned]
    want = _tokens(product)
    extra = _tokens(hints) - {"https", "http", "www", "com", "app", "issues", "net", "br"}
    scored = []
    for repo in discover():
        p = Path(repo["path"])
        name = _tokens(p.name)
        around = _tokens(p.parent.name) | _tokens(repo["remote"])
        score = 3 * len(want & name) + 1 * len(want & around) + 1 * len(extra & name) + 0.5 * len(extra & around)
        if _norm(product).strip() and _norm(product).strip() == _norm(p.name):
            score += 3
        if score > 0:
            scored.append((score, repo["path"]))
    scored.sort(key=lambda s: -s[0])
    candidates = [p for _, p in scored[:5]]
    if not scored:
        return None, []
    if len(scored) == 1 or scored[0][0] >= scored[1][0] + 1:
        return scored[0][1], candidates
    return None, candidates
