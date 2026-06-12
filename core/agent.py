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
agent.tool(tools.scan_vault_fast)
agent.tool(tools.read_file_fast)
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
def system_prompt_vault_path(ctx: RunContext[OrangeDeps]) -> str:
    return f"Current Obsidian Vault Root path: '{ctx.deps.obsidian_vault_path}'."

@agent.system_prompt
async def inject_mcp_tools(ctx: RunContext[OrangeDeps]) -> str:
    """
    Dynamically loads the list of available tools from MCP and
    injects them into the agent's system prompt.
    """
    if not ctx.deps.mcp_client or not ctx.deps.mcp_client._session:
        return "\n\nMCP Tools are not connected."

    try:
        mcp_tools = await ctx.deps.mcp_client.get_tools()
        tools_info = []
        for t in mcp_tools:
            tools_info.append(f"- {t.name}: {t.description} (Schema: {t.inputSchema})")
        
        if tools_info:
            tools_text = "\n".join(tools_info)
            return (
                "\n\nYOU HAVE THE FOLLOWING MCP TOOLS AVAILABLE FOR OBSIDIAN:\n"
                f"{tools_text}\n\n"
                "Use the tool 'call_obsidian_tool' passing 'tool_name' and 'arguments' (dict) "
                "to invoke these tools and interact with the vault."
            )
        return "\n\nNo available MCP tools found."
    except Exception as e:
        return f"\n\nFailed to retrieve MCP tools list: {e}"

@agent.tool
async def call_obsidian_tool(ctx: RunContext[OrangeDeps], tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Проксирует вызов к MCP-серверу Obsidian.
    
    Args:
        tool_name: Имя инструмента (например, 'read_file', 'write_file').
        arguments: Словарь с аргументами, которые ожидает инструмент.
    """
    if not ctx.deps.mcp_client or not ctx.deps.mcp_client._session:
        return "Error: MCP client is not connected."

    try:
        result = await ctx.deps.mcp_client.call_tool(tool_name, arguments)
        
        # Parse MCP response
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
        return f"Error executing tool '{tool_name}': {str(e)}"
