"""Local diagnostic events only: no audio, transcripts, keys or tool arguments."""
import logging
import threading
from logging.handlers import RotatingFileHandler

_logger = None
_lock = threading.Lock()


def record(event):
    global _logger
    try:
        with _lock:
            if _logger is None:
                from memory.config_manager import get_base_dir
                folder = get_base_dir() / "logs"
                folder.mkdir(exist_ok=True)
                logger = logging.getLogger("jarvis.voice.health")
                logger.setLevel(logging.INFO)
                logger.propagate = False
                handler = RotatingFileHandler(folder / "voice-health.log", maxBytes=131072,
                                              backupCount=2, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                logger.addHandler(handler)
                _logger = logger
            _logger.info(event)
    except Exception:
        pass  # diagnostics must never interrupt speech
