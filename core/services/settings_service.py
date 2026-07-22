from __future__ import annotations

import json
import os
from typing import Callable, Dict, Tuple

from config.settings import get_settings
from core.dependencies import OrangeDeps
from core.runtime_settings import load_runtime_settings, save_runtime_settings


class SettingsService:
    """Runtime settings and local subsystem status facade."""

    def __init__(self, deps: OrangeDeps = None, get_http_endpoint: Callable[[], Tuple[str, int]] = None):
        self._deps = deps
        self._get_http_endpoint = get_http_endpoint or (lambda: ("127.0.0.1", 8080))

    def get_settings(self) -> Dict:
        return load_runtime_settings()

    def save_settings(self, data) -> bool:
        if isinstance(data, str):
            data = json.loads(data)
        save_runtime_settings(data)
        print("[SettingsService] Settings saved to config/settings.json")
        return True

    def set_language(self, lang: str) -> bool:
        save_runtime_settings({"language": lang})
        print(f"[SettingsService] Language saved: {lang}")
        return True

    def get_i18n_json(self) -> str:
        path = "config/i18n.json"
        if not os.path.exists(path):
            return "{}"
        try:
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
        except Exception:
            return "{}"

    def get_http_base_url(self) -> str:
        host, port = self._get_http_endpoint()
        return f"http://{host}:{port}"

    def get_system_status(self) -> Dict:
        settings = get_settings()
        mcp_connected = (
            self._deps is not None
            and self._deps.mcp_client is not None
            and hasattr(self._deps.mcp_client, "_session")
            and self._deps.mcp_client._session is not None
        )
        vault_path = str(getattr(settings, "obsidian_vault_path", "") or "—")
        host, port = self._get_http_endpoint()
        return {
            "obsidian_vault_path": vault_path,
            "orange_port": port or getattr(settings, "orange_port", 8080),
            "http_base_url": f"http://{host}:{port}",
            "mcp_status": "CONNECTED" if mcp_connected else "OFFLINE",
            "watchdog_path": os.path.join(vault_path, "_Inbox"),
        }

    def get_mcp_status(self) -> Dict:
        mcp_connected = (
            self._deps is not None
            and self._deps.mcp_client is not None
            and hasattr(self._deps.mcp_client, "_session")
            and self._deps.mcp_client._session is not None
        )
        db_path = "orange_memory.db"
        db_exists = os.path.exists(db_path)
        db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2) if db_exists else 0
        return {
            "sqlite": {"status": "ONLINE" if db_exists else "ERROR", "size_mb": db_size_mb},
            "mcp": {"status": "CONNECTED" if mcp_connected else "OFFLINE"},
        }
