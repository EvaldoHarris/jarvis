"""Start the installed Docker Desktop without blocking the Jarvis interface."""
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


def desktop_path():
    cli = shutil.which('docker')
    candidates = []
    if cli:
        candidates.append(Path(cli).resolve().parents[2] / 'Docker Desktop.exe')
    candidates.append(Path(os.environ.get('ProgramFiles', r'C:\Program Files')) /
                      'Docker' / 'Docker' / 'Docker Desktop.exe')
    return next((p for p in candidates if p.is_file()), None)


def engine_ready():
    try:
        return subprocess.run(
            ['docker', 'info', '--format', '{{.ServerVersion}}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_docker(log, timeout=120):
    if os.name != 'nt' or engine_ready():
        return
    executable = desktop_path()
    if executable is None:
        log('SYS: Docker Desktop não encontrado. Instale-o para usar as câmeras iCSee.')
        return
    try:
        # Docker Desktop is single-instance; starting it also wakes an existing
        # Desktop whose engine is stopped. No elevation or service changes.
        subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        log('SYS: Iniciando Docker para as câmeras iCSee…')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if engine_ready():
                log('SYS: Docker pronto para conectar as câmeras iCSee.')
                return
            time.sleep(2)
        log('SYS: Docker ainda indisponível. Confira o Docker Desktop antes de conectar as câmeras.')
    except OSError:
        log('SYS: Não foi possível iniciar o Docker Desktop automaticamente.')


def start_in_background(log):
    thread = threading.Thread(target=ensure_docker, args=(log,), daemon=True,
                              name='docker-startup')
    thread.start()
    return thread
