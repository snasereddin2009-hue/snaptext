import tomllib
from pathlib import Path

import pytest

from snaptext.config import Config, ConfigError, load_config


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    return tmp_path / "SnapText" / "config.toml"


def test_first_run_creates_file_with_defaults(config_file: Path) -> None:
    config = load_config(config_file)

    assert config == Config()
    assert config_file.is_file()


def test_generated_file_round_trips_to_defaults(config_file: Path) -> None:
    load_config(config_file)

    assert load_config(config_file) == Config()


def test_reads_custom_values(config_file: Path) -> None:
    config_file.parent.mkdir()
    config_file.write_text(
        'hotkey = "alt+q"\nlanguage = "eng+deu"\npreprocess = false\n', encoding="utf-8"
    )

    assert load_config(config_file) == Config(
        hotkey="alt+q", language="eng+deu", preprocess=False
    )


def test_to_toml_round_trips_custom_values() -> None:
    config = Config(hotkey="win+shift+f2", language="fra", preprocess=False)

    assert Config.from_mapping(tomllib.loads(config.to_toml())) == config


def test_missing_keys_fall_back_to_defaults() -> None:
    config = Config.from_mapping({"language": "fra"})

    assert config == Config(language="fra")


def test_unknown_keys_are_ignored() -> None:
    assert Config.from_mapping({"theme": "dark"}) == Config()


def test_string_values_are_stripped() -> None:
    assert Config.from_mapping({"hotkey": "  alt+q "}).hotkey == "alt+q"


@pytest.mark.parametrize(
    "data",
    [
        {"hotkey": 5},
        {"language": True},
        {"preprocess": "yes"},
        {"preprocess": 1},
    ],
)
def test_wrong_type_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ConfigError, match="must be of type"):
        Config.from_mapping(data)


@pytest.mark.parametrize("key", ["hotkey", "language"])
def test_empty_string_is_rejected(key: str) -> None:
    with pytest.raises(ConfigError, match="must not be empty"):
        Config.from_mapping({key: "   "})


def test_malformed_toml_is_rejected(config_file: Path) -> None:
    config_file.parent.mkdir()
    config_file.write_text("hotkey = ctrl+shift+t", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(config_file)


def test_byte_order_mark_is_tolerated(config_file: Path) -> None:
    config_file.parent.mkdir()
    config_file.write_text('language = "deu"\n', encoding="utf-8-sig")

    assert load_config(config_file).language == "deu"
