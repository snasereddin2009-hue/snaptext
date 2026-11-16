import pytest

from snaptext.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    HotkeyError,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ctrl+shift+t", Hotkey(MOD_CONTROL | MOD_SHIFT, ord("T"))),
        ("Ctrl + Shift + T", Hotkey(MOD_CONTROL | MOD_SHIFT, ord("T"))),
        ("control+alt+9", Hotkey(MOD_CONTROL | MOD_ALT, ord("9"))),
        ("win+shift+f2", Hotkey(MOD_WIN | MOD_SHIFT, 0x71)),
        ("alt+f24", Hotkey(MOD_ALT, 0x87)),
        ("ctrl+space", Hotkey(MOD_CONTROL, 0x20)),
        ("esc", Hotkey(0, 0x1B)),
    ],
)
def test_parse_hotkey(text: str, expected: Hotkey) -> None:
    assert parse_hotkey(text) == expected


def test_modifier_order_does_not_matter() -> None:
    assert parse_hotkey("shift+ctrl+t") == parse_hotkey("ctrl+shift+t")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ctrl+",
        "ctrl++t",
        "ctrl+shift",
        "hyper+t",
        "ctrl+notakey",
        "ctrl+f25",
        "ctrl+é",
        "t+ctrl",
    ],
)
def test_invalid_hotkey_is_rejected(text: str) -> None:
    with pytest.raises(HotkeyError):
        parse_hotkey(text)
