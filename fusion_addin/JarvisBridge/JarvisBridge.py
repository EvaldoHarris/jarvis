"""
JarvisBridge — add-in do Autodesk Fusion que recebe código Python do JARVIS.

Escuta SOMENTE em 127.0.0.1:27183. Cada conexão envia uma linha JSON
{"code": "..."} e recebe uma linha JSON {"ok": bool, "result": str, "output": str}.

A API do Fusion só pode ser usada na thread principal, então o servidor (thread
de fundo) dispara um CustomEvent e espera o handler executar o código.
"""

import adsk.core
import adsk.fusion
import contextlib
import io
import json
import socket
import threading
import traceback
import uuid

HOST, PORT = "127.0.0.1", 27183
EVENT_ID = "JarvisBridgeExecEvent"
TIMEOUT = 120

_app = None
_ui = None
_event = None
_handlers = []
_server_sock = None
_running = False
_pending: dict = {}      # req_id -> {"code", "done": Event, "resp"}


class _ExecHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        req = _pending.get(args.additionalInfo)
        if not req:
            return
        out = io.StringIO()
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            ns = {
                "adsk": adsk, "app": _app, "ui": _ui, "design": design,
                "root": design.rootComponent if design else None,
                "result": None,
            }
            with contextlib.redirect_stdout(out):
                exec(req["code"], ns)
            req["resp"] = {"ok": True, "result": str(ns.get("result")),
                           "output": out.getvalue()[-4000:]}
        except Exception:
            req["resp"] = {"ok": False, "result": traceback.format_exc()[-3000:],
                           "output": out.getvalue()[-2000:]}
        finally:
            req["done"].set()


def _serve():
    global _server_sock
    _server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_sock.bind((HOST, PORT))
    _server_sock.listen(4)
    while _running:
        try:
            conn, _ = _server_sock.accept()
        except OSError:
            break
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


def _handle(conn):
    with conn:
        try:
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            msg = json.loads(buf.decode("utf-8") or "{}")
            if msg.get("ping"):
                resp = {"ok": True, "result": "pong"}
            else:
                rid = uuid.uuid4().hex
                req = {"code": msg.get("code", ""), "done": threading.Event(), "resp": None}
                _pending[rid] = req
                _app.fireCustomEvent(EVENT_ID, rid)
                if req["done"].wait(TIMEOUT):
                    resp = req["resp"]
                else:
                    resp = {"ok": False, "result": "Tempo esgotado no Fusion."}
                _pending.pop(rid, None)
        except Exception:
            resp = {"ok": False, "result": traceback.format_exc()[-2000:]}
        conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))


def run(context):
    global _app, _ui, _event, _running
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _event = _app.registerCustomEvent(EVENT_ID)
        h = _ExecHandler()
        _event.add(h)
        _handlers.append(h)
        _running = True
        threading.Thread(target=_serve, daemon=True).start()
    except Exception:
        if _ui:
            _ui.messageBox("JarvisBridge falhou:\n" + traceback.format_exc())


def stop(context):
    global _running
    _running = False
    try:
        if _server_sock:
            _server_sock.close()
        if _event:
            for h in _handlers:
                _event.remove(h)
        _app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
