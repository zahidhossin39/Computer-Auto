"""Tests for the headless JSON-Lines stdio bridge (src/bridge.py)."""

import io
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from src import config as cfg_mod
from src.bridge import StdioBridge
from src.config import Intent, IntentAction


def _make_fake_daemon():
    daemon = Mock()
    daemon.config = SimpleNamespace(
        vision_model="google/gemini-2.5-flash",
        vision_api_base="https://openrouter.ai/api/v1",
        vision_api_key="",
        stt_cloud_model="",
        theme="dark",
        max_vision_steps=8,
        use_jev=True,
        intents=[
            Intent(
                name="volume_up",
                category="system",
                triggers=["volume up", "louder"],
                action=IntentAction(type="system_action", command="volume_step_up"),
                is_destructive=False,
            ),
            Intent(
                name="window_close",
                category="window",
                triggers=["close window"],
                action=IntentAction(type="system_action", command="window_close_active"),
                is_destructive=True,
            ),
        ],
    )
    daemon.recognizer = SimpleNamespace(has_local_model=False, is_ready=True, cloud_model="")
    daemon.router = SimpleNamespace(use_jev=True)
    daemon.vision = SimpleNamespace(
        model_name="google/gemini-2.5-flash",
        api_base="https://openrouter.ai/api/v1",
        api_key="",
        mock_mode=False,
    )
    daemon.recorder = SimpleNamespace(on_level=None)
    daemon.hotkey_listener = SimpleNamespace(
        detector=SimpleNamespace(is_listening=False),
        start=Mock(),
    )
    daemon.continuous = False
    daemon._listening_active = False
    return daemon


def _parse_events(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_bridge_get_state_and_startup_events(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-1234567890abcd")
    out = io.StringIO()
    daemon = _make_fake_daemon()
    bridge = StdioBridge(daemon=daemon, out_stream=out)

    bridge.handle_message({"cmd": "get_state"})
    events = _parse_events(out)
    kinds = [e["event"] for e in events]
    assert kinds == ["state", "settings", "intents"]

    settings_ev = events[1]["data"]
    assert settings_ev["vision_model"] == "google/gemini-2.5-flash"
    assert settings_ev["has_api_key"] is True
    assert settings_ev["masked_key"] == "sk-or-v1...abcd"
    assert settings_ev["has_local_model"] is False
    assert "app_version" in settings_ev

    intents_ev = events[2]["data"]
    assert len(intents_ev) == 2
    assert intents_ev[0]["name"] == "volume_up"
    assert intents_ev[0]["destructive"] is False
    assert intents_ev[1]["name"] == "window_close"
    assert intents_ev[1]["destructive"] is True


def test_bridge_command_dispatch():
    out = io.StringIO()
    daemon = _make_fake_daemon()
    bridge = StdioBridge(daemon=daemon, out_stream=out)

    bridge.handle_message({"cmd": "run_command", "text": "open notepad"})
    daemon.on_manual_command.assert_called_once_with("open notepad")

    bridge.handle_message({"cmd": "toggle_mic"})
    daemon.toggle_session.assert_called_once()

    bridge.handle_message({"cmd": "start_mic"})
    assert daemon.continuous is True
    daemon.on_listening_toggle.assert_called_with(True)

    daemon._listening_active = True
    bridge.handle_message({"cmd": "stop_mic"})
    assert daemon.continuous is False
    daemon.on_listening_toggle.assert_called_with(False)

    bridge.handle_message({"cmd": "set_continuous", "enabled": True})
    assert daemon.continuous is True
    assert daemon.hotkey_listener.detector.is_listening is True

    bridge.handle_message({"cmd": "panic"})
    daemon.on_panic_key.assert_called_once()

    bridge.handle_message({"cmd": "confirm_guardrail", "approved": True})
    daemon.confirm_pending.assert_called_once_with(True, asynchronous=True)


def test_bridge_save_settings_syncs_files_and_daemon(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_mod, "SETTINGS_PATH", tmp_path / "app" / "settings.json")
    monkeypatch.setattr(cfg_mod, "REPO_ROOT_ENV_PATH", tmp_path / "repo" / ".env")
    monkeypatch.setattr(cfg_mod, "get_appdata_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(cfg_mod, "get_app_dir", lambda: tmp_path / "app")

    out = io.StringIO()
    daemon = _make_fake_daemon()
    bridge = StdioBridge(daemon=daemon, out_stream=out)

    bridge.handle_message({
        "cmd": "save_settings",
        "settings": {
            "openrouter_api_key": "sk-or-v1-updatedkey9999",
            "vision_model": "google/gemini-3.1-flash-lite",
            "stt_cloud_model": "openai/gpt-4o-transcribe",
            "theme": "light",
            "max_vision_steps": 12,
            "use_jev": False,
        },
    })

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-v1-updatedkey9999"
    assert daemon.config.vision_model == "google/gemini-2.5-flash"
    assert daemon.vision.model_name == "google/gemini-2.5-flash"
    assert daemon.vision.api_key == "sk-or-v1-updatedkey9999"
    assert daemon.recognizer.cloud_model == "openai/gpt-4o-transcribe"
    assert daemon.router.use_jev is False
    assert (tmp_path / "app" / "settings.json").is_file()
    assert (tmp_path / "appdata" / "settings.json").is_file()

    events = _parse_events(out)
    assert [e["event"] for e in events] == ["settings", "state"]
    assert events[0]["data"]["theme"] == "light"
    assert events[0]["data"]["max_vision_steps"] == 12


def test_bridge_download_model_and_cancel():
    out = io.StringIO()
    daemon = _make_fake_daemon()

    def fake_download(progress_cb=None):
        if progress_cb:
            progress_cb(50, 100, "Downloading...")
            progress_cb(100, 100, "Ready")
        daemon.recognizer.has_local_model = True
        return True

    daemon.download_offline_model.side_effect = fake_download
    bridge = StdioBridge(daemon=daemon, out_stream=out)

    bridge.handle_message({"cmd": "download_model"})
    bridge._download_thread.join(timeout=2.0)

    events = _parse_events(out)
    progress = [e for e in events if e["event"] == "download_progress"]
    assert len(progress) == 2
    assert progress[-1] == {"event": "download_progress", "done": 100, "total": 100, "stage": "Ready"}
    settings_events = [e for e in events if e["event"] == "settings"]
    assert settings_events[-1]["data"]["has_local_model"] is True

    bridge.handle_message({"cmd": "cancel_download"})
    daemon.cancel_model_download.assert_called_once()


def test_bridge_serve_forever_handles_audio_logs_and_bad_json():
    out = io.StringIO()
    daemon = _make_fake_daemon()
    bridge = StdioBridge(daemon=daemon, out_stream=out)

    stdin_data = io.StringIO('not-valid-json\n{"cmd": "panic"}\n')
    bridge.serve_forever(in_stream=stdin_data, start_hotkeys=True)

    daemon.hotkey_listener.start.assert_called_once()
    daemon.on_panic_key.assert_called_once()
    daemon.shutdown.assert_called_once()

    daemon.recorder.on_level(0.75)
    daemon.ui.log("[GUARDRAIL]: Confirm close?")
    daemon.ui.log("[TIER 2 VISION]: Planning")
    daemon.ui.log("[EXECUTED]: Done")

    events = _parse_events(out)
    assert any(e["event"] == "audio_level" and e["level"] == 0.75 for e in events)
    assert any(e["event"] == "log" and e["kind"] == "guardrail" for e in events)
    assert any(e["event"] == "log" and e["kind"] == "vision" for e in events)
    assert any(e["event"] == "log" and e["kind"] == "action" for e in events)
    assert any(e["event"] == "log" and e["kind"] == "error" for e in events)
