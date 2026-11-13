"""Linux supervisor. Only sanitized results leave the disposable container."""
import base64
import json
import os
import re
import socket
import threading
from pathlib import Path
import subprocess
import sys


def clean_video(data):
    # The SDK can prepend private pseudo-NALs with forbidden_zero_bit=1.
    # Preserve actual H.264/H.265 NALs; do not pass SDK markers to FFmpeg.
    pieces = re.split(b'\x00\x00\x00\x01|\x00\x00\x01', data)
    if len(pieces) < 2:
        return data
    return b''.join(b'\x00\x00\x00\x01' + p for p in pieces[1:] if p and not p[0] & 0x80)


def tcp_destinations():
    """Partial metadata only: IPv4 TCP endpoints, never payloads/credentials."""
    found = set()
    for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        address, port = fields[2].split(':')
        if int(port, 16):
            ip = socket.inet_ntoa(bytes.fromhex(address)[::-1])
            if ip != '127.0.0.1':
                found.add((ip, int(port, 16)))
    return found


def main():
    request = json.loads(sys.stdin.buffer.read(16384))
    if request.get('action') == 'live':
        from stream import run_live
        run_live(request, clean_video)
        return None
    request_file = Path('/work/request.json')
    request_file.write_text(json.dumps(request), encoding='utf-8')
    request_file.chmod(0o600)
    connections = set()
    stopped = threading.Event()

    def observe():
        while not stopped.is_set():
            try:
                if len(connections) < 64:
                    connections.update(tcp_destinations())
            except OSError:
                pass
            stopped.wait(0.2)

    observer = threading.Thread(target=observe, daemon=True)
    observer.start()
    try:
        process = subprocess.run(['xvfb-run', '-a', 'wine', '/opt/python/python.exe',
                                  r'Z:\opt\probe\worker.py'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=75)
        path = Path('/work/result.json')
        if process.returncode or not path.exists() or path.stat().st_size > 4096:
            return {'status': 'runtime_failed'}
        result = json.loads(path.read_text(encoding='utf-8'))
        result = {k: v for k, v in result.items()
                  if k in ('status', 'pointer_bits', 'client_size', 'packet_size',
                           'sdk_error', 'frames', 'bytes', 'codec', 'error_type', 'winerror')}
        result['tcp_destinations'] = [{'ip': ip, 'port': port}
                                      for ip, port in sorted(connections)[:64]]
        if result.get('status') == 'received':
            video = Path('/work/video.bin')
            if video.stat().st_size > 24_000_000:
                return {'status': 'invalid_result'}
            video.write_bytes(clean_video(video.read_bytes()))
            fmt = 'hevc' if result.get('codec') == 5 else 'h264'
            decoded = subprocess.run(['ffmpeg', '-v', 'error', '-f', fmt, '-i', '/work/video.bin',
                                      '-frames:v', '1', '-vf', 'scale=960:-2', '-f', 'image2pipe',
                                      '-vcodec', 'mjpeg', 'pipe:1'], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=12)
            if decoded.returncode == 0 and decoded.stdout.startswith(b'\xff\xd8') and len(decoded.stdout) < 2_000_000:
                result['status'] = 'video_verified'
                result['jpeg_base64'] = base64.b64encode(decoded.stdout).decode('ascii')
            else:
                result['status'] = 'received_decode_failed'
        return result
    finally:
        stopped.set()
        observer.join(timeout=1)
        request_file.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        result = main()
    except Exception as exc:
        result = {'status': 'supervisor_failed', 'error_type': type(exc).__name__}
    if result is not None:
        print(json.dumps(result), flush=True)
