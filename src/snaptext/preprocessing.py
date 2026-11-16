"""Image clean-up that makes screen text easier for Tesseract to read.

Tesseract is trained on dark text on a light background at print resolution.
Screen text is small, anti-aliased and often light-on-dark, so the pipeline
normalises all three before recognition.
"""

from __future__ import annotations

from PIL import Image, ImageOps, ImageStat

UPSCALE_FACTOR = 3.0
MAX_SIDE_PX = 6000
BORDER_PX = 12

_WHITE = 255
_MID_GREY = 128


def to_greyscale(image: Image.Image) -> Image.Image:
    return image.convert("L")


def is_dark(image: Image.Image) -> bool:
    """Report whether a greyscale image has a dark background.

    Text covers a minority of the pixels, so the median is the background.
    """
    return ImageStat.Stat(image).median[0] < _MID_GREY


def invert_if_dark(image: Image.Image) -> Image.Image:
    """Turn light-on-dark text into dark-on-light."""
    return ImageOps.invert(image) if is_dark(image) else image


def upscale(
    image: Image.Image,
    factor: float = UPSCALE_FACTOR,
    max_side: int = MAX_SIDE_PX,
) -> Image.Image:
    """Enlarge the image by ``factor``, keeping the longest side within ``max_side``."""
    factor = min(factor, max_side / max(image.size))
    if factor <= 1:
        return image
    size = (round(image.width * factor), round(image.height * factor))
    return image.resize(size, Image.Resampling.LANCZOS)


def otsu_threshold(image: Image.Image) -> int:
    """Return the grey level that best separates a greyscale image into two classes.

    Otsu's method: choose the threshold that maximises between-class variance.
    """
    histogram = image.histogram()
    total = sum(histogram)
    weighted_total = sum(level * count for level, count in enumerate(histogram))

    best_threshold = 0
    best_variance = -1.0
    below = 0
    weighted_below = 0
    for level, count in enumerate(histogram):
        below += count
        if below == 0:
            continue
        above = total - below
        if above == 0:
            break
        weighted_below += level * count
        mean_below = weighted_below / below
        mean_above = (weighted_total - weighted_below) / above
        variance = below * above * (mean_below - mean_above) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = level
    return best_threshold


def binarise(image: Image.Image) -> Image.Image:
    """Map a greyscale image to pure black and white around its Otsu threshold."""
    threshold = otsu_threshold(image)
    return image.point(lambda level: _WHITE if level > threshold else 0)


def add_border(image: Image.Image, width: int = BORDER_PX) -> Image.Image:
    """Pad with white so glyphs never touch the image edge."""
    return ImageOps.expand(image, border=width, fill=_WHITE)


def preprocess(image: Image.Image) -> Image.Image:
    """Run the full pipeline; the result is black text on a white background."""
    image = to_greyscale(image)
    image = invert_if_dark(image)
    image = upscale(image)
    image = binarise(image)
    return add_border(image)
