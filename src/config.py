"""Configuration and intent registry loader."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


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
    gemini_model: str = "gemini-2.5-flash"  # Flash model for vision reasoning


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


def load_config() -> AppConfig:
    """Load full application configuration."""
    intents = load_intents()
    return AppConfig(intents=intents)
