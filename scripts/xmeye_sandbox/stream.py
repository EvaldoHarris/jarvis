"""Container-only live decoder. Its loopback socket is never published."""
import json
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time


def read_exact(source, size):
    data = bytearray()
    while len(data) < size:
        piece = source.recv(size - len(data))
        if not piece:
            raise EOFError
        data.extend(piece)
    return bytes(data)


def jpeg_frames(pipe):
    buffer = bytearray()
    while True:
        data = pipe.read1(65536)
        if not data:
            return
        buffer.extend(data)
        if len(buffer) > 4_000_000:
            raise ValueError('Frame too large')
        while True:
            start = buffer.find(b'\xff\xd8')
            if start < 0:
                buffer[:] = buffer[-1:]
                break
            end = buffer.find(b'\xff\xd9', start + 2)
            if end < 0:
                if start:
                    del buffer[:start]
                break
            frame = bytes(buffer[start:end + 2])
            del buffer[:end + 2]
            yield frame


def run_live(request, clean_video):
    decoder = worker = None
    connection = None
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    server.settimeout(65)
    request['_port'] = server.getsockname()[1]
    request['_secret'] = secrets.token_hex(32)
    path = Path('/work/request.json')
    path.write_text(json.dumps(request), encoding='utf-8')
    path.chmod(0o600)
    try:
        worker = subprocess.Popen(['xvfb-run', '-a', 'wine', '/opt/python/python.exe',
                                    r'Z:\opt\probe\worker.py'], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        connection, _ = server.accept()
        connection.settimeout(30)
        if not secrets.compare_digest(read_exact(connection, 32), bytes.fromhex(request['_secret'])):
            return
        codec, size = struct.unpack('!II', read_exact(connection, 8))
        if codec not in (2, 5) or not 0 < size <= 4_000_000:
            return
        first = read_exact(connection, size)
        fmt = 'hevc' if codec == 5 else 'h264'
        decoder = subprocess.Popen([
            'ffmpeg', '-v', 'error', '-fflags', '+discardcorrupt+genpts',
            '-analyzeduration', '1000000', '-probesize', '1000000',
            '-f', fmt, '-i', 'pipe:0', '-an', '-vf', 'fps=5,scale=960:-2',
            '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def feed():
            try:
                decoder.stdin.write(clean_video(first))
                decoder.stdin.flush()
                deadline = time.monotonic() + 14400
                while time.monotonic() < deadline:
                    next_codec, count = struct.unpack('!II', read_exact(connection, 8))
                    if next_codec != codec or not 0 < count <= 4_000_000:
                        break
                    decoder.stdin.write(clean_video(read_exact(connection, count)))
                    decoder.stdin.flush()
            except (OSError, EOFError):
                pass
            finally:
                decoder.stdin.close()

        threading.Thread(target=feed, daemon=True).start()
        for frame in jpeg_frames(decoder.stdout):
            sys.stdout.buffer.write(struct.pack('!I', len(frame)) + frame)
            sys.stdout.buffer.flush()
    finally:
        server.close()
        if connection:
            connection.close()
        for process in (decoder, worker):
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)
        path.unlink(missing_ok=True)
