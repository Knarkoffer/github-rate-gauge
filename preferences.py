"""Local window preferences and monitor-aware positioning."""

import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path


@dataclass(frozen=True)
class Preferences:
    position: tuple[int, int] | None = None
    always_on_top: bool = False


class PreferencesStore:
    def __init__(self, path=None):
        if path is None:
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            directory = (
                Path(base) / "GitHubRateGauge"
                if base
                else Path.home() / ".local" / "share" / "github-rate-gauge"
            )
            path = directory / "settings.json"
        self.path = Path(path)

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return Preferences()
        if not isinstance(raw, dict):
            return Preferences()
        position = raw.get("position")
        valid_position = (
            isinstance(position, list)
            and len(position) == 2
            and all(
                type(value) is int and -(2**31) <= value < 2**31 for value in position
            )
        )
        always_on_top = raw.get("always_on_top", False)
        return Preferences(
            tuple(position) if valid_position else None,
            always_on_top if isinstance(always_on_top, bool) else False,
        )

    def save(self, preferences):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="settings-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(asdict(preferences), output, indent=2)
                output.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


@cache
def _windows_api():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MonitorFromRect.argtypes = (ctypes.POINTER(wintypes.RECT), wintypes.DWORD)
    user32.MonitorFromRect.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = (
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    )
    user32.SetWindowPos.restype = wintypes.BOOL
    return user32


def _native_window(root):
    user32 = _windows_api()
    window = user32.GetAncestor(root.winfo_id(), 2)
    rectangle = wintypes.RECT()
    if not user32.GetWindowRect(window, ctypes.byref(rectangle)):
        raise ctypes.WinError(ctypes.get_last_error())
    return window, rectangle


def window_position(root):
    if os.name == "nt":
        _, rectangle = _native_window(root)
        return rectangle.left, rectangle.top
    return root.winfo_x(), root.winfo_y()


def clamp_position(position, size, work_area):
    x, y = position
    width, height = size
    left, top, right, bottom = work_area
    return (
        min(max(x, left), max(left, right - width)),
        min(max(y, top), max(top, bottom - height)),
    )


def restore_window_position(root, position):
    root.update_idletasks()
    if os.name != "nt":
        x, y = clamp_position(
            position,
            (root.winfo_width(), root.winfo_height()),
            (0, 0, root.winfo_screenwidth(), root.winfo_screenheight()),
        )
        root.geometry(f"+{x}+{y}")
        return

    user32 = _windows_api()
    window, rectangle = _native_window(root)
    width = rectangle.right - rectangle.left
    height = rectangle.bottom - rectangle.top
    x, y = position
    target = wintypes.RECT(x, y, min(x + width, 2**31 - 1), min(y + height, 2**31 - 1))
    monitor = user32.MonitorFromRect(ctypes.byref(target), 2)
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    work = info.rcWork
    x, y = clamp_position(
        position, (width, height), (work.left, work.top, work.right, work.bottom)
    )
    # Keep the size, stacking order, and activation state while moving.
    if not user32.SetWindowPos(window, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010):
        raise ctypes.WinError(ctypes.get_last_error())
