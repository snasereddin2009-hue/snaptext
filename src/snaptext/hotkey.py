"""Global hotkeys through the Win32 ``RegisterHotKey`` API."""

from __future__ import annotations

import ctypes
import logging
import queue
import re
import threading
from collections.abc import Callable
from concurrent.futures import Future
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

_WM_QUIT = 0x0012
_WM_HOTKEY = 0x0312
_WM_TASK = 0x8000 + 1  # WM_APP + 1: run queued tasks on the listener thread
_PM_NOREMOVE = 0x0000
_ERROR_HOTKEY_ALREADY_REGISTERED = 1409
_TASK_TIMEOUT_S = 2.0

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}

_NAMED_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
}

_VK_F1 = 0x70
_FUNCTION_KEY = re.compile(r"f([1-9]|1[0-9]|2[0-4])")


class HotkeyError(ValueError):
    """A hotkey is malformed or could not be registered."""


@dataclass(frozen=True, slots=True)
class Hotkey:
    """A key combination as ``RegisterHotKey`` expects it."""

    modifiers: int
    key: int


def parse_hotkey(text: str) -> Hotkey:
    """Parse a combination such as ``"ctrl+shift+t"``.

    Raises:
        HotkeyError: The text is not a valid combination.
    """
    tokens = [token.strip().lower() for token in text.split("+")]
    if not all(tokens):
        raise HotkeyError(f"Invalid hotkey {text!r}: expected keys joined by '+'")

    *modifier_names, key_name = tokens
    modifiers = 0
    for name in modifier_names:
        if name not in _MODIFIERS:
            raise HotkeyError(f"Invalid hotkey {text!r}: unknown modifier {name!r}")
        modifiers |= _MODIFIERS[name]
    return Hotkey(modifiers, _virtual_key(key_name, text))


def _virtual_key(name: str, hotkey: str) -> int:
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(name.upper())
    if match := _FUNCTION_KEY.fullmatch(name):
        return _VK_F1 + int(match.group(1)) - 1
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name]
    if name in _MODIFIERS:
        raise HotkeyError(f"Invalid hotkey {hotkey!r}: it must end with a non-modifier key")
    raise HotkeyError(f"Invalid hotkey {hotkey!r}: unknown key {name!r}")


class HotkeyListener:
    """Registers global hotkeys and runs their callbacks on a background thread.

    ``RegisterHotKey`` binds a hotkey to the calling thread's message queue,
    so registration is marshalled onto the listener thread rather than done
    on the caller's.
    """

    def __init__(self) -> None:
        self._user32 = _load_user32()
        self._thread = threading.Thread(
            target=self._run, name="snaptext-hotkeys", daemon=True
        )
        self._thread_id = 0
        self._ready = threading.Event()
        self._tasks: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._ids: dict[Hotkey, int] = {}
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1

    def start(self) -> None:
        self._thread.start()
        self._ready.wait()

    def stop(self) -> None:
        if self._thread.is_alive():
            self._user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
            self._thread.join(_TASK_TIMEOUT_S)

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Invoke ``callback`` on the listener thread whenever ``hotkey`` is pressed.

        Raises:
            HotkeyError: The hotkey is malformed or already taken.
        """
        parsed = parse_hotkey(hotkey)
        self._run_on_thread(lambda: self._register(hotkey, parsed, callback))

    def unregister(self, hotkey: str) -> None:
        """Remove a hotkey; unknown hotkeys are ignored."""
        parsed = parse_hotkey(hotkey)
        self._run_on_thread(lambda: self._unregister(parsed))

    def _run_on_thread(self, task: Callable[[], None]) -> None:
        future: Future[None] = Future()

        def run() -> None:
            try:
                task()
            except Exception as exc:
                future.set_exception(exc)
            else:
                future.set_result(None)

        self._tasks.put(run)
        if not self._user32.PostThreadMessageW(self._thread_id, _WM_TASK, 0, 0):
            raise HotkeyError("The hotkey listener is not running")
        try:
            future.result(_TASK_TIMEOUT_S)
        except TimeoutError as exc:
            raise HotkeyError("The hotkey listener did not respond") from exc

    def _register(self, text: str, hotkey: Hotkey, callback: Callable[[], None]) -> None:
        if hotkey in self._ids:
            raise HotkeyError(f"Hotkey {text!r} is already registered")
        hotkey_id = self._next_id
        self._next_id += 1
        registered = self._user32.RegisterHotKey(
            None, hotkey_id, hotkey.modifiers | _MOD_NOREPEAT, hotkey.key
        )
        if not registered:
            error = ctypes.get_last_error()
            if error == _ERROR_HOTKEY_ALREADY_REGISTERED:
                raise HotkeyError(f"Hotkey {text!r} is already used by another application")
            raise HotkeyError(
                f"Could not register hotkey {text!r}: {ctypes.FormatError(error)}"
            )
        self._ids[hotkey] = hotkey_id
        self._callbacks[hotkey_id] = callback

    def _unregister(self, hotkey: Hotkey) -> None:
        hotkey_id = self._ids.pop(hotkey, None)
        if hotkey_id is not None:
            del self._callbacks[hotkey_id]
            self._user32.UnregisterHotKey(None, hotkey_id)

    def _run(self) -> None:
        message = wintypes.MSG()
        # A thread has no message queue until it first asks for a message;
        # peeking creates it so other threads can post to it from now on.
        self._user32.PeekMessageW(ctypes.byref(message), None, 0, 0, _PM_NOREMOVE)
        self._thread_id = threading.get_native_id()
        self._ready.set()

        while self._user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == _WM_HOTKEY:
                self._dispatch(message.wParam)
            elif message.message == _WM_TASK:
                self._drain_tasks()

        for hotkey_id in self._callbacks:
            self._user32.UnregisterHotKey(None, hotkey_id)

    def _dispatch(self, hotkey_id: int) -> None:
        callback = self._callbacks.get(hotkey_id)
        if callback is None:
            return
        try:
            callback()
        except Exception:
            log.exception("Hotkey callback failed")

    def _drain_tasks(self) -> None:
        while True:
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                return
            task()


def _load_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    message_pointer = ctypes.POINTER(wintypes.MSG)
    user32.RegisterHotKey.argtypes = (
        wintypes.HWND,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.UINT,
    )
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = (
        message_pointer,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    )
    user32.GetMessageW.restype = ctypes.c_int
    user32.PeekMessageW.argtypes = (
        message_pointer,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    )
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = (
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostThreadMessageW.restype = wintypes.BOOL
    return user32
