"""Fullscreen drag-to-select overlay."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from snaptext.capture import Region

SelectionCallback = Callable[[Region | None], None]

_DIM_COLOUR = "#000000"
_DIM_ALPHA = 0.35
_SELECTION_FILL = "#9a9a9a"
_SELECTION_OUTLINE = "#ffffff"
_OUTLINE_WIDTH = 2


@dataclass(slots=True)
class _Session:
    """State of one open overlay."""

    window: tk.Toplevel
    canvas: tk.Canvas
    bounds: Region
    on_done: SelectionCallback
    origin: tuple[int, int] | None = None
    rectangle: int | None = None


class SelectionOverlay:
    """Dims every monitor and lets the user drag out a rectangle.

    The window is sized in physical pixels, which is only correct when the
    process is per-monitor DPI aware; otherwise Windows would scale it and
    the selection would no longer line up with the screenshot.
    """

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._session: _Session | None = None

    def show(self, bounds: Region, on_done: SelectionCallback) -> None:
        """Open the overlay across ``bounds``.

        ``on_done`` receives the selected region in virtual-screen
        coordinates, or ``None`` if the selection was cancelled.
        """
        if self._session is not None:
            return

        window = tk.Toplevel(self._root)
        window.overrideredirect(True)
        # Tk reads "+-1920" as 1920 px left of the origin; a bare "-1920"
        # would instead be measured from the right-hand screen edge.
        window.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
        window.attributes("-topmost", True)
        window.attributes("-alpha", _DIM_ALPHA)

        canvas = tk.Canvas(
            window, bg=_DIM_COLOUR, highlightthickness=0, cursor="crosshair"
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        window.bind("<Escape>", lambda _event: self.cancel())
        window.focus_force()

        self._session = _Session(window, canvas, bounds, on_done)

    def cancel(self) -> None:
        """Close the overlay without a selection; a no-op when it is not open."""
        self._close(None)

    def _on_press(self, event: tk.Event[tk.Canvas]) -> None:
        session = self._session
        if session is None:
            return
        session.origin = (event.x, event.y)
        session.rectangle = session.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            fill=_SELECTION_FILL,
            outline=_SELECTION_OUTLINE,
            width=_OUTLINE_WIDTH,
        )

    def _on_drag(self, event: tk.Event[tk.Canvas]) -> None:
        session = self._session
        if session is None or session.origin is None or session.rectangle is None:
            return
        corner = _clamp(event.x, event.y, session.bounds)
        session.canvas.coords(session.rectangle, *session.origin, *corner)

    def _on_release(self, event: tk.Event[tk.Canvas]) -> None:
        session = self._session
        if session is None or session.origin is None:
            return
        x0, y0 = session.origin
        x1, y1 = _clamp(event.x, event.y, session.bounds)
        region = Region(
            left=session.bounds.left + min(x0, x1),
            top=session.bounds.top + min(y0, y1),
            width=abs(x1 - x0),
            height=abs(y1 - y0),
        )
        self._close(region)

    def _close(self, result: Region | None) -> None:
        session = self._session
        if session is None:
            return
        self._session = None
        session.window.destroy()
        self._root.update_idletasks()
        session.on_done(result)


def _clamp(x: int, y: int, bounds: Region) -> tuple[int, int]:
    """Keep a pointer position inside the overlay."""
    return (min(max(x, 0), bounds.width), min(max(y, 0), bounds.height))
