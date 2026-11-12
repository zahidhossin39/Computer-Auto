"""Configuration and intent registry loader."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import yaml


def get_app_dir() -> Path:
    """Return the directory holding user-mutable files (settings.json, .env, models/).

    When frozen by PyInstaller, sys.executable's directory is used rather than
    sys._MEIPASS so portable user configs and models live alongside the .exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# What the Settings tab writes. Holds the API key, so .gitignore covers it.
SETTINGS_PATH = get_app_dir() / "settings.json"


@dataclass
class IntentAction:
    type: str  # "system_action", "launch_app", "hotkey", "open_app", "type_text", "open_url"
    command: Optional[str] = None
    keys: List[str] = field(default_factory=list)  # for "hotkey": ["ctrl", "t"]
    target: Optional[str] = None
    fallback_target: Optional[str] = None
    args: List[str] = field(default_factory=list)


@dataclass
class Intent:
    name: str
    category: str
    triggers: List[str]
    action: IntentAction
    is_destructive: bool = False


@dataclass
class AppConfig:
    intents: List[Intent]
    double_tap_threshold_ms: int = 600  # 400ms missed real double-taps (measured 449ms)
    sample_rate: int = 16000
    stt_provider: str = "sherpa-onnx"
    stt_model_dir: str = "models/parakeet-tdt-0.6b-int8"
    vision_model: str = "qwen/qwen3-vl-8b-instruct"  # OpenRouter vision model (tested: accurate, ~$0.0003/call)
    use_jev: bool = True  # Jev understands commands the trigger list misses
    stt_cloud_model: str = ""  # "" = on-device Parakeet; else an OpenRouter transcription model
    vision_api_base: str = "https://openrouter.ai/api/v1"  # any OpenAI-compatible endpoint
    vision_api_key: str = ""  # "" = the OpenRouter key
    theme: str = "dark"
    minimize_to_tray: bool = False
    max_vision_steps: int = 8


def load_intents(config_path: Optional[Path] = None) -> List[Intent]:
    """Load and validate intents from intents.yaml."""
    if config_path is None:
        candidate = get_app_dir() / "intents.yaml"
        if candidate.exists():
            config_path = candidate
        elif getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            config_path = Path(sys._MEIPASS) / "intents.yaml"
        else:
            config_path = candidate

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "intents" not in data:
        raise ValueError("Invalid intents.yaml format: missing 'intents' root key")

    intents: List[Intent] = []
    for item in data["intents"]:
        action_data = item.get("action", {})
        action = IntentAction(
            type=action_data.get("type", "system_action"),
            command=action_data.get("command"),
            target=action_data.get("target"),
            fallback_target=action_data.get("fallback_target"),
            args=action_data.get("args", []),
            keys=action_data.get("keys", []),
        )
        intent = Intent(
            name=item["name"],
            category=item.get("category", "general"),
            triggers=[t.lower().strip() for t in item.get("triggers", [])],
            action=action,
            is_destructive=item.get("is_destructive", False),
        )
        intents.append(intent)

    return intents


def load_settings() -> Dict[str, Any]:
    """Read the settings the user saved in the Settings tab."""
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(values: Dict[str, Any]) -> None:
    """Write settings and apply the API key right away, so no restart is needed."""
    SETTINGS_PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")
    api_key = str(values.get("openrouter_api_key") or "").strip()
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key


def load_config() -> AppConfig:
    """Load full application configuration; saved settings win over the defaults and .env."""
    config = AppConfig(intents=load_intents())
    settings = load_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key
    if settings.get("vision_model"):
        config.vision_model = str(settings["vision_model"])
    if "use_jev" in settings:
        config.use_jev = bool(settings["use_jev"])
    if settings.get("stt_cloud_model") is not None:
        config.stt_cloud_model = str(settings["stt_cloud_model"])
    if settings.get("vision_api_base"):
        config.vision_api_base = str(settings["vision_api_base"])
    if settings.get("vision_api_key") is not None:
        config.vision_api_key = str(settings["vision_api_key"])
    if settings.get("theme"):
        config.theme = str(settings["theme"])
    if "minimize_to_tray" in settings:
        config.minimize_to_tray = bool(settings["minimize_to_tray"])
    raw_steps = settings.get("max_vision_steps")
    if raw_steps is not None:
        try:
            steps_val = int(raw_steps)
            if steps_val > 0:
                config.max_vision_steps = steps_val
        except (TypeError, ValueError):
            pass
    return config
