from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, Tuple

from config.settings import get_settings
from core.dependencies import OrangeDeps
from core.runtime_settings import load_runtime_settings, save_runtime_settings
from core.service_result import success

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SettingsService:
    """Runtime settings and local subsystem status facade."""

    def __init__(self, deps: OrangeDeps = None, get_http_endpoint: Callable[[], Tuple[str, int]] = None):
        self._deps = deps
        self._get_http_endpoint = get_http_endpoint or (lambda: ("127.0.0.1", 8080))

    def get_settings(self) -> Dict:
        runtime = load_runtime_settings()
        return success(runtime, **runtime)

    def save_settings(self, data) -> Dict:
        if isinstance(data, str):
            data = json.loads(data)
        saved = save_runtime_settings(data)
        print("[SettingsService] Settings saved to config/settings.json")
        return success(saved, "Settings saved.", **saved)

    def set_language(self, lang: str) -> Dict:
        saved = save_runtime_settings({"language": lang})
        print(f"[SettingsService] Language saved: {lang}")
        return success(saved, "Language saved.", **saved)

    def get_i18n_json(self) -> str:
        path = PROJECT_ROOT / "config" / "i18n.json"
        if not path.exists():
            return "{}"
        try:
            with path.open("r", encoding="utf-8") as file:
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
        vault_path = str(
            getattr(self._deps, "obsidian_vault_path", "")
            or getattr(settings, "obsidian_vault_path", "")
            or "—"
        )
        host, port = self._get_http_endpoint()
        runtime = load_runtime_settings()
        vault_exists = Path(vault_path).is_dir()
        mcp_configured = bool(getattr(settings, "mcp_server_url", None))
        telegram_enabled = runtime.get("telegram_daemon", "OFF") == "ON"
        telegram_session = PROJECT_ROOT / "config" / "orange_tg_session.session"
        telegram_configured = bool(
            os.environ.get("TELEGRAM_API_ID")
            and os.environ.get("TELEGRAM_API_HASH")
            and (os.environ.get("TELEGRAM_PHONE") or telegram_session.exists())
        )
        payload = {
            "obsidian_vault_path": vault_path,
            "orange_port": port or getattr(settings, "orange_port", 8080),
            "http_base_url": f"http://{host}:{port}",
            "vault_status": "READY" if vault_exists else "NOT_CONFIGURED",
            "mcp_status": (
                "CONNECTED"
                if mcp_connected
                else "OFFLINE" if mcp_configured else "NOT_CONFIGURED"
            ),
            "watchdog_path": os.path.join(vault_path, "_Inbox"),
            "watchdog_status": (
                "ACTIVE"
                if vault_exists and (Path(vault_path) / "_Inbox").is_dir()
                else "NOT_CONFIGURED"
            ),
            "google_api": "CONFIGURED" if bool(settings.gemini_api_key) else "NOT_CONFIGURED",
            "openrouter_api": "CONFIGURED" if bool(os.environ.get("OPENROUTER_API_KEY")) else "NOT_CONFIGURED",
            "telegram_status": (
                "OFF"
                if not telegram_enabled
                else "READY" if telegram_configured else "NOT_CONFIGURED"
            ),
        }
        return success(payload, **payload)

    def get_mcp_status(self) -> Dict:
        mcp_connected = (
            self._deps is not None
            and self._deps.mcp_client is not None
            and hasattr(self._deps.mcp_client, "_session")
            and self._deps.mcp_client._session is not None
        )
        from core.db import DB_PATH

        db_path = Path(DB_PATH)
        db_exists = db_path.exists()
        db_size_mb = round(db_path.stat().st_size / 1024 / 1024, 2) if db_exists else 0
        mcp_configured = bool(
            self._deps
            and getattr(self._deps.settings, "mcp_server_url", None)
        )
        payload = {
            "sqlite": {"status": "ONLINE" if db_exists else "ERROR", "size_mb": db_size_mb},
            "mcp": {
                "status": (
                    "CONNECTED"
                    if mcp_connected
                    else "OFFLINE" if mcp_configured else "NOT_CONFIGURED"
                )
            },
        }
        return success(payload, **payload)
