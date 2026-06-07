import contextlib
import logging
from typing import Any, Dict, List
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

logger = logging.getLogger(__name__)

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
        try:
            if self.server_url.startswith("http://") or self.server_url.startswith("https://"):
                logger.info(f"Подключение к MCP серверу по SSE: {self.server_url}")
                sse_ctx = sse_client(self.server_url)
                streams = await self._exit_stack.enter_async_context(sse_ctx)
            else:
                logger.info(f"Подключение к MCP серверу через stdio: node {self.server_url}")
                server_params = StdioServerParameters(command="node", args=[self.server_url])
                stdio_ctx = stdio_client(server_params)
                streams = await self._exit_stack.enter_async_context(stdio_ctx)

            self._session = await self._exit_stack.enter_async_context(ClientSession(*streams))
            await self._session.initialize()
            logger.info("Успешно подключено к MCP серверу.")
        except Exception as e:
            logger.error(f"Ошибка при подключении к MCP серверу: {e}")
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
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Выполняет инструмент на стороне сервера."""
        if not self._session:
            raise RuntimeError("Клиент не подключен. Сначала вызовите connect().")
        return await self._session.call_tool(name, arguments=arguments)
