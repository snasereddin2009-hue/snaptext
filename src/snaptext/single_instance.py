"""Single-instance guard backed by a named Windows mutex."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Holds a named mutex for as long as this process should be the only one.

    Windows releases the mutex when the process exits, so a crash never
    leaves a stale lock behind.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._handle: int | None = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def acquire(self) -> bool:
        """Claim the lock; return ``False`` if another process already holds it."""
        handle = self._kernel32.CreateMutexW(None, False, self._name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == _ERROR_ALREADY_EXISTS:
            self._kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
