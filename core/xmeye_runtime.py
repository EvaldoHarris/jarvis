"""iCSee cloud runtime: disposable SDK containers, no native DLLs on the host."""
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / 'config' / 'xmeye_devices.json'
IMAGE = 'jarvis-xmeye-probe:local'
STATUSES = {'loaded', 'initialized', 'wrong_runtime', 'init_failed', 'login_failed',
            'stream_failed', 'callback_failed', 'received', 'no_frames', 'worker_failed',
            'runtime_failed', 'video_verified', 'received_decode_failed',
            'invalid_result', 'supervisor_failed', 'container_failed', 'timeout', 'controller_failed',
            'awaiting_credentials', 'testing'}


def load_devices(path=None):
    path = Path(path) if path is not None else DEVICES
    try:
        if path.stat().st_size > 200_000:
            return []
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            return []
        devices, seen = [], set()
        for row in data[:256]:
            if not isinstance(row, dict):
                continue
            cloud = row.get('cloud_id')
            name, user = row.get('name'), row.get('username', 'admin')
            if not isinstance(cloud, str) or not re.fullmatch(r'[A-Za-z0-9]{12,32}', cloud):
                continue
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                continue
            if not isinstance(user, str) or not user or len(user.encode()) > 63:
                continue
            if cloud in seen:
                continue
            seen.add(cloud)
            devices.append(dict(name=name.strip(), cloud_id=cloud, username=user))
        return devices
    except (OSError, ValueError):
        return []


def save_device_credentials(request):
    """Explicit local setup action; never share one password across cameras."""
    from memory.config_manager import get_plugin_config, save_plugin_config
    device = validate(dict(request, action='probe'))
    values = dict(get_plugin_config('cameras_locais'))
    serial = device['cloud_id']
    if any(d['cloud_id'] == serial for d in load_devices()):
        prefix = f'icsee_{serial}_'
        values.update({prefix + 'username': device['username'],
                       prefix + 'password': device['password'], prefix + 'stream': str(device['stream'])})
    else:
        values.update(camera1_vendor='icsee', camera1_cloud_id=serial,
                      camera1_username=device['username'], camera1_password=device['password'],
                      camera1_channel=device['channel'] + 1, camera1_stream=str(device['stream']))
    save_plugin_config('cameras_locais', values)


def sanitize(result):
    safe = {'status': result.get('status') if result.get('status') in STATUSES else 'invalid_result'}
    for key in ('sdk_error', 'pointer_bits', 'client_size', 'packet_size', 'frames', 'bytes', 'codec', 'winerror'):
        value = result.get(key)
        if type(value) is int and -(2**31) <= value <= 2**32:
            safe[key] = value
    endpoints = []
    candidates = result.get('tcp_destinations', [])
    for endpoint in (candidates[:64] if isinstance(candidates, list) else []):
        try:
            ip = str(ipaddress.IPv4Address(endpoint['ip']))
            port = int(endpoint['port'])
            if 0 < port < 65536:
                endpoints.append(dict(ip=ip, port=port))
        except (ValueError, KeyError, TypeError):
            continue
    if endpoints:
        safe['tcp_destinations'] = endpoints
    return safe


def validate(request):
    action = request.get('action')
    if action in ('load', 'init'):
        return {'action': action}
    if action not in ('probe', 'live'):
        raise ValueError('Ação inválida.')
    cloud = str(request.get('cloud_id', '')).strip()
    user = str(request.get('username', '')).strip()
    password = str(request.get('password', ''))
    if not re.fullmatch(r'[A-Za-z0-9]{12,32}', cloud):
        raise ValueError('Informe o número de série/Cloud ID do dispositivo.')
    if not user or len(user.encode()) > 63 or len(password.encode()) > 63:
        raise ValueError('Usuário ou senha excede o limite do SDK.')
    channel, stream = int(request.get('channel', 0)), int(request.get('stream', 1))
    if not 0 <= channel < 64 or stream not in (0, 1):
        raise ValueError('Canal ou stream inválido.')
    return dict(action=action, cloud_id=cloud, username=user, password=password,
                channel=channel, stream=stream)


def command(name, network):
    return ['docker', 'run', '--pull=never', '--rm', '-i', '--name', name,
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--user=1000:1000', '--memory=1536m', '--cpus=2', '--pids-limit=160',
            '--log-driver=none', '--network=' + network,
            '--tmpfs=/work:rw,nosuid,nodev,size=768m,uid=1000,gid=1000,mode=700',
            '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777', IMAGE]


def run_probe(request):
    request = validate(request)
    network = 'bridge' if request['action'] == 'probe' else 'none'
    name = 'jarvis-xmeye-' + uuid.uuid4().hex[:16]
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
    try:
        process = subprocess.run(command(name, network), input=json.dumps(request).encode(),
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=100, **flags)
        if process.returncode or len(process.stdout) > 3_000_000:
            return {'status': 'container_failed'}
        result = json.loads(process.stdout)
        if not isinstance(result, dict):
            return {'status': 'invalid_result'}
        safe = sanitize(result)
        image = result.get('jpeg_base64')
        if safe['status'] == 'video_verified' and isinstance(image, str) and len(image) < 2_800_000:
            safe['jpeg_base64'] = image
        return safe
    except subprocess.TimeoutExpired:
        return {'status': 'timeout'}
    except (OSError, ValueError):
        return {'status': 'controller_failed'}
    finally:
        # Remove only this generated container, including after a CLI timeout.
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, **flags)
