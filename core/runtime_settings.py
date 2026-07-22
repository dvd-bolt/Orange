from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path("config/settings.json")

DEFAULT_RUNTIME_SETTINGS: Dict[str, Any] = {
    "auth_token": "************************",
    "telemetry_stream": "ON",
    "telegram_daemon": "OFF",
    "auto_backup_enabled": "OFF",
    "auto_push_enabled": "OFF",
    "language": "ru",
}


def load_runtime_settings(path: str | Path = CONFIG_PATH) -> Dict[str, Any]:
    """Loads UI/runtime settings and backfills newly introduced defaults."""
    settings_path = Path(path)
    if not settings_path.exists():
        save_runtime_settings({}, settings_path)
        return DEFAULT_RUNTIME_SETTINGS.copy()

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    merged = DEFAULT_RUNTIME_SETTINGS.copy()
    merged.update(data)
    return merged


def save_runtime_settings(data: Dict[str, Any], path: str | Path = CONFIG_PATH) -> Dict[str, Any]:
    """Merges and persists runtime settings."""
    settings_path = Path(path)
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    merged = DEFAULT_RUNTIME_SETTINGS.copy()
    merged.update(existing)
    merged.update(data)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=4), encoding="utf-8")
    return merged


def runtime_flag(name: str, default: str = "OFF", path: str | Path = CONFIG_PATH) -> bool:
    return load_runtime_settings(path).get(name, default) == "ON"
