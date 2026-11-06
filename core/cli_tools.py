"""Find locally installed CLIs without downloading or invoking a package runner."""
import os
import shutil
from pathlib import Path


def executable(name):
    if name == "codex":
        bundled = sorted((Path.home() / ".vscode/extensions").glob(
            "openai.chatgpt-*/bin/windows-x86_64/codex.exe"), reverse=True)
        if bundled:
            return str(bundled[0])
    found = shutil.which(name + ".exe") or shutil.which(name + ".cmd") or shutil.which(name)
    if found:
        return found
    for root in [Path(os.environ.get("APPDATA", str(Path.home()))) / "npm",
                 Path.home() / ".local/bin",
                 Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs/OpenAI/Codex/bin"]:
        for suffix in (".exe", ".cmd", ""):
            path = root / (name + suffix)
            if path.is_file():
                return str(path)
    return None


def command(exe, args):
    # npm's Windows shim is a batch file. Use node + its installed entry point
    # instead: arguments never pass through cmd.exe (which interprets & and %).
    if os.name == "nt" and Path(exe).suffix.lower() == ".cmd":
        entries = {"railway": "@railway/cli/bin/railway.js",
                   "netlify": "netlify-cli/bin/run.js",
                   "codex": "@openai/codex/bin/codex.js"}
        entry = Path(exe).parent / "node_modules" / entries.get(Path(exe).stem.lower(), "missing")
        node = shutil.which("node")
        if not node or not entry.is_file():
            raise ValueError("Instalação npm incompleta; reinstale o CLI ou use o executável nativo.")
        return [node, str(entry), *args]
    return [exe, *args]
