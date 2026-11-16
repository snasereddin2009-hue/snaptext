"""Generate synthetic screen-text images with ground truth for the OCR benchmark.

Each image is written as ``<theme>_<font>_<size>.png`` next to a ``.txt``
file holding the exact text it shows.

Usage:
    python scripts/generate_samples.py [--out samples]
"""

from __future__ import annotations

import argparse
import itertools
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

Colour = tuple[int, int, int]

_MARGIN_PX = 16
_LINE_SPACING_PX = 6
_FONT_SIZES_PX = (12, 15, 20)

_FONTS = {
    "segoe": "segoeui.ttf",
    "consolas": "consola.ttf",
    "times": "times.ttf",
}

_TEXTS = (
    "The quick brown fox jumps over the lazy dog.\n"
    "Pack my box with five dozen liquor jugs.\n"
    "How vexingly quick daft zebras jump!",
    "Invoice #40218 was issued on 14 March 2025.\n"
    "Subtotal: $1,284.50 Tax (8.5%): $109.18\n"
    "Please remit payment within 30 days.",
    "def area(radius: float) -> float:\n"
    "    return 3.14159 * radius ** 2\n"
    "print(area(2.5))",
    "Settings > Display > Scale and layout\n"
    "Change the size of text, apps, and other items\n"
    "Recommended: 150% at 2560 x 1440",
)


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    background: Colour
    foreground: Colour


_THEMES = (
    Theme("light", (255, 255, 255), (30, 30, 30)),
    Theme("dark", (30, 30, 30), (212, 212, 212)),
    Theme("lowcontrast", (236, 236, 236), (140, 140, 140)),
    Theme("accent", (0, 90, 158), (255, 255, 255)),
)


def fonts_dir() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def render(text: str, font: ImageFont.FreeTypeFont, theme: Theme) -> Image.Image:
    """Draw ``text`` on a tightly cropped canvas, like a region selected on screen."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    left, top, right, bottom = probe.multiline_textbbox(
        (0, 0), text, font=font, spacing=_LINE_SPACING_PX
    )
    size = (right - left + 2 * _MARGIN_PX, bottom - top + 2 * _MARGIN_PX)
    image = Image.new("RGB", size, theme.background)
    ImageDraw.Draw(image).multiline_text(
        (_MARGIN_PX - left, _MARGIN_PX - top),
        text,
        font=font,
        fill=theme.foreground,
        spacing=_LINE_SPACING_PX,
    )
    return image


def generate(out_dir: Path) -> int:
    """Write every theme, font and size combination; return the image count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = itertools.cycle(_TEXTS)
    count = 0
    for font_name, font_file in _FONTS.items():
        font_path = fonts_dir() / font_file
        if not font_path.is_file():
            print(f"Skipping {font_name}: {font_path} not found")
            continue
        for theme, size in itertools.product(_THEMES, _FONT_SIZES_PX):
            text = next(texts)
            font = ImageFont.truetype(font_path, size)
            stem = f"{theme.name}_{font_name}_{size}"
            render(text, font, theme).save(out_dir / f"{stem}.png")
            (out_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=Path("samples"), help="output folder (default: samples)"
    )
    args = parser.parse_args()
    count = generate(args.out)
    print(f"Wrote {count} sample images to {args.out}")


if __name__ == "__main__":
    main()
