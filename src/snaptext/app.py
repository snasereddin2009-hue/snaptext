"""Application wiring: hotkey -> overlay -> capture -> OCR -> clipboard."""

from __future__ import annotations

import ctypes
import logging
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from PIL import Image

from snaptext import __version__, capture, clipboard, ocr
from snaptext.capture import CaptureError, Region
from snaptext.clipboard import ClipboardError
from snaptext.config import (
    APP_NAME,
    Config,
    ConfigError,
    config_path,
    load_config,
    log_path,
    write_default_config,
)
from snaptext.hotkey import HotkeyError, HotkeyListener
from snaptext.overlay import SelectionOverlay
from snaptext.single_instance import SingleInstance
from snaptext.tray import Tray

log = logging.getLogger(__name__)

_MUTEX_NAME = "SnapText.SingleInstance"
_CANCEL_HOTKEY = "esc"
_TASK_POLL_MS = 30
# Time for the compositor to repaint the desktop once the overlay is gone.
_CAPTURE_DELAY_MS = 120
_MIN_SELECTION_PX = 4
_PROCESS_PER_MONITOR_DPI_AWARE = 2
_MB_ICONINFORMATION = 0x40


class App:
    """Owns the UI thread and coordinates the capture pipeline.

    Tk is single-threaded, so the hotkey, tray and OCR threads never touch
    it directly: they queue tasks that the Tk event loop runs.
    """

    def __init__(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.report_callback_exception = _log_callback_exception
        self._tasks: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._busy = False

        self._config, self._config_problem = _load_config()
        self._overlay = SelectionOverlay(self._root)
        self._hotkeys = HotkeyListener()
        self._tray = Tray(
            on_capture=lambda: self._post(self._begin_capture),
            on_open_config=lambda: self._post(self._open_config),
            on_quit=lambda: self._post(self._quit),
        )

    def run(self) -> None:
        """Run until the user quits from the tray menu."""
        signal.signal(signal.SIGINT, lambda *_: self._post(self._quit))
        self._tray.start()
        self._hotkeys.start()
        try:
            self._report_startup_problems()
            self._root.after(_TASK_POLL_MS, self._run_tasks)
            self._root.mainloop()
        finally:
            self._hotkeys.stop()
            self._tray.stop()
            self._root.destroy()

    def _post(self, task: Callable[[], None]) -> None:
        """Queue ``task`` to run on the UI thread; safe to call from any thread."""
        self._tasks.put(task)

    def _run_tasks(self) -> None:
        try:
            while True:
                try:
                    task = self._tasks.get_nowait()
                except queue.Empty:
                    break
                try:
                    task()
                except Exception:
                    log.exception("Unhandled error on the UI thread")
        finally:
            self._root.after(_TASK_POLL_MS, self._run_tasks)

    def _report_startup_problems(self) -> None:
        problems = [
            self._config_problem,
            self._register_capture_hotkey(),
            _check_tesseract(),
        ]
        found = [problem for problem in problems if problem]
        if found:
            self._tray.notify("\n".join(found))

    def _register_capture_hotkey(self) -> str | None:
        """Register the capture hotkey; return a description of any failure."""
        try:
            self._hotkeys.register(
                self._config.hotkey, lambda: self._post(self._begin_capture)
            )
        except HotkeyError as exc:
            log.error("%s", exc)
            return f"{exc}. Capture from the tray menu until this is fixed."
        log.info("Listening for %s", self._config.hotkey)
        return None

    def _begin_capture(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            self._overlay.show(capture.virtual_screen(), self._on_selection)
        except (CaptureError, tk.TclError) as exc:
            log.error("Could not open the selection overlay: %s", exc)
            self._finish("Could not start the capture.")
            return
        self._set_cancel_hotkey(True)

    def _set_cancel_hotkey(self, enabled: bool) -> None:
        """Toggle a global Esc hotkey for the lifetime of the overlay.

        The overlay also binds Esc itself, but a borderless window is not
        guaranteed keyboard focus, so this keeps cancelling reliable.
        """
        try:
            if enabled:
                self._hotkeys.register(
                    _CANCEL_HOTKEY, lambda: self._post(self._overlay.cancel)
                )
            else:
                self._hotkeys.unregister(_CANCEL_HOTKEY)
        except HotkeyError as exc:
            log.debug("Global cancel hotkey unavailable: %s", exc)

    def _on_selection(self, region: Region | None) -> None:
        self._set_cancel_hotkey(False)
        if region is None:
            log.info("Capture cancelled")
            self._busy = False
        elif min(region.width, region.height) < _MIN_SELECTION_PX:
            self._finish("Selection was empty. Drag a box around the text to copy.")
        else:
            self._root.after(_CAPTURE_DELAY_MS, self._capture, region)

    def _capture(self, region: Region) -> None:
        try:
            image = capture.grab(region)
        except CaptureError as exc:
            log.error("%s", exc)
            self._finish("Could not capture the screen.")
            return
        threading.Thread(
            target=self._recognise, args=(image,), name="snaptext-ocr", daemon=True
        ).start()

    def _recognise(self, image: Image.Image) -> None:
        """Run OCR on a worker thread and hand the outcome back to the UI thread."""
        try:
            text = ocr.recognise(
                image, self._config.language, preprocess=self._config.preprocess
            )
        except ocr.OcrError as exc:
            log.error("%s", exc)
            message = str(exc)
            self._post(lambda: self._finish(message))
        except Exception:
            log.exception("Unexpected OCR failure")
            self._post(lambda: self._finish("OCR failed. See the log for details."))
        else:
            self._post(lambda: self._deliver(text))

    def _deliver(self, text: str) -> None:
        if not text:
            self._finish("No text detected in the selection.")
            return
        try:
            clipboard.copy_text(text)
        except ClipboardError as exc:
            log.error("%s", exc)
            self._finish("Could not copy to the clipboard.")
            return
        log.info("Copied %d characters", len(text))
        self._finish("Copied!")

    def _finish(self, message: str) -> None:
        """End the current capture and tell the user how it went."""
        self._busy = False
        self._tray.notify(message)

    def _open_config(self) -> None:
        path = config_path()
        try:
            if not path.exists():
                write_default_config(path)
            subprocess.Popen(["notepad.exe", str(path)])
        except OSError:
            log.exception("Could not open %s", path)
            self._tray.notify("Could not open the config file.")

    def _quit(self) -> None:
        log.info("Shutting down")
        self._root.quit()


def _load_config() -> tuple[Config, str | None]:
    """Load the config, falling back to defaults and describing any problem."""
    try:
        return load_config(), None
    except (ConfigError, OSError) as exc:
        log.error("Config problem, using defaults: %s", exc)
        return Config(), f"Config problem, using defaults: {exc}"


def _check_tesseract() -> str | None:
    try:
        log.info("Using Tesseract %s", ocr.tesseract_version())
    except ocr.TesseractNotFoundError as exc:
        log.error("%s", exc)
        return str(exc)
    return None


def _log_callback_exception(
    exc_type: type[BaseException],
    exc: BaseException,
    traceback: TracebackType | None,
) -> None:
    log.error("Unhandled error in a Tk callback", exc_info=(exc_type, exc, traceback))


def _configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(path, maxBytes=512_000, backupCount=2, encoding="utf-8")
    ]
    # Windowed builds have no console, in which case sys.stderr is None.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


def _enable_dpi_awareness() -> None:
    """Make Tk and mss agree on physical pixels on scaled and mixed-DPI displays.

    Must run before the first window is created.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE)
    except (AttributeError, OSError):
        log.warning("Could not enable per-monitor DPI awareness", exc_info=True)


def _show_message(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, _MB_ICONINFORMATION)


def main() -> int:
    """Start SnapText; return the process exit code."""
    _configure_logging(log_path())
    instance = SingleInstance(_MUTEX_NAME)
    if not instance.acquire():
        log.warning("Another instance is already running; exiting")
        _show_message(f"{APP_NAME} is already running.")
        return 1

    try:
        log.info("%s %s starting", APP_NAME, __version__)
        _enable_dpi_awareness()
        App().run()
    except Exception:
        log.exception("Fatal error")
        return 1
    finally:
        instance.release()
    return 0
