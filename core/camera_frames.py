"""Share fresh preview frames without opening a second camera handle."""
import threading
import time

_lock = threading.Lock()
_frame = None
_at = 0.0


def publish(frame):
    global _frame, _at
    with _lock:
        _frame, _at = bytes(frame), time.monotonic()


def latest():
    with _lock:
        return _frame if time.monotonic() - _at < 1.0 else None


def clear():
    global _frame, _at
    with _lock:
        _frame, _at = None, 0.0
