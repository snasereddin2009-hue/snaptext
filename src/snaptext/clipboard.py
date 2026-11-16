"""Clipboard access."""

from __future__ import annotations

import pyperclip


class ClipboardError(RuntimeError):
    """The clipboard could not be written to."""


def copy_text(text: str) -> None:
    """Place ``text`` on the system clipboard."""
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise ClipboardError(f"Could not copy to the clipboard: {exc}") from exc
