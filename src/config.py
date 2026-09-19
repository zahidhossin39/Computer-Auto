"""Configuration and intent registry loader."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

# What the Settings tab writes. Holds the API key, so .gitignore covers it.
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"


@dataclass
class IntentAction:
    type: str  # "system_action", "launch_app", "shell"
    command: Optional[str] = None
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
    double_tap_threshold_ms: int = 400
    sample_rate: int = 16000
    stt_provider: str = "sherpa-onnx"
    stt_model_dir: str = "models/parakeet-tdt-0.6b-int8"
    vision_model: str = "qwen/qwen3-vl-8b-instruct"  # OpenRouter vision model (tested: accurate, ~$0.0003/call)
    use_jev: bool = True  # Jev understands commands the trigger list misses


def load_intents(config_path: Optional[Path] = None) -> List[Intent]:
    """Load and validate intents from intents.yaml."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "intents.yaml"

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
    if values.get("openrouter_api_key"):
        os.environ["OPENROUTER_API_KEY"] = values["openrouter_api_key"]


def load_config() -> AppConfig:
    """Load full application configuration; saved settings win over the defaults."""
    config = AppConfig(intents=load_intents())
    settings = load_settings()
    if settings.get("openrouter_api_key"):
        os.environ.setdefault("OPENROUTER_API_KEY", settings["openrouter_api_key"])
    if settings.get("vision_model"):
        config.vision_model = settings["vision_model"]
    config.use_jev = settings.get("use_jev", True)
    return config
