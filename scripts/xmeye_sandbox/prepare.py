"""Stage only reviewed SDK files and official Python into a narrow build context."""
import hashlib
import io
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / '.codex-attachments' / 'xmeye-sandbox-build'
SDK = Path(r'D:\Program Files (x86)\NetSurveillance\CMS')
HASHES = {
    'NetSdk.dll': '90FDA339D0BE68CD6E17006950A7C41019A3C729BA7D00832EFAC76B620C8C55',
    'StreamReader.dll': '56547D2662A7FD158A855C8C82F4AE86F61B34525CA0CF355F263754DD5E9D51',
}


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / 'sdk').mkdir(exist_ok=True)
    for name, digest in HASHES.items():
        data = (SDK / name).read_bytes()
        if hashlib.sha256(data).hexdigest().upper() != digest:
            raise RuntimeError('SDK changed since review: ' + name)
        (STAGE / 'sdk' / name).write_bytes(data)
    url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-win32.zip'
    data = urllib.request.urlopen(url, timeout=30).read()
    if hashlib.sha256(data).hexdigest() != 'daf24de7fb3b173e94e56a201d3f38dfedebbdc7ed1925f7aeb8ed588e2b4189':
        raise RuntimeError('Official Python archive changed since staging review')
    print('Official Python archive SHA256:', hashlib.sha256(data).hexdigest())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        target = STAGE / 'python'
        for member in archive.infolist():
            path = (target / member.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise RuntimeError('Invalid archive path')
        archive.extractall(target)
    for name in ('Dockerfile', 'entry.py', 'worker.py', 'stream.py'):
        shutil.copyfile(Path(__file__).parent / name, STAGE / name)
    print('Build context:', STAGE)


if __name__ == '__main__':
    main()
