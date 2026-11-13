"""Local event recordings: 24-hour retention, 1 GB total and 50 MB per event."""
import json
from pathlib import Path
import re
import struct
import threading
import time
from memory.config_manager import get_base_dir

ROOT = get_base_dir() / 'data' / 'monitor_recordings'
MAX_TOTAL = 1_000_000_000
MAX_EVENT = 50_000_000
RETENTION = 24 * 3600
LOCK = threading.RLock()


def valid(key):
    if not isinstance(key, str) or not re.fullmatch(r'monitor_[a-f0-9]{24}', key):
        raise ValueError('Identificador de gravação inválido.')
    return key


def prune():
    with LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        groups = {}
        for path in ROOT.iterdir():
            if path.suffix in ('.json', '.frames') and re.fullmatch(r'monitor_[a-f0-9]{24}', path.stem):
                groups.setdefault(path.stem, []).append(path)
        entries = [(max(p.stat().st_mtime for p in files), sum(p.stat().st_size for p in files), files)
                   for files in groups.values()]
        total = sum(size for _, size, _ in entries)
        for updated, size, files in sorted(entries, key=lambda item: item[0]):
            if time.time() - updated > RETENTION or total > MAX_TOTAL:
                for path in files:
                    path.unlink(missing_ok=True)
                total -= size


def append(packet, image):
    key = valid(packet['alert_id'])
    with LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        meta, video = ROOT / (key + '.json'), ROOT / (key + '.frames')
        if not meta.exists():
            meta.write_text(json.dumps({k: packet[k] for k in ('alert_id', 'group', 'camera', 'labels', 'time')},
                                       ensure_ascii=False), encoding='utf-8')
        if image and len(image) <= 700_000:
            size = video.stat().st_size if video.exists() else 0
            if size + len(image) + 12 <= MAX_EVENT:
                with video.open('ab') as stream:
                    stream.write(struct.pack('!dI', float(packet['offset']), len(image)))
                    stream.write(image)
        if packet.get('final'):
            prune()


def list_recordings():
    with LOCK:
        prune()
        result = []
        for path in ROOT.glob('monitor_*.json'):
            try:
                valid(path.stem)
                if path.stat().st_size > 10000 or not path.with_suffix('.frames').exists():
                    continue
                row = json.loads(path.read_text(encoding='utf-8'))
                row['alert_id'] = path.stem
                result.append(row)
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda row: row.get('time', ''), reverse=True)


def load(key):
    with LOCK:
        prune()
        path = ROOT / (valid(key) + '.frames')
        if path.stat().st_size > MAX_EVENT:
            raise ValueError('Gravação maior que o limite permitido.')
        frames = []
        with path.open('rb') as stream:
            while header := stream.read(12):
                if len(header) != 12:
                    break
                offset, size = struct.unpack('!dI', header)
                if not 4 <= size <= 700_000:
                    break
                image = stream.read(size)
                if len(image) != size:
                    break
                frames.append((offset, image))
        return frames
