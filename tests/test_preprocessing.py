import pytest
from PIL import Image, ImageDraw

from snaptext.preprocessing import (
    BORDER_PX,
    UPSCALE_FACTOR,
    add_border,
    binarise,
    invert_if_dark,
    is_dark,
    otsu_threshold,
    preprocess,
    to_greyscale,
    upscale,
)

Colour = tuple[int, int, int]

WHITE: Colour = (255, 255, 255)
BLACK: Colour = (0, 0, 0)


def text_like(background: Colour, foreground: Colour) -> Image.Image:
    """A flat background with a small block of 'ink' on it."""
    image = Image.new("RGB", (120, 40), background)
    ImageDraw.Draw(image).rectangle((20, 10, 50, 30), fill=foreground)
    return image


def levels(image: Image.Image) -> set[int]:
    return {level for _, level in image.getcolors()}


def test_to_greyscale_returns_single_channel() -> None:
    assert to_greyscale(text_like(WHITE, BLACK)).mode == "L"


def test_to_greyscale_accepts_images_with_alpha() -> None:
    assert to_greyscale(Image.new("RGBA", (4, 4), (10, 20, 30, 255))).mode == "L"


@pytest.mark.parametrize(
    ("background", "foreground", "expected"),
    [(WHITE, BLACK, False), (BLACK, WHITE, True), ((30, 30, 30), (212, 212, 212), True)],
)
def test_is_dark_follows_the_background(
    background: Colour, foreground: Colour, expected: bool
) -> None:
    assert is_dark(to_greyscale(text_like(background, foreground))) is expected


def test_invert_if_dark_flips_dark_images() -> None:
    result = invert_if_dark(to_greyscale(text_like(BLACK, WHITE)))

    assert result.getpixel((0, 0)) == 255
    assert result.getpixel((30, 20)) == 0


def test_invert_if_dark_leaves_light_images_unchanged() -> None:
    image = to_greyscale(text_like(WHITE, BLACK))

    assert invert_if_dark(image) is image


def test_upscale_multiplies_dimensions() -> None:
    result = upscale(Image.new("L", (100, 40)), factor=3)

    assert result.size == (300, 120)


def test_upscale_respects_max_side() -> None:
    result = upscale(Image.new("L", (1000, 200)), factor=3, max_side=2000)

    assert result.size == (2000, 400)


def test_upscale_never_shrinks() -> None:
    image = Image.new("L", (1000, 200))

    assert upscale(image, factor=3, max_side=500) is image


def test_otsu_threshold_separates_two_levels() -> None:
    image = to_greyscale(text_like((200, 200, 200), (50, 50, 50)))

    assert 50 <= otsu_threshold(image) < 200


def test_otsu_threshold_handles_uniform_image() -> None:
    assert 0 <= otsu_threshold(Image.new("L", (10, 10), 128)) <= 255


def test_binarise_yields_only_black_and_white() -> None:
    image = to_greyscale(text_like((200, 200, 200), (90, 90, 90)))

    result = binarise(image)

    assert levels(result) == {0, 255}
    assert result.getpixel((0, 0)) == 255
    assert result.getpixel((30, 20)) == 0


def test_add_border_pads_every_side_with_white() -> None:
    result = add_border(Image.new("L", (10, 10), 0), width=5)

    assert result.size == (20, 20)
    assert result.getpixel((0, 0)) == 255
    assert result.getpixel((10, 10)) == 0


@pytest.mark.parametrize(
    ("background", "foreground"),
    [(WHITE, BLACK), (BLACK, WHITE), ((30, 30, 30), (212, 212, 212))],
)
def test_preprocess_outputs_black_text_on_white(
    background: Colour, foreground: Colour
) -> None:
    result = preprocess(text_like(background, foreground))

    ink = (BORDER_PX + round(35 * UPSCALE_FACTOR), BORDER_PX + round(20 * UPSCALE_FACTOR))
    assert result.mode == "L"
    assert levels(result) == {0, 255}
    assert result.getpixel((0, 0)) == 255
    assert result.getpixel((BORDER_PX + 5, BORDER_PX + 5)) == 255
    assert result.getpixel(ink) == 0


def test_preprocess_scales_and_pads() -> None:
    result = preprocess(text_like(WHITE, BLACK))

    assert result.size == (
        round(120 * UPSCALE_FACTOR) + 2 * BORDER_PX,
        round(40 * UPSCALE_FACTOR) + 2 * BORDER_PX,
    )


def test_preprocess_does_not_modify_its_input() -> None:
    image = text_like(BLACK, WHITE)
    original = image.copy()

    preprocess(image)

    assert image.tobytes() == original.tobytes()
