from typing import Any, Dict
from pydantic_ai import Agent, RunContext
from core.dependencies import OrangeDeps
from core import tools

LITE_MODEL = 'gemini-3.1-flash-lite'
HEAVY_MODEL = 'gemini-3.5-flash'

# Инициализируем агента с моделью gemini-3.1-flash-lite и зависимостями OrangeDeps
agent = Agent(
    LITE_MODEL,
    deps_type=OrangeDeps,
)

# Регистрация инструментов из Rust-ядра
agent.tool_plain(tools.scan_vault_fast)
agent.tool_plain(tools.read_file_fast)
agent.tool_plain(tools.fetch_website_fast)

# Регистрация Playwright и новых инструментов
agent.tool(tools.deep_analyze_website)
agent.tool(tools.rewrite_file)
agent.tool(tools.add_task)
agent.tool(tools.search_memory)
agent.tool(tools.fetch_url)
agent.tool(tools.deep_research)
agent.tool(tools.execute_python)
agent.tool(tools.list_existing_notes)

@agent.system_prompt
async def inject_mcp_tools(ctx: RunContext[OrangeDeps]) -> str:
    """
    Динамически подгружает список доступных инструментов из MCP и 
    добавляет их в системный промпт агента, чтобы он знал, какие инструменты может вызывать.
    """
    # Если MCP клиент не инициализирован (например, выключен в конфиге)
    if not ctx.deps.mcp_client or not ctx.deps.mcp_client._session:
        return "\n\nИнструменты MCP не подключены."

    try:
        mcp_tools = await ctx.deps.mcp_client.get_tools()
        tools_info = []
        for t in mcp_tools:
            tools_info.append(f"- {t.name}: {t.description} (Схема аргументов: {t.inputSchema})")
        
        if tools_info:
            tools_text = "\n".join(tools_info)
            return (
                "\n\nТЕБЕ ДОСТУПНЫ СЛЕДУЮЩИЕ ИНСТРУМЕНТЫ MCP ДЛЯ РАБОТЫ С OBSIDIAN:\n"
                f"{tools_text}\n\n"
                "Используй tool 'call_obsidian_tool', передавая в него 'tool_name' и 'arguments' (словарь), "
                "чтобы вызывать эти инструменты и взаимодействовать с хранилищем."
            )
        return "\n\nДоступных инструментов MCP не найдено."
    except Exception as e:
        return f"\n\nНе удалось получить список инструментов MCP: {e}"

@agent.tool
async def call_obsidian_tool(ctx: RunContext[OrangeDeps], tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Проксирует вызов к MCP-серверу Obsidian.
    
    Args:
        tool_name: Имя инструмента (например, 'read_file', 'write_file').
        arguments: Словарь с аргументами, которые ожидает инструмент.
    """
    if not ctx.deps.mcp_client or not ctx.deps.mcp_client._session:
        return "Ошибка: MCP клиент не подключен."

    try:
        result = await ctx.deps.mcp_client.call_tool(tool_name, arguments)
        
        # Парсим ответ от MCP. Обычно возвращается объект, у которого есть поле content.
        if hasattr(result, "content") and result.content:
            text_outputs = []
            for item in result.content:
                if item.type == "text":
                    text_outputs.append(item.text)
                else:
                    text_outputs.append(str(item))
            return "\n".join(text_outputs)
            
        return str(result)
    except Exception as e:
        return f"Ошибка при выполнении инструмента '{tool_name}': {str(e)}"
