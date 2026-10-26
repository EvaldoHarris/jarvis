"""Explicit Windows window/monitor selection, verified layout and guarded undo."""
import ctypes
import json
import secrets
import threading
import time
from ctypes import wintypes

from core import outcome, appidentity
from core.undo import push_undo

_lock = threading.Lock()
_observed = None


def monitors():
    class Info(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
    areas = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    ctypes.windll.user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(Info)]
    ctypes.windll.user32.GetMonitorInfoW.restype = wintypes.BOOL
    ctypes.windll.user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    ctypes.windll.user32.EnumDisplayMonitors.restype = wintypes.BOOL
    def visit(handle, dc, rect, extra):
        info = Info(); info.size = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.work
            areas.append({'id': len(areas) + 1, 'work': [r.left, r.top, r.right, r.bottom], 'primary': bool(info.flags & 1)})
        return True
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(visit), 0)
    return areas


def windows():
    from pywinauto import Desktop
    own = appidentity.own_pids()
    return [w for w in Desktop(backend='win32').windows() if w.is_visible() and not w.is_minimized() and w.window_text().strip() and w.process_id() not in own]


def bounds(window):
    r = window.rectangle()
    return [r.left, r.top, r.right, r.bottom]


def layout_rect(area, position):
    left, top, right, bottom = area
    mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
    choices = {'full': [left, top, right, bottom], 'left': [left, top, mid_x, bottom],
               'right': [mid_x, top, right, bottom], 'top_left': [left, top, mid_x, mid_y],
               'top_right': [mid_x, top, right, mid_y], 'bottom_left': [left, mid_y, mid_x, bottom],
               'bottom_right': [mid_x, mid_y, right, bottom]}
    if position not in choices:
        raise ValueError('Unknown layout position')
    return choices[position]


def place(window, rect):
    left, top, right, bottom = rect
    window.restore()
    window.move_window(x=left, y=top, width=right-left, height=bottom-top, repaint=True)
    return bounds(window)


def window_layout(parameters=None, **context):
    global _observed
    params = parameters or {}
    with _lock:
        try:
            if params.get('action') == 'list':
                token = secrets.token_hex(5)
                areas = monitors()
                entries = {}
                for window in windows():
                    key = f'{token}:{window.handle}'
                    entries[key] = {'handle': window.handle, 'pid': window.process_id(), 'title': window.window_text(), 'bounds': bounds(window)}
                _observed = (time.monotonic(), entries, areas)
                return outcome.untrusted('observed Windows windows and monitor work areas', json.dumps({'windows': [{'id': key, **value} for key, value in entries.items()], 'monitors': areas}, ensure_ascii=False))
            if params.get('action') != 'place' or not _observed:
                raise ValueError('List windows and monitors before place')
            observed, _observed = _observed, None
            at, entries, areas = observed
            entry = entries.get(params.get('window_id'))
            if time.monotonic() - at > 30 or not entry or monitors() != areas:
                raise ValueError('Window selection expired or monitors changed; list again')
            matches = [w for w in windows() if w.handle == entry['handle'] and w.process_id() == entry['pid'] and w.window_text() == entry['title'] and bounds(w) == entry['bounds']]
            if len(matches) != 1:
                raise ValueError('Window changed; no layout sent')
            area = next((m for m in areas if m['id'] == params.get('monitor')), None)
            if not area:
                raise ValueError('Choose an observed monitor id')
            rect = layout_rect(area['work'], params.get('position', 'full'))
            window = matches[0]
            actual = place(window, rect)
            def undo():
                candidates = [w for w in windows() if w.handle == entry['handle'] and w.process_id() == entry['pid'] and bounds(w) == actual]
                if len(candidates) != 1 or monitors() != areas:
                    return 'Window or monitors changed; previous layout not restored'
                place(candidates[0], entry['bounds'])
                return 'Previous window bounds requested; inspect the layout'
            push_undo('organizou janela ' + entry['title'], undo)
            if any(abs(a-b) > 12 for a, b in zip(actual, rect)):
                return outcome.unverified('window_layout', 'App minimum size or window borders prevented the requested bounds', actual=actual, retry_allowed=False)
            return outcome.done('window_layout', verified_scope='window_bounds', title=entry['title'], bounds=actual, monitor=area['id'])
        except Exception as exc:
            return outcome.unverified('window_layout', str(exc), retry_allowed=False)


TOOL = {'name': 'window_layout', 'description': 'Windows multi-monitor layouts. list exposes actual windows and monitor work areas; place needs fresh window_id, monitor id and position full/left/right/top_left/top_right/bottom_left/bottom_right. No guessed coordinates, no touching Jarvis processes. Supports guarded undo. List again after every placement. Ask for the intended layout if unspecified; never invent monitor preferences.',
        'brief': 'List real windows/monitors; place a selected window in a monitor half/quadrant/full area, verify bounds and support undo.',
        'parameters': {'type': 'OBJECT', 'properties': {'action': {'type': 'STRING', 'enum': ['list', 'place']}, 'window_id': {'type': 'STRING'}, 'monitor': {'type': 'INTEGER'}, 'position': {'type': 'STRING', 'enum': ['full','left','right','top_left','top_right','bottom_left','bottom_right']}}, 'required': ['action']}, 'handler': window_layout}
