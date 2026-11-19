"""Windows single-instance startup and activation of an existing gauge."""

import ctypes
import os
from ctypes import wintypes

APPLICATION_TITLE = "GitHub Rate Gauge"
MUTEX_NAME = r"Local\GitHubRateGauge-A94E76C5-3B25-4B58-A93E-1C4628F32075"
ACTIVATION_EVENT_NAME = MUTEX_NAME + "-Activate"
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self):
        self._kernel32 = None
        self._mutex = None
        self._activation_event = None

    def acquire(self):
        if os.name != "nt":
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateEventW.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32 = kernel32

        # Create the event before taking the mutex so concurrent startup can
        # signal the winner even while its Tk window is still being created.
        self._activation_event = kernel32.CreateEventW(
            None, False, False, ACTIVATION_EVENT_NAME
        )
        if not self._activation_event:
            raise ctypes.WinError(ctypes.get_last_error())
        self._mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not self._mutex:
            error = ctypes.WinError(ctypes.get_last_error())
            self.release()
            raise error
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            try:
                if not kernel32.SetEvent(self._activation_event):
                    raise ctypes.WinError(ctypes.get_last_error())
                _allow_existing_window_foreground()
            finally:
                self.release()
            return False
        return True

    def activation_requested(self):
        return (
            self._activation_event is not None
            and self._kernel32.WaitForSingleObject(self._activation_event, 0) == 0
        )

    def release(self):
        for handle in (self._mutex, self._activation_event):
            if handle is not None:
                self._kernel32.CloseHandle(handle)
        self._mutex = None
        self._activation_event = None


def _allow_existing_window_foreground():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AllowSetForegroundWindow.argtypes = (wintypes.DWORD,)
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL

    window = user32.FindWindowW(None, APPLICATION_TITLE)
    if window:
        process_id = wintypes.DWORD()
        if user32.GetWindowThreadProcessId(window, ctypes.byref(process_id)):
            user32.AllowSetForegroundWindow(process_id.value)
