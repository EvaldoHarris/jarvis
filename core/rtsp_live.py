"""One local live RTSP session; isolated decoder, bounded startup and clean stop."""
import atexit
import json
import os
import struct
import subprocess
import sys
import threading

from core.rtsp_capture import build_url


def _read_exact(pipe, size):
    data = bytearray()
    while len(data) < size:
        chunk = pipe.read(size - len(data))
        if not chunk:
            raise EOFError("Video stream ended")
        data.extend(chunk)
    return bytes(data)


class LiveCamera:
    def __init__(self):
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._process = None
        self._generation = 0

    def stop(self):
        with self._lock:
            self._generation += 1
            process, self._process = self._process, None
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)

    def start(self, camera, emit):
        with self._start_lock:
            return self._start(camera, emit)

    def _start(self, camera, emit):
        from memory.config_manager import get_base_dir
        url = build_url(camera)
        if getattr(sys, "frozen", False):
            raise RuntimeError("RTSP requires Python installation")
        with self._lock:
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            process = subprocess.Popen(
                [sys.executable, "-m", "core.rtsp_capture"], cwd=str(get_base_dir()),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **flags)
            previous_generation = self._generation
            generation = previous_generation + 1
            ready = threading.Event()
            received = []
            title = f"{camera['name']} - canal {camera['channel']}"

            def consume():
                try:
                    process.stdin.write(json.dumps({"url": url, "live": True}).encode())
                    process.stdin.close()
                    while True:
                        size = struct.unpack("!I", _read_exact(process.stdout, 4))[0]
                        if not 4 <= size <= 4_000_000:
                            raise ValueError("Invalid video frame")
                        frame = _read_exact(process.stdout, size)
                        if not frame.startswith(b"\xff\xd8"):
                            raise ValueError("Invalid JPEG")
                        with self._lock:
                            if not received:
                                if previous_generation != self._generation:
                                    return
                                self.stop()
                                self._process = process
                                emit((generation, "start", title))
                                received.append(True)
                            elif generation != self._generation:
                                return
                            emit((generation, "frame", frame))
                        ready.set()
                except Exception:
                    pass  # Never expose credential-bearing decoder errors.
                finally:
                    ready.set()
                    with self._lock:
                        if self._process is process and generation == self._generation:
                            emit((generation, "end", None))
                            self.stop()
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    if not process.stdin.closed:
                        process.stdin.close()
                    process.stdout.close()

            threading.Thread(target=consume, daemon=True, name="rtsp-live").start()
        if not ready.wait(12) or not received:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            raise RuntimeError("No live image received")
        return generation


live_camera = LiveCamera()
atexit.register(live_camera.stop)
