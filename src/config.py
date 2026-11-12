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
DEFAULT_VISION_MODEL = "google/gemini-2.5-flash"
DEPRECATED_MODEL_MAP = {
    "google/gemini-3.1-flash-lite": DEFAULT_VISION_MODEL,
}
REPO_ROOT_ENV_PATH = Path(r"D:\Vibe-coding\Computer-Auto\.env")


def get_appdata_dir() -> Path:
    """Return the per-user AppData directory for Computer-Auto."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Computer-Auto"
    return Path.home() / "AppData" / "Roaming" / "Computer-Auto"


def _upgrade_model_id(model_id: Any) -> str:
    """Upgrade deprecated model slugs to their current replacement."""
    slug = str(model_id or "").strip()
    return DEPRECATED_MODEL_MAP.get(slug, slug)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    """Read a JSON object from *path*, returning {} on missing or invalid files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_dotenv_file(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE pairs from a .env file without mutating os.environ."""
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
        raw = dotenv_values(path)
        return {k: str(v) for k, v in raw.items() if k and v is not None}
    except Exception:
        result: Dict[str, str] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                k, v = stripped.split("=", 1)
                result[k.strip()] = v.strip().strip("\"'")
        except Exception:
            pass
        return result


def _env_candidate_paths() -> List[Path]:
    """Return deduplicated .env candidate paths in priority order."""
    candidates = [
        get_app_dir() / ".env",
        REPO_ROOT_ENV_PATH,
        get_appdata_dir() / ".env",
    ]
    seen: set[Path] = set()
    unique: List[Path] = []
    for p in candidates:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def _settings_candidate_paths() -> List[Path]:
    """Return deduplicated settings.json paths (app dir + AppData)."""
    candidates = [
        get_appdata_dir() / "settings.json",
        SETTINGS_PATH,
    ]
    seen: set[Path] = set()
    unique: List[Path] = []
    for p in candidates:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


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
    vision_model: str = DEFAULT_VISION_MODEL  # OpenRouter vision model
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
            repo_intents = Path(__file__).resolve().parent.parent / "intents.yaml"
            config_path = repo_intents if repo_intents.exists() else candidate

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


def load_merged_settings() -> Dict[str, Any]:
    """Load and merge settings.json from AppData and app dir, respecting newer .env keys.

    If a .env file has a non-empty OPENROUTER_API_KEY and settings.json either lacks a
    key or was not explicitly saved after that .env file, the .env key takes precedence.
    Deprecated model slugs are automatically upgraded.
    """
    existing_settings: List[tuple[float, Dict[str, Any]]] = []
    for path in _settings_candidate_paths():
        if path.is_file():
            data = _read_json_dict(path)
            if data:
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    mtime = 0.0
                existing_settings.append((mtime, data))

    # Merge oldest -> newest so the most recently saved settings.json wins
    existing_settings.sort(key=lambda item: item[0])
    merged: Dict[str, Any] = {}
    newest_settings_mtime = 0.0
    for mtime, data in existing_settings:
        merged.update(data)
        if mtime > newest_settings_mtime:
            newest_settings_mtime = mtime

    # Upgrade deprecated model IDs
    for model_field in ("vision_model", "stt_cloud_model"):
        if merged.get(model_field):
            merged[model_field] = _upgrade_model_id(merged[model_field])

    # Check .env candidates for OPENROUTER_API_KEY
    env_key = ""
    env_mtime = 0.0
    for env_path in _env_candidate_paths():
        if env_path.is_file():
            vals = _read_dotenv_file(env_path)
            candidate_key = str(vals.get("OPENROUTER_API_KEY") or "").strip()
            if candidate_key:
                try:
                    mtime = os.path.getmtime(env_path)
                except OSError:
                    mtime = 0.0
                if not env_key or mtime > env_mtime:
                    env_key = candidate_key
                    env_mtime = mtime

    settings_key = str(merged.get("openrouter_api_key") or "").strip()
    if env_key and (not settings_key or newest_settings_mtime <= env_mtime):
        merged["openrouter_api_key"] = env_key

    return merged


def save_merged_settings(data: Dict[str, Any]) -> None:
    """Persist settings to both app dir and AppData, and apply API key to os.environ."""
    merged = load_merged_settings()
    merged.update(data)

    for model_field in ("vision_model", "stt_cloud_model"):
        if merged.get(model_field):
            merged[model_field] = _upgrade_model_id(merged[model_field])

    payload = json.dumps(merged, indent=2)
    for path in _settings_candidate_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        except Exception:
            pass

    api_key = str(merged.get("openrouter_api_key") or "").strip()
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key


def load_settings() -> Dict[str, Any]:
    """Read the merged settings (AppData + app dir + .env precedence)."""
    return load_merged_settings()


def save_settings(values: Dict[str, Any]) -> None:
    """Write settings to both locations and apply the API key right away."""
    save_merged_settings(values)


def load_config() -> AppConfig:
    """Load full application configuration from merged settings and .env."""
    config = AppConfig(intents=load_intents())
    settings = load_merged_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key
    if settings.get("vision_model"):
        config.vision_model = _upgrade_model_id(settings["vision_model"]) or DEFAULT_VISION_MODEL
    if "use_jev" in settings:
        config.use_jev = bool(settings["use_jev"])
    if settings.get("stt_cloud_model") is not None:
        config.stt_cloud_model = _upgrade_model_id(settings["stt_cloud_model"])
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
