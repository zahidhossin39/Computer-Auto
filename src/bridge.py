"""Headless JSON-Lines stdio bridge for the Rust Tauri desktop UI.

Run with:
    python -u -m src.bridge
    python -u src/bridge.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
from typing import Any, Dict, List, Optional, TextIO

# Support both `python -m src.bridge` and `python src/bridge.py`
if __package__ is None or __package__ == "":
    _REPO_ROOT = str(Path(__file__).resolve().parent.parent)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from src.config import DEFAULT_VISION_MODEL, _upgrade_model_id, save_merged_settings

try:
    from src.updater import APP_VERSION
except Exception:
    APP_VERSION = "1.0.0"


def _mask_key(key: str) -> str:
    """Return a masked representation of an API key for UI display."""
    k = key.strip()
    if not k:
        return ""
    if len(k) <= 12:
        return "*" * len(k)
    return f"{k[:8]}...{k[-4:]}"


def _classify_log_kind(line: str) -> str:
    """Classify a daemon log line into UI log categories."""
    upper = line.upper()
    if "[GUARDRAIL]" in upper or "[PANIC]" in upper:
        return "guardrail"
    if "[ERROR]" in upper or "[AUDIO WARNING]" in upper or "VISION ERROR" in upper or "FAILED" in upper:
        return "error"
    if "[TIER 2 VISION]" in upper or "[AGENT STEP" in upper:
        return "vision"
    if "[EXECUTED]" in upper or "[TIER 1 ROUTER]" in upper or "[COMMAND]" in upper or "[ANSWER]" in upper:
        return "action"
    return "info"


class _BridgeUIAdapter:
    """Lightweight headless UI adapter attached to ComputerAutoDaemon.ui."""

    def __init__(self, bridge: "StdioBridge"):
        self._bridge = bridge

    def update_state(self, state: str, message: str, detail: str = "") -> None:
        self._bridge.emit_state(state, message, detail)

    def log(self, message: str) -> None:
        self._bridge.emit_log(message)

    def set_transcript(self, text: str) -> None:
        self._bridge.emit_log(f'[STT]: "{text}"', kind="info")

    def set_ghost(self, ghost: bool) -> None:
        pass

    def update_queue(
        self,
        pending: List[Dict[str, str]],
        running: Optional[Dict[str, str]] = None,
    ) -> None:
        self._bridge.emit_queue(pending, running)


class StdioBridge:
    """JSON-Lines stdio bridge wrapping ComputerAutoDaemon without Tkinter."""

    def __init__(
        self,
        daemon: Optional[Any] = None,
        out_stream: Optional[TextIO] = None,
    ):
        self._out: TextIO = out_stream or sys.stdout
        self._write_lock = threading.Lock()
        self._download_thread: Optional[threading.Thread] = None
        self._queue_emit_seq = 0

        if daemon is None:
            from main import ComputerAutoDaemon
            daemon = ComputerAutoDaemon(ui_mode="none")

        self.daemon = daemon
        self.daemon.ui = _BridgeUIAdapter(self)
        if hasattr(self.daemon, "recorder") and hasattr(self.daemon.recorder, "on_level"):
            self.daemon.recorder.on_level = self.emit_audio_level

        has_key = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
        if not getattr(self.daemon.recognizer, "is_ready", True) and not has_key:
            self._current_state = (
                "ready",
                "Offline voice model missing — open Settings to download",
                "Typed commands still work",
            )
        else:
            self._current_state = ("ready", "Ready", "Double-tap Left Ctrl or type a command")

    def emit(self, payload: Dict[str, Any]) -> None:
        """Write one JSON-Lines event to stdout, thread-safely."""
        line = json.dumps(payload, ensure_ascii=False)
        with self._write_lock:
            self._out.write(line + "\n")
            self._out.flush()

    def emit_state(self, state: str, text: str, detail: str = "") -> None:
        self._current_state = (state, text, detail)
        self.emit({"event": "state", "state": state, "text": text, "detail": detail})

    def emit_audio_level(self, level: float) -> None:
        try:
            clamped = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            clamped = 0.0
        self.emit({"event": "audio_level", "level": clamped})

    def emit_log(self, line: str, kind: Optional[str] = None) -> None:
        resolved_kind = kind or _classify_log_kind(line)
        self.emit({"event": "log", "line": str(line), "kind": resolved_kind})

    def build_settings_payload(self) -> Dict[str, Any]:
        """Build the current settings snapshot for the UI."""
        cfg = self.daemon.config
        api_key = str(os.environ.get("OPENROUTER_API_KEY") or "").strip()
        return {
            "vision_model": getattr(cfg, "vision_model", DEFAULT_VISION_MODEL),
            "vision_api_base": getattr(cfg, "vision_api_base", "https://openrouter.ai/api/v1"),
            "vision_api_key": api_key,
            "stt_cloud_model": getattr(cfg, "stt_cloud_model", ""),
            "theme": getattr(cfg, "theme", "dark"),
            "max_vision_steps": int(getattr(cfg, "max_vision_steps", 8)),
            "use_jev": bool(getattr(cfg, "use_jev", True)),
            "has_api_key": bool(api_key),
            "masked_key": _mask_key(api_key),
            "has_local_model": bool(getattr(self.daemon.recognizer, "has_local_model", False)),
            "app_version": APP_VERSION,
        }

    def emit_settings(self) -> None:
        self.emit({"event": "settings", "data": self.build_settings_payload()})

    def build_intents_payload(self) -> List[Dict[str, Any]]:
        """Serialize loaded intents for the Commands view."""
        items: List[Dict[str, Any]] = []
        for intent in getattr(self.daemon.config, "intents", []):
            action = getattr(intent, "action", None)
            desc = (
                getattr(action, "command", None)
                or getattr(action, "target", None)
                or intent.name.replace("_", " ").title()
            )
            items.append({
                "name": intent.name,
                "description": str(desc),
                "phrases": list(getattr(intent, "triggers", [])),
                "category": getattr(intent, "category", "general"),
                "destructive": bool(getattr(intent, "is_destructive", False)),
            })
        return items

    def emit_intents(self) -> None:
        self.emit({"event": "intents", "data": self.build_intents_payload()})

    def emit_download_progress(self, done: int, total: int, stage: str) -> None:
        self.emit({
            "event": "download_progress",
            "done": int(done),
            "total": int(total),
            "stage": str(stage),
        })

    def _get_daemon_queue_snapshot(self) -> tuple[List[Dict[str, str]], Optional[Dict[str, str]]]:
        snap_fn = getattr(self.daemon, "get_queue_snapshot", None)
        if callable(snap_fn):
            try:
                res = snap_fn()
                if (
                    isinstance(res, tuple)
                    and len(res) == 2
                    and isinstance(res[0], list)
                    and (res[1] is None or isinstance(res[1], dict))
                ):
                    return res[0], res[1]
            except Exception:
                pass
        return [], None

    def emit_queue(
        self,
        pending: Optional[List[Dict[str, str]]] = None,
        running: Optional[Dict[str, str]] = None,
    ) -> None:
        if pending is None and running is None:
            pending, running = self._get_daemon_queue_snapshot()
        norm_pending = [
            {"id": str(item.get("id", "")), "text": str(item.get("text", ""))}
            for item in (pending or [])
            if isinstance(item, dict)
        ]
        norm_running = (
            {"id": str(running.get("id", "")), "text": str(running.get("text", ""))}
            if isinstance(running, dict)
            else None
        )
        self._queue_emit_seq += 1
        self.emit({
            "event": "queue",
            "pending": norm_pending,
            "running": norm_running,
        })

    @staticmethod
    def _get_learned_module() -> Optional[Any]:
        try:
            from src import learned
            return learned
        except Exception:
            return None

    def _call_learned_helper(self, fn_name: str, *args: Any) -> List[Dict[str, Any]]:
        mod = self._get_learned_module()
        if mod is None:
            return []
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            try:
                res = fn(*args)
                if isinstance(res, list):
                    return res
            except Exception:
                pass
        list_fn = getattr(mod, "bridge_list_learned", None) or getattr(mod, "list_commands", None)
        if callable(list_fn):
            try:
                res = list_fn()
                if isinstance(res, list):
                    return res
            except Exception:
                pass
        return []

    def emit_learned(self, data: Optional[List[Dict[str, Any]]] = None) -> None:
        if data is None:
            data = self._call_learned_helper("bridge_list_learned")
        self.emit({"event": "learned", "data": list(data)})

    def emit_mcp_config(self, snippet: Optional[str] = None) -> None:
        if snippet is None:
            mod = self._get_learned_module()
            fn = getattr(mod, "get_mcp_config_snippet", None) if mod is not None else None
            if callable(fn):
                try:
                    snippet = str(fn())
                except Exception:
                    snippet = None
            if not snippet:
                repo_root = str(Path(__file__).resolve().parent.parent)
                snippet = json.dumps(
                    {
                        "mcpServers": {
                            "computer-auto": {
                                "command": "python",
                                "args": ["-m", "src.mcp_server"],
                                "cwd": repo_root,
                            }
                        }
                    },
                    indent=2,
                )
        self.emit({"event": "mcp_config", "data": str(snippet)})

    def _apply_settings(self, raw: Dict[str, Any]) -> None:
        """Persist settings and hot-reload daemon components without restart."""
        to_save: Dict[str, Any] = {}
        cfg = self.daemon.config

        if "openrouter_api_key" in raw:
            key = str(raw.get("openrouter_api_key") or "").strip()
            if key:
                to_save["openrouter_api_key"] = key
                os.environ["OPENROUTER_API_KEY"] = key

        if raw.get("vision_model"):
            model = _upgrade_model_id(raw["vision_model"]) or DEFAULT_VISION_MODEL
            to_save["vision_model"] = model
            cfg.vision_model = model

        if "stt_cloud_model" in raw and raw["stt_cloud_model"] is not None:
            stt_model = _upgrade_model_id(raw["stt_cloud_model"])
            to_save["stt_cloud_model"] = stt_model
            cfg.stt_cloud_model = stt_model

        if raw.get("vision_api_base"):
            base = str(raw["vision_api_base"]).strip()
            to_save["vision_api_base"] = base
            cfg.vision_api_base = base

        if "vision_api_key" in raw and raw["vision_api_key"] is not None:
            vkey = str(raw["vision_api_key"]).strip()
            to_save["vision_api_key"] = vkey
            cfg.vision_api_key = vkey

        if raw.get("theme"):
            theme = str(raw["theme"]).strip()
            to_save["theme"] = theme
            cfg.theme = theme

        if "use_jev" in raw:
            use_jev = bool(raw["use_jev"])
            to_save["use_jev"] = use_jev
            cfg.use_jev = use_jev

        if "max_vision_steps" in raw and raw["max_vision_steps"] is not None:
            try:
                steps = int(raw["max_vision_steps"])
                if steps > 0:
                    to_save["max_vision_steps"] = steps
                    cfg.max_vision_steps = steps
            except (TypeError, ValueError):
                pass

        save_merged_settings(to_save)

        if hasattr(self.daemon, "router") and self.daemon.router is not None:
            self.daemon.router.use_jev = cfg.use_jev

        if hasattr(self.daemon, "recognizer") and self.daemon.recognizer is not None:
            self.daemon.recognizer.cloud_model = cfg.stt_cloud_model

        if hasattr(self.daemon, "vision") and self.daemon.vision is not None:
            self.daemon.vision.model_name = cfg.vision_model
            self.daemon.vision.api_base = cfg.vision_api_base.rstrip("/")
            effective_key = cfg.vision_api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
            if effective_key:
                self.daemon.vision.api_key = effective_key
                self.daemon.vision.mock_mode = False

        self.emit_settings()
        self.emit_state(*self._current_state)

    def _start_download_model(self) -> None:
        """Start offline Parakeet model download on a background thread."""
        if self._download_thread is not None and self._download_thread.is_alive():
            self.emit_log("[STT]: Offline model download already in progress.", kind="info")
            return

        def _worker() -> None:
            self.daemon.download_offline_model(progress_cb=self.emit_download_progress)
            self.emit_settings()

        self._download_thread = threading.Thread(target=_worker, daemon=True)
        self._download_thread.start()

    def handle_message(self, msg: Dict[str, Any]) -> None:
        """Dispatch one parsed JSON command from stdin."""
        cmd = str(msg.get("cmd") or "").strip()
        if not cmd:
            return

        if cmd == "get_state":
            self.emit_state(*self._current_state)
            self.emit_settings()
            self.emit_intents()
            self.emit_queue()
            if self._get_learned_module() is not None:
                self.emit_learned()
                self.emit_mcp_config()
        elif cmd == "run_command":
            text = str(msg.get("text") or "").strip()
            if text:
                self.daemon.on_manual_command(text)
        elif cmd == "clear_queue":
            prev_seq = self._queue_emit_seq
            if hasattr(self.daemon, "clear_queue"):
                self.daemon.clear_queue()
            if self._queue_emit_seq == prev_seq:
                self.emit_queue([], None)
        elif cmd == "remove_queued":
            task_id = str(msg.get("id") or "").strip()
            prev_seq = self._queue_emit_seq
            if hasattr(self.daemon, "remove_queued"):
                self.daemon.remove_queued(task_id)
            if self._queue_emit_seq == prev_seq:
                self.emit_queue(*self._get_daemon_queue_snapshot())
        elif cmd == "list_learned":
            self.emit_learned()
        elif cmd == "approve_learned":
            cmd_id = str(msg.get("id") or "").strip()
            self.emit_learned(self._call_learned_helper("bridge_approve_learned", cmd_id))
        elif cmd == "toggle_learned":
            cmd_id = str(msg.get("id") or "").strip()
            enabled = bool(msg.get("enabled", True))
            self.emit_learned(self._call_learned_helper("bridge_toggle_learned", cmd_id, enabled))
        elif cmd == "delete_learned":
            cmd_id = str(msg.get("id") or "").strip()
            self.emit_learned(self._call_learned_helper("bridge_delete_learned", cmd_id))
        elif cmd == "get_mcp_config":
            self.emit_mcp_config()
        elif cmd == "toggle_mic":
            self.daemon.toggle_session()
        elif cmd == "start_mic":
            if not getattr(self.daemon, "_listening_active", False):
                self.daemon.continuous = True
                self.daemon.hotkey_listener.detector.is_listening = True
                self.daemon.on_listening_toggle(True)
        elif cmd == "stop_mic":
            if getattr(self.daemon, "_listening_active", False) or getattr(self.daemon, "continuous", False):
                self.daemon.continuous = False
                self.daemon.hotkey_listener.detector.is_listening = False
                self.daemon.on_listening_toggle(False)
        elif cmd == "set_continuous":
            enabled = bool(msg.get("enabled", False))
            self.daemon.continuous = enabled
            self.daemon.hotkey_listener.detector.is_listening = enabled
        elif cmd == "panic":
            self.daemon.on_panic_key()
        elif cmd == "confirm_guardrail":
            approved = bool(msg.get("approved", False))
            self.daemon.confirm_pending(approved, asynchronous=True)
        elif cmd == "save_settings":
            settings_data = msg.get("settings")
            if isinstance(settings_data, dict):
                self._apply_settings(settings_data)
        elif cmd == "download_model":
            self._start_download_model()
        elif cmd == "cancel_download":
            self.daemon.cancel_model_download()
        else:
            self.emit_log(f"[BRIDGE]: Unknown command '{cmd}'", kind="error")

    def serve_forever(self, in_stream: Optional[TextIO] = None, start_hotkeys: bool = True) -> None:
        """Read JSON-Lines commands from stdin until EOF."""
        stream = in_stream or sys.stdin
        if start_hotkeys:
            try:
                self.daemon.hotkey_listener.start()
            except Exception as e:
                self.emit_log(f"[BRIDGE]: Hotkey listener unavailable ({e})", kind="error")

        # Emit initial state/settings/intents/queue immediately on startup
        self.emit_state(*self._current_state)
        self.emit_settings()
        self.emit_intents()
        self.emit_queue()
        if self._get_learned_module() is not None:
            self.emit_learned()
            self.emit_mcp_config()

        try:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as e:
                    self.emit_log(f"[BRIDGE]: Invalid JSON input: {e}", kind="error")
                    continue
                if isinstance(msg, dict):
                    try:
                        self.handle_message(msg)
                    except Exception as e:
                        self.emit_log(f"[BRIDGE]: Command error: {e}", kind="error")
        except KeyboardInterrupt:
            pass
        finally:
            try:
                wait_fn = getattr(self.daemon, "wait_for_queue", None)
                if callable(wait_fn):
                    wait_fn(timeout=15.0)
            except Exception:
                pass
            try:
                self.daemon.shutdown()
            except Exception:
                pass


def main() -> None:
    if sys.platform == "win32":
        for stream_name in ("stdin", "stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is not None and hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception:
                    pass

    # Reserve real stdout exclusively for JSON-Lines events; route print() to stderr + logs/app.log
    json_out = sys.stdout
    try:
        from src.config import get_app_dir
        log_dir = get_app_dir() / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)

        class _TeeStderr:
            def __init__(self, stream, lf):
                self._stream = stream
                self._log = lf

            def write(self, message):
                try:
                    self._stream.write(message)
                except Exception:
                    pass
                try:
                    self._log.write(message)
                except Exception:
                    pass

            def flush(self):
                try:
                    self._stream.flush()
                except Exception:
                    pass
                try:
                    self._log.flush()
                except Exception:
                    pass

            def __getattr__(self, name):
                return getattr(self._stream, name)

        sys.stdout = _TeeStderr(sys.stderr, log_file)
    except Exception:
        sys.stdout = sys.stderr

    bridge = StdioBridge(out_stream=json_out)
    bridge.serve_forever()


if __name__ == "__main__":
    main()
