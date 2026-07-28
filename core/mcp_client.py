import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

class ObsidianMCPClient:
    """
    Асинхронный клиент для подключения к MCP-серверу (Obsidian).
    Поддерживает подключение как по SSE (http/https), так и через stdio.
    """
    def __init__(self, server_url: str):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._exit_stack = contextlib.AsyncExitStack()

    async def connect(self):
        """Устанавливает соединение с сервером."""
        if self._session is not None:
            return
        try:
            if self.server_url.startswith("http://") or self.server_url.startswith("https://"):
                logger.info(f"Подключение к MCP серверу по SSE: {self.server_url}")
                sse_ctx = sse_client(
                    self.server_url,
                    timeout=10,
                    sse_read_timeout=60,
                )
                streams = await self._exit_stack.enter_async_context(sse_ctx)
            else:
                server_params = self._stdio_server_parameters()
                logger.info(
                    "Подключение к MCP серверу через stdio: %s",
                    server_params.command,
                )
                stdio_ctx = stdio_client(server_params)
                streams = await self._exit_stack.enter_async_context(stdio_ctx)

            self._session = await self._exit_stack.enter_async_context(ClientSession(*streams))
            await asyncio.wait_for(self._session.initialize(), timeout=20.0)
            logger.info("Успешно подключено к MCP серверу.")
        except Exception as e:
            logger.error(
                "Ошибка при подключении к MCP серверу: %s",
                type(e).__name__,
            )
            self._session = None
            await self._exit_stack.aclose()
            self._exit_stack = contextlib.AsyncExitStack()
            raise

    async def disconnect(self):
        """Закрывает соединение с сервером."""
        await self._exit_stack.aclose()
        self._session = None
        logger.info("Соединение с MCP сервером закрыто.")

    async def get_tools(self) -> List[Any]:
        """Получает список доступных инструментов от сервера."""
        if not self._session:
            raise RuntimeError("Клиент не подключен. Сначала вызовите connect().")
        result = await asyncio.wait_for(
            self._session.list_tools(),
            timeout=30.0,
        )
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Выполняет инструмент на стороне сервера."""
        if not self._session:
            raise RuntimeError("Клиент не подключен. Сначала вызовите connect().")
        return await asyncio.wait_for(
            self._session.call_tool(name, arguments=arguments),
            timeout=30.0,
        )

    def _stdio_server_parameters(self) -> StdioServerParameters:
        configured = Path(self.server_url).expanduser()
        server_path = (
            configured
            if configured.is_absolute()
            else PROJECT_ROOT / configured
        ).resolve(strict=False)
        if not server_path.is_file():
            raise FileNotFoundError("Configured MCP server file does not exist.")

        configured_runtime = os.environ.get("ORANGE_MCP_RUNTIME", "").strip()
        if configured_runtime:
            runtime = configured_runtime
        elif server_path.suffix.lower() == ".ts":
            runtime = shutil.which("bun") or ""
        else:
            runtime = shutil.which("node") or ""
        if not runtime:
            expected = "Bun" if server_path.suffix.lower() == ".ts" else "Node.js"
            raise RuntimeError(f"{expected} runtime is not available for MCP.")

        args = (
            ["run", str(server_path)]
            if Path(runtime).name.lower().startswith("bun")
            else [str(server_path)]
        )
        child_env = {
            key: value
            for key in (
                "PATH",
                "HOME",
                "USER",
                "TMPDIR",
                "TEMP",
                "TMP",
                "LANG",
                "LC_ALL",
                "OBSIDIAN_VAULT_PATH",
            )
            if (value := os.environ.get(key)) is not None
        }
        return StdioServerParameters(
            command=runtime,
            args=args,
            cwd=str(PROJECT_ROOT),
            env=child_env,
        )
