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


def get_appdata_settings_path() -> Path:
    """Return the authoritative per-user settings.json path in %APPDATA%."""
    return get_appdata_dir() / "settings.json"


def _is_masked_secret(value: str) -> bool:
    """Return True if *value* looks like a UI-masked placeholder rather than a real key."""
    s = value.strip()
    if not s:
        return False
    if "..." in s or "••••" in s:
        return True
    return set(s) <= {"*"}


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* atomically to *path* so readers never see truncated JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _settings_candidate_paths() -> List[Path]:
    """Return deduplicated settings.json paths (AppData first, legacy app dir second)."""
    candidates = [
        get_appdata_settings_path(),
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


def _read_first_env_key() -> str:
    """Return OPENROUTER_API_KEY from the highest-priority .env candidate if present."""
    for env_path in _env_candidate_paths():
        if env_path.is_file():
            vals = _read_dotenv_file(env_path)
            candidate_key = str(vals.get("OPENROUTER_API_KEY") or "").strip()
            if candidate_key:
                return candidate_key
    return ""


def _read_settings_without_env() -> Dict[str, Any]:
    """Load settings.json with %APPDATA%/Computer-Auto/settings.json as single source of truth.

    Legacy app-dir settings.json (SETTINGS_PATH) is used only as fallback for fields/keys
    absent from AppData, never overriding an AppData value or user-saved API key.
    """
    appdata_path = get_appdata_settings_path()
    legacy_path = SETTINGS_PATH

    legacy_data: Dict[str, Any] = {}
    try:
        same_file = legacy_path.resolve() == appdata_path.resolve()
    except Exception:
        same_file = legacy_path == appdata_path

    if not same_file and legacy_path.is_file():
        legacy_data = _read_json_dict(legacy_path)

    appdata_data: Dict[str, Any] = _read_json_dict(appdata_path) if appdata_path.is_file() else {}

    merged: Dict[str, Any] = dict(legacy_data)
    for k, v in appdata_data.items():
        # Never let an empty string in one field wipe a populated legacy key on first merge,
        # unless AppData already carries a non-empty key in either key field.
        if k in ("openrouter_api_key", "vision_api_key") and not str(v or "").strip():
            continue
        merged[k] = v

    for model_field in ("vision_model", "stt_cloud_model"):
        if merged.get(model_field):
            merged[model_field] = _upgrade_model_id(merged[model_field])

    openrouter_key = str(merged.get("openrouter_api_key") or "").strip()
    vision_key = str(merged.get("vision_api_key") or "").strip()
    if openrouter_key and not vision_key:
        merged["vision_api_key"] = openrouter_key
    elif vision_key and not openrouter_key:
        merged["openrouter_api_key"] = vision_key

    return merged


def load_merged_settings() -> Dict[str, Any]:
    """Load settings from %APPDATA%\\Computer-Auto\\settings.json (single source of truth).

    A dev .env file may seed OPENROUTER_API_KEY ONLY when settings.json has no saved key;
    it never overrides a key the user saved, regardless of file timestamps.
    """
    merged = _read_settings_without_env()
    settings_key = str(merged.get("openrouter_api_key") or merged.get("vision_api_key") or "").strip()

    if not settings_key:
        env_key = _read_first_env_key()
        if env_key:
            merged["openrouter_api_key"] = env_key
            merged["vision_api_key"] = env_key

    return merged


def save_merged_settings(data: Dict[str, Any]) -> None:
    """Persist settings to %APPDATA%\\Computer-Auto\\settings.json and apply API key to os.environ."""
    merged = _read_settings_without_env()
    clear_key = bool(data.get("clear_api_key"))

    clean_patch: Dict[str, Any] = {}
    for k, v in data.items():
        if k == "clear_api_key":
            continue
        if k in ("openrouter_api_key", "vision_api_key"):
            s = str(v or "").strip()
            if not s or _is_masked_secret(s):
                continue
            clean_patch[k] = s
        else:
            clean_patch[k] = v

    merged.update(clean_patch)

    if clear_key:
        merged.pop("openrouter_api_key", None)
        merged.pop("vision_api_key", None)
    else:
        api_base = str(merged.get("vision_api_base") or "https://openrouter.ai/api/v1").lower()
        if "vision_api_key" in clean_patch and "openrouter_api_key" not in clean_patch:
            if "openrouter.ai" in api_base or not str(merged.get("openrouter_api_key") or "").strip():
                merged["openrouter_api_key"] = clean_patch["vision_api_key"]
        if "openrouter_api_key" in clean_patch and "vision_api_key" not in clean_patch:
            merged["vision_api_key"] = clean_patch["openrouter_api_key"]

    for model_field in ("vision_model", "stt_cloud_model"):
        if merged.get(model_field):
            merged[model_field] = _upgrade_model_id(merged[model_field])

    payload = json.dumps(merged, indent=2)
    # Primary single source of truth: %APPDATA%\Computer-Auto\settings.json
    appdata_path = get_appdata_settings_path()
    _atomic_write_text(appdata_path, payload)

    # Best-effort mirror to legacy SETTINGS_PATH for dev/test compatibility
    for path in _settings_candidate_paths():
        if path == appdata_path:
            continue
        try:
            _atomic_write_text(path, payload)
        except Exception:
            pass

    api_key = str(merged.get("openrouter_api_key") or merged.get("vision_api_key") or "").strip()
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key
    elif clear_key:
        os.environ.pop("OPENROUTER_API_KEY", None)


def load_settings() -> Dict[str, Any]:
    """Read the merged settings (AppData authoritative + .env seed only when empty)."""
    return load_merged_settings()


def save_settings(values: Dict[str, Any]) -> None:
    """Write settings to AppData and apply the API key right away."""
    save_merged_settings(values)


def load_config() -> AppConfig:
    """Load full application configuration from merged settings and .env."""
    config = AppConfig(intents=load_intents())
    settings = load_merged_settings()
    api_key = str(settings.get("openrouter_api_key") or settings.get("vision_api_key") or "").strip()
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
    vkey = str(settings.get("vision_api_key") or settings.get("openrouter_api_key") or "").strip()
    if vkey:
        config.vision_api_key = vkey
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
