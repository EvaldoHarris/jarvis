"""Exercise the real container decoder/HUD framing offline with synthetic video."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
from core.xmeye_runtime import command

CONTAINER_SCRIPT = r'''
import sys
sys.path.insert(0, '/opt/probe')
import stream, entry
original = stream.subprocess.Popen
fixture = r"""
import json, socket, struct, subprocess
from pathlib import Path
r=json.loads(Path('/work/request.json').read_text())
subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                'color=c=blue:size=320x240:rate=10','-t','2','-threads','1',
                '-c:v','libx264','-pix_fmt','yuv420p','-f','h264','-y','/work/test.h264'],check=True)
b=Path('/work/test.h264').read_bytes()
with socket.create_connection(('127.0.0.1',r['_port'])) as s:
    s.sendall(bytes.fromhex(r['_secret']))
    s.sendall(struct.pack('!II',2,len(b))+b)
"""
def spawn(args, **kwargs):
    if args[0] == 'xvfb-run':
        args = [sys.executable, '-c', fixture]
    return original(args, **kwargs)
stream.subprocess.Popen = spawn
stream.run_live({'action':'live'},entry.clean_video)
'''


def main():
    from PIL import Image
    name = 'jarvis-xmeye-fixture-' + uuid.uuid4().hex[:12]
    args = command(name, 'none')
    args[-1:-1] = ['--entrypoint', 'python3']
    try:
        result = subprocess.run(args + ['-'], input=CONTAINER_SCRIPT.encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
        if result.returncode:
            raise RuntimeError('Container live pipeline failed')
        source = io.BytesIO(result.stdout)
        count = 0
        while header := source.read(4):
            size = struct.unpack('!I', header)[0]
            if not 4 <= size <= 4_000_000:
                raise RuntimeError('Invalid HUD frame size')
            jpeg = source.read(size)
            image = Image.open(io.BytesIO(jpeg))
            image.load()
            if image.size != (960, 720):
                raise RuntimeError('Unexpected image dimensions')
            count += 1
        if count < 5:
            raise RuntimeError('Not enough live frames received')
        print(json.dumps({'status': 'live_pipeline_verified', 'jpeg_frames': count,
                          'network': 'none', 'real_camera': False}))
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)


if __name__ == '__main__':
    main()
