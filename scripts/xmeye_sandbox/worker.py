"""Runs only inside Wine in the disposable container, never on the host."""
import ctypes as C
import json
import os
import queue
import socket
import struct
from pathlib import Path
import threading
import time


class Client(C.Structure):
    _fields_ = [(n, C.c_int32) for n in ("channel", "stream", "mode", "com_type")] + [("window", C.c_void_p)]


class Packet(C.Structure):
    _fields_ = [("kind", C.c_int32), ("buffer", C.c_void_p),
                ("size", C.c_uint32), ("codec", C.c_uint32)]
    _fields_ += [(n, C.c_uint32) for n in ("year", "month", "day", "hour", "minute", "second",
                                          "timestamp", "timestamp_high", "frame", "fps")]
    _fields_ += [("width", C.c_uint16), ("height", C.c_uint16), ("reserved", C.c_uint32 * 6)]


def probe(request):
    if os.name != "nt" or C.sizeof(C.c_void_p) != 4:
        return {"status": "wrong_runtime"}
    # No generic arbitrary DLL path or callable exports from user input.
    directory = r"Z:\opt\sdk"
    os.chdir(directory)
    dll_dir = os.add_dll_directory(directory)
    sdk = C.WinDLL(directory + r"\NetSdk.dll")
    result = {"status": "loaded", "pointer_bits": 32,
              "client_size": C.sizeof(Client), "packet_size": C.sizeof(Packet)}
    if request.get("action") == "load":
        return result
    callback_type = C.WINFUNCTYPE(C.c_int32, C.c_int32, C.POINTER(Packet), C.c_int32)
    signatures = {
        "H264_DVR_Init": ([C.c_void_p, C.c_uint32], C.c_int32),
        "H264_DVR_SetConnectTime": ([C.c_int32, C.c_int32], C.c_bool),
        "H264_DVR_Login_Cloud": ([C.c_char_p, C.c_uint16, C.c_char_p, C.c_char_p,
                                  C.c_void_p, C.POINTER(C.c_int32), C.c_char_p], C.c_int32),
        "H264_DVR_RealPlay": ([C.c_int32, C.POINTER(Client)], C.c_int32),
        "H264_DVR_SetRealDataCallBack_V2": ([C.c_int32, callback_type, C.c_int32], C.c_bool),
        "H264_DVR_DelRealDataCallBack_V2": ([C.c_int32, callback_type, C.c_int32], C.c_bool),
        "H264_DVR_StopRealPlay": ([C.c_int32, C.c_void_p], C.c_bool),
        "H264_DVR_Logout": ([C.c_int32], C.c_int32),
        "H264_DVR_Cleanup": ([], C.c_bool),
        "H264_DVR_GetLastError": ([], C.c_int32),
    }
    for name, (args, returns) in signatures.items():
        fn = getattr(sdk, name)
        fn.argtypes, fn.restype = args, returns
    login = handle = 0
    callback = None
    frames, byte_count, codec = 0, 0, 0
    ready = threading.Event()
    lock = threading.Lock()
    accepting = True
    live = request.get('action') == 'live'
    packets = queue.Queue(maxsize=32)
    sender = None
    connection = None
    try:
        if sdk.H264_DVR_Init(None, 0) <= 0:
            return {"status": "init_failed", "sdk_error": sdk.H264_DVR_GetLastError()}
        if request.get("action") == "init":
            return dict(result, status="initialized")
        sdk.H264_DVR_SetConnectTime(12000, 1)
        time.sleep(4)
        # Overallocated output storage: do not depend on the newer header's
        # DEVICEINFO layout when loading this older SDK build.
        info, error = C.create_string_buffer(16384), C.c_int32()
        login = sdk.H264_DVR_Login_Cloud(request["cloud_id"].encode(), 34567,
                                        request["username"].encode(), request["password"].encode(),
                                        info, C.byref(error), b"")
        if login <= 0:
            return {"status": "login_failed", "sdk_error": error.value}
        if live:
            connection = socket.create_connection(('127.0.0.1', request['_port']), timeout=15)
            connection.sendall(bytes.fromhex(request['_secret']))

            def send_packets():
                try:
                    while True:
                        packet = packets.get()
                        if packet is None:
                            break
                        connection.sendall(packet)
                except OSError:
                    ready.set()

            sender = threading.Thread(target=send_packets, daemon=True)
            sender.start()
        client = Client(request.get("channel", 0), request.get("stream", 1), 0, 0, None)
        handle = sdk.H264_DVR_RealPlay(login, C.byref(client))
        if handle <= 0:
            return {"status": "stream_failed", "sdk_error": sdk.H264_DVR_GetLastError()}
        with open('NUL' if live else r"Z:\work\video.bin", "wb") as video:
            def receive(_handle, pointer, _user):
                nonlocal frames, byte_count, codec
                try:
                    p = pointer.contents
                    if p.kind not in (1, 2, 3, 4, 5) or p.codec not in (2, 5):
                        return 0
                    if not p.buffer or not 0 < p.size <= 4_000_000:
                        return 0
                    with lock:
                        if not accepting:
                            return 0
                        if not live and byte_count + p.size > 24_000_000:
                            ready.set()
                            return 0
                        data = C.string_at(p.buffer, p.size)
                        if live:
                            try:
                                packets.put_nowait(struct.pack('!II', p.codec, len(data)) + data)
                            except queue.Full:
                                return 0
                        else:
                            video.write(data)
                        frames += 1
                        byte_count += p.size
                        codec = p.codec
                        if not live and frames >= 100:
                            ready.set()
                except Exception:
                    ready.set()
                return 0
            callback = callback_type(receive)
            if not sdk.H264_DVR_SetRealDataCallBack_V2(handle, callback, 0):
                return {"status": "callback_failed", "sdk_error": sdk.H264_DVR_GetLastError()}
            ready.wait(14400 if live else 12)
            sdk.H264_DVR_DelRealDataCallBack_V2(handle, callback, 0)
            # Synchronize the writer before closing the stream file.
            with lock:
                accepting = False
                video.flush()
        return {"status": "received" if frames else "no_frames", "frames": frames,
                "bytes": byte_count, "codec": codec}
    finally:
        if connection:
            connection.close()
        if handle > 0:
            sdk.H264_DVR_StopRealPlay(handle, None)
        if login > 0:
            sdk.H264_DVR_Logout(login)
        sdk.H264_DVR_Cleanup()
        dll_dir.close()


if __name__ == "__main__":
    try:
        request = json.loads(Path(r"Z:\work\request.json").read_text(encoding="utf-8"))
        result = probe(request)
    except Exception as exc:
        # Never include exception text, SDK logs, identifiers or passwords.
        result = {"status": "worker_failed", "error_type": type(exc).__name__,
                  "winerror": getattr(exc, "winerror", None)}
    Path(r"Z:\work\result.json").write_text(json.dumps(result), encoding="utf-8")
