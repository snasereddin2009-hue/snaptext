"""Text recognition with Tesseract."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytesseract
from PIL import Image

from snaptext.preprocessing import preprocess as preprocess_image

log = logging.getLogger(__name__)

# Page segmentation mode 6: treat the image as a single uniform block of text.
_TESSERACT_ARGS = "--psm 6"

_INSTALL_LOCATIONS = (
    ("PROGRAMFILES", "Tesseract-OCR"),
    ("PROGRAMFILES(X86)", "Tesseract-OCR"),
    ("LOCALAPPDATA", "Programs/Tesseract-OCR"),
)


class OcrError(RuntimeError):
    """Text recognition could not be performed."""


class TesseractNotFoundError(OcrError):
    """The Tesseract executable is not installed or cannot be located."""

    def __init__(self) -> None:
        super().__init__(
            "Tesseract OCR was not found. Install it and add it to PATH."
        )


def _locate_tesseract() -> None:
    """Point pytesseract at tesseract.exe.

    The Windows installer does not add Tesseract to PATH, so its default
    install directories are checked as a fallback.
    """
    if shutil.which(pytesseract.pytesseract.tesseract_cmd):
        return
    for variable, subdirectory in _INSTALL_LOCATIONS:
        base = os.environ.get(variable)
        if not base:
            continue
        candidate = Path(base) / subdirectory / "tesseract.exe"
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def tesseract_version() -> str:
    """Return the installed Tesseract version.

    Raises:
        TesseractNotFoundError: Tesseract is not installed.
    """
    _locate_tesseract()
    try:
        return str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError as exc:
        raise TesseractNotFoundError from exc


def recognise(image: Image.Image, language: str = "eng", *, preprocess: bool = True) -> str:
    """Return the text in ``image``, or an empty string when none is detected.

    Raises:
        TesseractNotFoundError: Tesseract is not installed.
        OcrError: Tesseract failed, for example on a missing language pack.
    """
    _locate_tesseract()
    if preprocess:
        image = preprocess_image(image)
    try:
        text = pytesseract.image_to_string(image, lang=language, config=_TESSERACT_ARGS)
    except pytesseract.TesseractNotFoundError as exc:
        raise TesseractNotFoundError from exc
    except pytesseract.TesseractError as exc:
        log.error("Tesseract failed: %s", exc)
        if "Failed loading language" in str(exc):
            raise OcrError(
                f"Tesseract has no language data for '{language}'. "
                "Install it or change 'language' in the config."
            ) from exc
        raise OcrError("Tesseract failed. See the log for details.") from exc
    return _tidy(text)


def _tidy(text: str) -> str:
    """Strip the padding and trailing whitespace Tesseract adds to its output."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())
