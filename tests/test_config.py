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
