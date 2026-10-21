"""Bounded RTSP snapshot worker; credentials travel via stdin, never argv/logs."""
import ipaddress
import json
import os
import subprocess
import sys
import struct
import time
from urllib.parse import quote


def build_url(camera):
    host = str(camera.get("host", "")).strip()
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise ValueError("Informe o endereço IPv4 local da câmera.") from None
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("Use um endereço privado da rede local.")
    user = str(camera.get("username", "")).strip()
    password = str(camera.get("password", ""))
    if not user or not password:
        raise ValueError("Preencha usuário e senha da câmera nas configurações locais do plugin.")
    port = int(camera.get("port") or 554)
    channel = int(camera.get("channel") or 1)
    stream = int(camera.get("stream", 1))
    if not 1 <= port <= 65535 or not 1 <= channel <= 64 or stream not in (0, 1):
        raise ValueError("Porta, canal ou stream inválido.")
    user, password = quote(user, safe=""), quote(password, safe="")
    vendor = camera.get("vendor", "icsee")
    base = f"rtsp://{host}:{port}"
    if vendor == "icsee":
        return f"{base}/user={user}&password={password}&channel={channel}&stream={stream}.sdp"
    if vendor == "intelbras":
        return f"rtsp://{user}:{password}@{host}:{port}/cam/realmonitor?channel={channel}&subtype={stream}"
    raise ValueError("Tipo de câmera não suportado. Use icsee ou intelbras.")


def snapshot(camera):
    from memory.config_manager import get_base_dir

    url = build_url(camera)
    if getattr(sys, "frozen", False):
        raise RuntimeError("Nesta versão, o acesso RTSP exige executar o Jarvis pelo Python.")
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "core.rtsp_capture"],
            input=json.dumps({"url": url}).encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12, cwd=str(get_base_dir()), **flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("A câmera não enviou imagem em até 12 segundos. Confira IP, rede e RTSP.") from None
    if result.returncode or not result.stdout.startswith(b"\xff\xd8"):
        raise RuntimeError(
            "Não foi possível obter vídeo. Confira usuário/senha do dispositivo, "
            "RTSP habilitado, canal e stream. Nenhuma outra senha foi tentada.")
    return result.stdout


def _worker():
    # FFmpeg may print credential-bearing URLs on failure. The parent discards
    # this process's stderr, including messages from native libraries.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    import cv2
    payload = json.loads(sys.stdin.buffer.read(16384))
    cap = cv2.VideoCapture()
    try:
        opened = cap.open(payload["url"], cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000,
        ])
        if not opened:
            return 2
        if payload.get("live"):
            last = 0.
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    return 3
                now = time.monotonic()
                if now - last < .1:
                    continue
                last = now
                height, width = frame.shape[:2]
                scale = min(1., 1280 / width, 720 / height)
                if scale < 1:
                    frame = cv2.resize(frame, (int(width*scale), int(height*scale)))
                ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    data = jpeg.tobytes()
                    sys.stdout.buffer.write(struct.pack("!I", len(data)) + data)
                    sys.stdout.buffer.flush()
        ok, frame = cap.read()
        if not ok or frame is None:
            return 3
        height, width = frame.shape[:2]
        scale = min(1., 1920 / width, 1080 / height)
        if scale < 1:
            frame = cv2.resize(frame, (int(width*scale), int(height*scale)))
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            return 4
        sys.stdout.buffer.write(jpeg.tobytes())
        return 0
    finally:
        cap.release()


if __name__ == "__main__":
    try:
        status = _worker()
    except Exception:
        status = 1
    raise SystemExit(status)
