from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"

DEFAULT_RUNTIME_SETTINGS: Dict[str, Any] = {
    "telemetry_stream": "ON",
    "telegram_daemon": "OFF",
    "auto_backup_enabled": "OFF",
    "auto_push_enabled": "OFF",
    "language": "ru",
}
ALLOWED_RUNTIME_KEYS = set(DEFAULT_RUNTIME_SETTINGS)
_settings_lock = threading.RLock()


def load_runtime_settings(path: str | Path = CONFIG_PATH) -> Dict[str, Any]:
    """Loads UI/runtime settings and backfills newly introduced defaults."""
    settings_path = Path(path)
    with _settings_lock:
        if not settings_path.exists():
            save_runtime_settings({}, settings_path)
            return DEFAULT_RUNTIME_SETTINGS.copy()

        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        merged = DEFAULT_RUNTIME_SETTINGS.copy()
        merged.update(_validate_runtime_values(data, strict=False))
        return merged


def save_runtime_settings(data: Dict[str, Any], path: str | Path = CONFIG_PATH) -> Dict[str, Any]:
    """Merges and persists runtime settings."""
    settings_path = Path(path)
    if not isinstance(data, dict):
        raise ValueError("Runtime settings must be a JSON object.")
    with _settings_lock:
        existing = {}
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        merged = DEFAULT_RUNTIME_SETTINGS.copy()
        merged.update(_validate_runtime_values(existing, strict=False))
        merged.update(_validate_runtime_values(data, strict=True))
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        from core.file_ops import sync_atomic_write

        sync_atomic_write(
            settings_path,
            json.dumps(merged, indent=4, ensure_ascii=False) + "\n",
        )
        return merged


def runtime_flag(name: str, default: str = "OFF", path: str | Path = CONFIG_PATH) -> bool:
    return load_runtime_settings(path).get(name, default) == "ON"


def _validate_runtime_values(data: Dict[str, Any], *, strict: bool) -> Dict[str, Any]:
    validated = {}
    for key, value in data.items():
        if key not in ALLOWED_RUNTIME_KEYS:
            continue
        if key == "language":
            if value not in {"ru", "en"}:
                if strict:
                    raise ValueError("language must be 'ru' or 'en'.")
                continue
        elif value not in {"ON", "OFF"}:
            if strict:
                raise ValueError(f"{key} must be 'ON' or 'OFF'.")
            continue
        validated[key] = value
    return validated
