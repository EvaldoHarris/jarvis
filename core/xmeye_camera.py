"""iCSee cloud snapshots and framed live JPEGs from an isolated SDK container."""
import base64
import json
import subprocess
import sys
import uuid

from core.xmeye_runtime import command, run_probe, validate


class CloudCameraUnavailable(RuntimeError):
    """Sanitized connection failure suitable for display in the settings panel."""


def request_for(camera, action='probe'):
    if getattr(sys, 'frozen', False):
        raise RuntimeError('A conexão iCSee exige executar o Jarvis pelo Python e manter o Docker ativo.')
    return validate(dict(action=action, cloud_id=camera.get('cloud_id', ''),
                         username=camera.get('username', ''), password=camera.get('password', ''),
                         channel=int(camera.get('channel', 1)) - 1,
                         stream=camera.get('stream', 1)))


def snapshot(camera):
    result = run_probe(request_for(camera))
    if result.get('status') != 'video_verified':
        code = result.get('sdk_error')
        suffix = f' (código {code})' if type(code) is int else ''
        raise CloudCameraUnavailable(
            'A câmera iCSee não retornou imagem' + suffix + '. '
            'Se for solar/bateria, ela pode estar suspensa: abra o vídeo no aplicativo iCSee, '
            'aguarde a imagem e teste novamente enquanto estiver acordada. '
            'O conector atual não envia o comando de despertar. '
            'Confira também Docker, internet e as credenciais do dispositivo.')
    image = base64.b64decode(result.get('jpeg_base64', ''), validate=True)
    if not image.startswith(b'\xff\xd8') or len(image) > 2_000_000:
        raise RuntimeError('A câmera iCSee retornou uma imagem inválida.')
    return image


class CloudProcess:
    """Popen-like owner that removes the container when the HUD closes."""
    def __init__(self, process, name):
        self.process, self.name = process, name
        self.stdin, self.stdout = process.stdin, process.stdout

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        return self.process.wait(timeout=timeout)

    def kill(self):
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
        try:
            subprocess.run(['docker', 'rm', '-f', self.name], timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        finally:
            if self.process.poll() is None:
                self.process.kill()


def open_live(camera):
    request = request_for(camera, 'live')
    name = 'jarvis-xmeye-live-' + uuid.uuid4().hex[:16]
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
    try:
        process = subprocess.Popen(command(name, 'bridge'), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        raise RuntimeError('Abra o Docker para conectar a câmera iCSee.') from None
    owned = CloudProcess(process, name)
    try:
        owned.stdin.write(json.dumps(request).encode('utf-8'))
        owned.stdin.close()
    except Exception:
        owned.kill()
        owned.wait(timeout=3)
        raise RuntimeError('Não foi possível iniciar a conexão iCSee.') from None
    return owned
