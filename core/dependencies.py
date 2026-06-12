from typing import Optional, Callable, Awaitable
from dataclasses import dataclass
from config.settings import Settings
from core.mcp_client import ObsidianMCPClient

@dataclass
class OrangeDeps:
    """Зависимости, которые передаются в агента (context)."""
    settings: Settings
    mcp_client: ObsidianMCPClient
    obsidian_vault_path: str = "test_vault"
    request_override: Optional[Callable[[str], Awaitable[bool]]] = None

