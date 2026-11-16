"""User configuration and per-user file locations."""

from __future__ import annotations

import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Self

log = logging.getLogger(__name__)

APP_NAME = "SnapText"

_TEMPLATE = """\
# SnapText configuration. Restart SnapText after editing this file.

# Global hotkey that starts a capture.
# Modifiers: ctrl, shift, alt, win. Keys: a-z, 0-9, f1-f24, space, tab, ...
hotkey = "{hotkey}"

# Tesseract language code. Combine several with "+", e.g. "eng+deu".
language = "{language}"

# Clean up the screenshot before OCR (greyscale, dark-mode inversion,
# upscaling, thresholding).
preprocess = {preprocess}
"""


class ConfigError(ValueError):
    """The config file exists but cannot be used."""


@dataclass(frozen=True, slots=True)
class Config:
    """User-editable settings."""

    hotkey: str = "ctrl+shift+t"
    language: str = "eng"
    preprocess: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Self:
        """Build a config from parsed TOML, using defaults for missing keys."""
        known = {field.name: type(field.default) for field in fields(cls)}
        for key in data.keys() - known.keys():
            log.warning("Ignoring unknown config key %r", key)

        values: dict[str, Any] = {}
        for name, expected in known.items():
            if name not in data:
                continue
            value = data[name]
            if type(value) is not expected:
                raise ConfigError(
                    f"'{name}' must be of type {expected.__name__}, "
                    f"not {type(value).__name__}"
                )
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    raise ConfigError(f"'{name}' must not be empty")
            values[name] = value
        return cls(**values)

    def to_toml(self) -> str:
        """Render the config as a commented TOML document."""
        return _TEMPLATE.format(
            hotkey=self.hotkey,
            language=self.language,
            preprocess=str(self.preprocess).lower(),
        )


def app_dir() -> Path:
    """Return the per-user directory that holds the config and log files."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_NAME


def config_path() -> Path:
    return app_dir() / "config.toml"


def log_path() -> Path:
    return app_dir() / "snaptext.log"


def write_default_config(path: Path) -> None:
    """Create the config file, and its directory, with default settings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Config().to_toml(), encoding="utf-8")


def load_config(path: Path | None = None) -> Config:
    """Load the config file, creating it with defaults on first run.

    Raises:
        ConfigError: The file is not valid TOML or holds invalid values.
    """
    path = path or config_path()
    if not path.exists():
        write_default_config(path)
        log.info("Created default config at %s", path)
        return Config()

    try:
        # utf-8-sig tolerates the byte order mark some editors prepend.
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc
    return Config.from_mapping(data)
