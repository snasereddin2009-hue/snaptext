"""System tray icon, menu and notifications."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from snaptext.config import APP_NAME

log = logging.getLogger(__name__)

_ICON_SIZE = 64
_ICON_COLOUR = (37, 99, 235, 255)
_MAX_MESSAGE_CHARS = 255  # limit of the Win32 notification text buffer


def _draw_icon() -> Image.Image:
    """Draw the tray icon: a white "T" on a rounded blue tile."""
    image = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=_ICON_COLOUR)
    draw.rectangle((16, 16, 47, 24), fill="white")
    draw.rectangle((28, 16, 35, 49), fill="white")
    return image


class Tray:
    """Tray icon running on its own thread.

    The callbacks are invoked on the tray thread, so they must be safe to
    call from outside the UI thread.
    """

    def __init__(
        self,
        *,
        on_capture: Callable[[], None],
        on_open_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._lock = threading.Lock()
        self._visible = False
        self._pending: str | None = None
        # pystray inspects each handler's signature to decide what to pass
        # it; the lambdas guarantee a zero-argument call for any callable.
        menu = pystray.Menu(
            pystray.MenuItem("Capture", lambda: on_capture(), default=True),
            pystray.MenuItem("Open Config", lambda: on_open_config()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: on_quit()),
        )
        self._icon = pystray.Icon(
            APP_NAME.lower(), icon=_draw_icon(), title=APP_NAME, menu=menu
        )

    def start(self) -> None:
        self._icon.run_detached(setup=self._on_ready)

    def stop(self) -> None:
        self._icon.stop()

    def notify(self, message: str) -> None:
        """Show a notification next to the tray icon; safe to call from any thread.

        A notification sent before the icon exists is held back and shown
        once it appears.
        """
        with self._lock:
            if not self._visible:
                self._pending = message
                return
        self._show(message)

    def _on_ready(self, icon: pystray.Icon) -> None:
        try:
            icon.visible = True
        except Exception:
            log.exception("Could not show the tray icon")
            return
        with self._lock:
            self._visible = True
            pending, self._pending = self._pending, None
        if pending is not None:
            self._show(pending)

    def _show(self, message: str) -> None:
        try:
            self._icon.notify(message[:_MAX_MESSAGE_CHARS], APP_NAME)
        except Exception:
            log.exception("Could not show notification: %s", message)
