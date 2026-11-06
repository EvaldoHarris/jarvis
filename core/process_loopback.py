"""WASAPI process loopback: exclude this process tree (Windows build 20348+).

Uses Microsoft's ApplicationLoopback API. No microphone and no system-mix fallback.
All COM audio operations belong to the capture thread; activation is asynchronous.
"""
from __future__ import annotations

import ctypes as C
import os
import sys
import threading
import uuid

HRESULT = C.c_long
UINT = C.c_uint32
PTR = C.c_void_p
_PENDING = []  # Keep timed-out async callbacks alive until Windows releases them.


class GUID(C.Structure):
    _fields_ = [("data", C.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


class WaveFormat(C.Structure):
    _pack_ = 1
    _fields_ = [("tag", C.c_uint16), ("channels", C.c_uint16), ("rate", UINT),
                ("bytes_per_second", UINT), ("align", C.c_uint16),
                ("bits", C.c_uint16), ("extra", C.c_uint16)]


class Blob(C.Structure):
    _fields_ = [("size", UINT), ("data", PTR)]


class PropVariant(C.Structure):
    _fields_ = [("vt", C.c_uint16), ("reserved", C.c_uint16 * 3), ("blob", Blob)]


def _check(hr):
    if hr < 0:
        raise OSError(f"WASAPI HRESULT 0x{hr & 0xffffffff:08X}")


def _method(pointer, index, result, *types):
    table = C.cast(pointer, C.POINTER(C.POINTER(PTR))).contents
    return C.WINFUNCTYPE(result, PTR, *types)(table[index])


def _release(pointer):
    if pointer:
        _method(pointer, 2, UINT)(pointer)


class ProcessLoopback:
    rate = 44100
    channels = 2

    def __init__(self, exclude_pid=None):
        self.pid = exclude_pid or os.getpid()
        self.client, self.capture, self.operation = PTR(), PTR(), PTR()
        self.event = None
        self._com = False
        self._activation = threading.Event()
        self._activation_error = None
        self._refs = 1
        self._abandoned = False
        self._activation_lock = threading.Lock()

    def __enter__(self):
        if sys.platform != "win32" or sys.getwindowsversion().build < 20348:
            raise RuntimeError("Excluir a voz do Jarvis requer Windows build 20348 ou posterior.")
        self.ole = C.WinDLL("ole32")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateEventW.argtypes = [PTR, C.c_int, C.c_int, C.c_wchar_p]
        self.kernel.CreateEventW.restype = PTR
        self.kernel.CloseHandle.argtypes = [PTR]
        self.kernel.WaitForSingleObject.argtypes = [PTR, UINT]
        self.kernel.WaitForSingleObject.restype = UINT
        _check(self.ole.CoInitializeEx(None, 0))  # MTA
        self._com = True
        try:
            self._activate()
            fmt = WaveFormat(1, self.channels, self.rate, self.rate * 4, 4, 16, 0)
            # shared, loopback + event callback + automatic PCM conversion
            _check(_method(self.client, 3, HRESULT, C.c_int, UINT, C.c_int64, C.c_int64,
                           C.POINTER(WaveFormat), PTR)(
                self.client, 0, 0x80060000, 0, 0, C.byref(fmt), None))
            iid = GUID("C8ADBD64-E71E-48A0-A4DE-185C395CD317")
            _check(_method(self.client, 14, HRESULT, C.POINTER(GUID), C.POINTER(PTR))(
                self.client, C.byref(iid), C.byref(self.capture)))
            self.event = self.kernel.CreateEventW(None, False, False, None)
            if not self.event:
                raise C.WinError(C.get_last_error())
            _check(_method(self.client, 13, HRESULT, PTR)(self.client, self.event))
            _check(_method(self.client, 10, HRESULT)(self.client))
            return self
        except Exception:
            self.close()
            raise

    def _activate(self):
        iid = GUID("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")
        accepted = {uuid.UUID(v).bytes_le for v in (
            "00000000-0000-0000-C000-000000000046",  # IUnknown
            "41D949AB-9862-444A-80F6-C261334DA5EB",  # completion handler
            "94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90",  # IAgileObject
        )}
        query_type = C.WINFUNCTYPE(HRESULT, PTR, C.POINTER(GUID), C.POINTER(PTR))
        ref_type = C.WINFUNCTYPE(UINT, PTR)
        done_type = C.WINFUNCTYPE(HRESULT, PTR, PTR)

        def query(this, requested, out):
            if bytes(requested.contents.data) in accepted:
                out[0] = this
                self._refs += 1
                return 0
            out[0] = None
            return -2147467262  # E_NOINTERFACE

        def addref(this):
            self._refs += 1
            return self._refs

        def release(this):
            self._refs -= 1
            return self._refs

        def done(this, operation):
            unknown = PTR()
            activated = PTR()
            try:
                hr = HRESULT()
                _check(_method(operation, 3, HRESULT, C.POINTER(HRESULT), C.POINTER(PTR))(
                    operation, C.byref(hr), C.byref(unknown)))
                _check(hr.value)
                _check(_method(unknown, 0, HRESULT, C.POINTER(GUID), C.POINTER(PTR))(
                    unknown, C.byref(iid), C.byref(activated)))
                with self._activation_lock:
                    if self._abandoned:
                        _release(activated)
                    else:
                        self.client = activated
            except Exception as exc:
                self._activation_error = exc
            finally:
                _release(unknown)
                self._activation.set()
            return 0

        self._callbacks = (query_type(query), ref_type(addref), ref_type(release), done_type(done))
        self._vtable = (PTR * 4)(*[C.cast(fn, PTR).value for fn in self._callbacks])
        self._handler = C.pointer(C.cast(self._vtable, C.POINTER(PTR)))
        self._params = (UINT * 3)(1, self.pid, 1)  # process loopback, pid, exclude tree
        self._prop = PropVariant(65, (C.c_uint16 * 3)(), Blob(12, C.cast(self._params, PTR)))
        activate = C.WinDLL("Mmdevapi").ActivateAudioInterfaceAsync
        activate.argtypes = [C.c_wchar_p, C.POINTER(GUID), C.POINTER(PropVariant), PTR, C.POINTER(PTR)]
        activate.restype = HRESULT
        _check(activate("VAD\\Process_Loopback", C.byref(iid), C.byref(self._prop),
                        C.cast(self._handler, PTR), C.byref(self.operation)))
        if not self._activation.wait(10):
            with self._activation_lock:
                self._abandoned = True
            _PENDING.append(self)
            raise TimeoutError("O Windows não ativou a captura por processo em 10 segundos.")
        if self._activation_error:
            raise self._activation_error

    def packets(self, stop):
        while not stop.is_set():
            waited = self.kernel.WaitForSingleObject(self.event, 100)
            if waited == 0xffffffff:
                raise C.WinError(C.get_last_error())
            size = UINT()
            while not stop.is_set():
                _check(_method(self.capture, 5, HRESULT, C.POINTER(UINT))(self.capture, C.byref(size)))
                if not size.value:
                    break
                data, frames, flags = PTR(), UINT(), UINT()
                _check(_method(self.capture, 3, HRESULT, C.POINTER(PTR), C.POINTER(UINT),
                               C.POINTER(UINT), PTR, PTR)(
                    self.capture, C.byref(data), C.byref(frames), C.byref(flags), None, None))
                try:
                    count = frames.value * self.channels * 2
                    block = bytes(count) if flags.value & 2 else C.string_at(data, count)
                finally:
                    _check(_method(self.capture, 4, HRESULT, UINT)(self.capture, frames.value))
                yield block

    def close(self):
        with self._activation_lock:
            client, self.client = self.client, PTR()
        if client:
            _method(client, 11, HRESULT)(client)
        _release(self.capture)
        self.capture = PTR()
        _release(client)
        _release(self.operation)
        self.operation = PTR()
        if self.event:
            self.kernel.CloseHandle(self.event)
            self.event = None
        if self._com:
            self.ole.CoUninitialize()
            self._com = False

    def __exit__(self, *args):
        self.close()
