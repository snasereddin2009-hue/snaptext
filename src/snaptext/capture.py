"""Screen geometry and region capture."""

from __future__ import annotations

from dataclasses import dataclass

import mss
from mss.exception import ScreenShotError
from PIL import Image


class CaptureError(RuntimeError):
    """The screen could not be captured."""


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle in physical pixels of the virtual screen.

    The origin is the top-left corner of the primary monitor, so monitors
    placed to its left or above have negative coordinates.
    """

    left: int
    top: int
    width: int
    height: int


def virtual_screen() -> Region:
    """Return the bounding box that spans every connected monitor."""
    try:
        with mss.mss() as screen:
            box = screen.monitors[0]
    except ScreenShotError as exc:
        raise CaptureError(f"Could not query the monitor layout: {exc}") from exc
    return Region(box["left"], box["top"], box["width"], box["height"])


def grab(region: Region) -> Image.Image:
    """Capture ``region`` of the screen as an RGB image."""
    box = {
        "left": region.left,
        "top": region.top,
        "width": region.width,
        "height": region.height,
    }
    try:
        with mss.mss() as screen:
            shot = screen.grab(box)
    except ScreenShotError as exc:
        raise CaptureError(f"Could not capture the screen: {exc}") from exc
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
