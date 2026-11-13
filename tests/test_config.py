"""Tests for configuration and intent loader."""

import json
import os
from pathlib import Path
import pytest
from src import config as cfg_mod
from src.config import (
    DEFAULT_VISION_MODEL,
    Intent,
    IntentAction,
    load_config,
    load_intents,
    load_merged_settings,
    save_merged_settings,
)


@pytest.fixture(autouse=True)
def _isolate_host_paths(tmp_path, monkeypatch):
    """Prevent tests from reading/writing host AppData or D:\\Vibe-coding\\Computer-Auto\\.env."""
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", tmp_path / "app" / "settings.json")
    monkeypatch.setattr(cfg_mod, "REPO_ROOT_ENV_PATH", tmp_path / "repo" / ".env")
    monkeypatch.setattr(cfg_mod, "get_appdata_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(cfg_mod, "get_app_dir", lambda: tmp_path / "app")


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
    assert cfg_bad.vision_model == DEFAULT_VISION_MODEL


def test_dotenv_seeds_only_when_missing_and_never_clobbers_saved_key(tmp_path, monkeypatch):
    """A dev .env seeds OPENROUTER_API_KEY only when settings has none, and never clobbers a saved key."""
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    env_file = app_dir / ".env"
    settings_file = app_dir / "settings.json"
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", settings_file)

    # 1. No saved key -> .env seeds it
    env_file.write_text("OPENROUTER_API_KEY=sk-from-dotenv-seed\n", encoding="utf-8")
    merged = load_merged_settings()
    assert merged["openrouter_api_key"] == "sk-from-dotenv-seed"
    assert merged["vision_api_key"] == "sk-from-dotenv-seed"

    # 2. User saves their own key -> persisted to APPDATA and survives even a newer .env
    save_merged_settings({"vision_api_key": "sk-explicit-ui-save"})
    appdata_file = tmp_path / "appdata" / "settings.json"
    assert appdata_file.is_file()

    # Touch .env to be newer than settings.json with a different key
    saved_mtime = appdata_file.stat().st_mtime
    env_file.write_text("OPENROUTER_API_KEY=sk-from-dotenv-newer\n", encoding="utf-8")
    os.utime(env_file, (saved_mtime + 100, saved_mtime + 100))

    reloaded = load_merged_settings()
    assert reloaded["openrouter_api_key"] == "sk-explicit-ui-save"
    assert reloaded["vision_api_key"] == "sk-explicit-ui-save"

    # Saving another setting (without passing key) preserves the saved key and does not fall back to .env
    save_merged_settings({"theme": "light", "vision_api_key": ""})
    reloaded2 = load_merged_settings()
    assert reloaded2["theme"] == "light"
    assert reloaded2["openrouter_api_key"] == "sk-explicit-ui-save"
    assert os.environ["OPENROUTER_API_KEY"] == "sk-explicit-ui-save"


def test_simulated_upgrade_new_exe_dir_same_appdata_keeps_key(tmp_path, monkeypatch):
    """Simulated app update/reinstall (new exe dir, same APPDATA) keeps user-saved API key."""
    v1_dir = tmp_path / "install_v2_2"
    v1_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg_mod, "get_app_dir", lambda: v1_dir)
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", v1_dir / "settings.json")

    save_merged_settings({
        "vision_api_key": "sk-or-v1-user-persisted-key-9999",
        "vision_model": "anthropic/claude-sonnet-4.5",
        "theme": "light",
    })

    # Simulate installing v2.4 into a brand-new exe directory with a fresh .env and empty app-dir settings
    v2_dir = tmp_path / "install_v2_4"
    v2_dir.mkdir(parents=True, exist_ok=True)
    (v2_dir / ".env").write_text("OPENROUTER_API_KEY=sk-dev-override-should-not-win\n", encoding="utf-8")
    (v2_dir / "settings.json").write_text(json.dumps({"openrouter_api_key": ""}), encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "get_app_dir", lambda: v2_dir)
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", v2_dir / "settings.json")

    cfg = load_config()
    assert cfg.vision_api_key == "sk-or-v1-user-persisted-key-9999"
    assert cfg.vision_model == "anthropic/claude-sonnet-4.5"
    assert cfg.theme == "light"
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-v1-user-persisted-key-9999"


def test_save_ignores_masked_key_and_syncs_reload(tmp_path, monkeypatch):
    """Saving a masked placeholder from the UI must never overwrite the stored API key."""
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", tmp_path / "app" / "settings.json")
    save_merged_settings({"openrouter_api_key": "sk-or-v1-real-secret-1234"})
    save_merged_settings({"openrouter_api_key": "sk-or-v1...1234", "vision_api_key": "sk-or-••••••1234"})

    cfg = load_config()
    assert cfg.vision_api_key == "sk-or-v1-real-secret-1234"
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-v1-real-secret-1234"


def test_deprecated_model_auto_upgraded(tmp_path, monkeypatch):
    """Deprecated google/gemini-3.1-flash-lite is auto-upgraded to google/gemini-2.5-flash."""
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    settings_file = app_dir / "settings.json"
    settings_file.write_text(
        json.dumps({
            "vision_model": "google/gemini-3.1-flash-lite",
            "stt_cloud_model": "google/gemini-3.1-flash-lite",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", settings_file)

    cfg = load_config()
    assert cfg.vision_model == "google/gemini-2.5-flash"
    assert cfg.stt_cloud_model == "google/gemini-2.5-flash"
