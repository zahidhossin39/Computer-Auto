"""Tests for configuration and intent loader."""

from pathlib import Path
import pytest
from src.config import load_config, load_intents, Intent, IntentAction


def test_load_default_intents():
    """Verify that intents.yaml loads correctly with valid schema."""
    intents = load_intents()
    assert len(intents) > 0

    # Verify key intents exist
    intent_names = {i.name for i in intents}
    assert "volume_up" in intent_names
    assert "volume_down" in intent_names
    assert "media_play_pause" in intent_names
    assert "launch_notepad" in intent_names
    assert "window_snap_left" in intent_names
    assert "window_close" in intent_names


def test_destructive_intent_flag():
    """Verify that potentially destructive actions are flagged."""
    intents = load_intents()
    close_intent = next(i for i in intents if i.name == "window_close")
    assert close_intent.is_destructive is True

    volume_intent = next(i for i in intents if i.name == "volume_up")
    assert volume_intent.is_destructive is False


def test_missing_config_raises_file_not_found(tmp_path):
    """Verify error on nonexistent file."""
    non_existent = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_intents(non_existent)


def test_invalid_yaml_raises_value_error(tmp_path):
    """Verify error on malformed YAML missing 'intents'."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("foo: bar", encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'intents' root key"):
        load_intents(bad_file)


def test_settings_json_overrides_env_api_key(tmp_path, monkeypatch):
    """Non-empty settings.json openrouter_api_key must override .env / os.environ."""
    import json
    import os
    from src import config as cfg_mod

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"openrouter_api_key": "sk-from-settings"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", settings_file)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-dotenv")

    load_config()
    assert os.environ["OPENROUTER_API_KEY"] == "sk-from-settings"


def test_empty_settings_api_key_preserves_env(tmp_path, monkeypatch):
    """Empty openrouter_api_key in settings.json leaves existing env var intact."""
    import json
    import os
    from src import config as cfg_mod

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"openrouter_api_key": "   "}), encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", settings_file)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-dotenv")

    load_config()
    assert os.environ["OPENROUTER_API_KEY"] == "sk-from-dotenv"


def test_optional_config_fields_defaults_and_overrides(tmp_path, monkeypatch):
    """theme, minimize_to_tray, and max_vision_steps load from settings.json with safe defaults."""
    import json
    from src import config as cfg_mod

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", settings_file)

    # Defaults when settings.json doesn't exist
    cfg_default = load_config()
    assert cfg_default.theme == "dark"
    assert cfg_default.minimize_to_tray is False
    assert cfg_default.max_vision_steps == 8

    # Valid overrides
    settings_file.write_text(
        json.dumps({"theme": "light", "minimize_to_tray": True, "max_vision_steps": 12}),
        encoding="utf-8",
    )
    cfg_custom = load_config()
    assert cfg_custom.theme == "light"
    assert cfg_custom.minimize_to_tray is True
    assert cfg_custom.max_vision_steps == 12

    # Invalid max_vision_steps falls back safely to default 8
    settings_file.write_text(json.dumps({"max_vision_steps": "bad"}), encoding="utf-8")
    cfg_bad = load_config()
    assert cfg_bad.max_vision_steps == 8
