from typing import Any, Dict
from pydantic_ai import Agent, RunContext
from core.dependencies import OrangeDeps
from core import tools

import os
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

if "GOOGLE_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ:
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]

LITE_MODEL = os.environ.get("ORANGE_LITE_MODEL", "google:gemini-3.5-flash-lite")
HEAVY_MODEL = os.environ.get("ORANGE_HEAVY_MODEL", "google:gemini-3.6-flash")
SAFE_AGENT_MCP_TOOLS = {"list_notes", "read_note"}

def get_openrouter_model(model_name: str) -> OpenAIChatModel:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")
    provider = OpenRouterProvider(api_key=api_key)
    return OpenAIChatModel(
        model_name,
        provider=provider,
    )

class OrangeAgent(Agent):
    async def run(
        self,
        user_prompt,
        *,
        deps=None,
        model=None,
        message_history=None,
        model_settings=None,
        instructions=None,
        usage=None,
        metadata=None,
        **kwargs
    ):
        instructions_text = _instructions_text(instructions)
        run_metadata = metadata if isinstance(metadata, dict) else {}
        is_coder = run_metadata.get("orange_profile") == "coder" or (
            not run_metadata.get("orange_profile")
            and ("Coder mode" in instructions_text or "CODER PROFILE" in instructions_text)
        )
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")

        configured = os.environ.get("ORANGE_CODER_MODELS", "")
        coder_models = [
            name.strip()
            for name in configured.split(",")
            if name.strip()
        ]
        if is_coder and openrouter_key and coder_models:
            for coder_m_name in coder_models:
                try:
                    print(f"[ModelRouter] Routing CODER profile to OpenRouter model: {coder_m_name}")
                    m = get_openrouter_model(coder_m_name)
                    return await super().run(
                        user_prompt,
                        deps=deps,
                        model=m,
                        message_history=message_history,
                        model_settings=model_settings,
                        instructions=instructions,
                        usage=usage,
                        metadata=metadata,
                        **kwargs
                    )
                except Exception as e:
                    print(
                        f"[ModelRouter Warning] Coder model {coder_m_name} failed: "
                        f"{type(e).__name__}"
                    )
            print("[ModelRouter] Configured coder models failed; falling back to the per-run primary model.")

        try:
            target_model = model
            if isinstance(target_model, str):
                if target_model == 'gemini-3.1-flash-lite':
                    target_model = LITE_MODEL
                elif target_model in ('gemini-3.1-flash', 'gemini-3.1-pro-preview', 'gemini-3.5-flash'):
                    target_model = HEAVY_MODEL

            return await super().run(
                user_prompt,
                deps=deps,
                model=target_model,
                message_history=message_history,
                model_settings=model_settings,
                instructions=instructions,
                usage=usage,
                metadata=metadata,
                **kwargs
            )
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "resource exhausted" in err_str or "resource_exhausted" in err_str or "503" in err_str:
                failover_models = [
                    name.strip()
                    for name in os.environ.get("ORANGE_FAILOVER_MODELS", "openrouter/free").split(",")
                    if name.strip()
                ]
                if not openrouter_key:
                    raise
                print("[ModelRouter] Primary provider returned 429/503. Starting configured failover.")
                for f_model in failover_models:
                    try:
                        print(f"[ModelRouter] Routing to failover OpenRouter model: {f_model}")
                        m = get_openrouter_model(f_model)
                        return await super().run(
                            user_prompt,
                            deps=deps,
                            model=m,
                            message_history=message_history,
                            model_settings=model_settings,
                            instructions=instructions,
                            usage=usage,
                            metadata=metadata,
                            **kwargs
                        )
                    except Exception as fe:
                        print(
                            f"[ModelRouter Warning] Failover model {f_model} failed: "
                            f"{type(fe).__name__}"
                        )
            # Re-raise the error if failover didn't handle it or failed too
            raise e


def _instructions_text(instructions: Any) -> str:
    if isinstance(instructions, str):
        return instructions
    if isinstance(instructions, (list, tuple)):
        return "\n".join(item for item in instructions if isinstance(item, str))
    return ""

# Инициализируем агента с моделью gemini-3.1-flash-lite и зависимостями OrangeDeps
agent = OrangeAgent(
    LITE_MODEL,
    deps_type=OrangeDeps,
    defer_model_check=True,
)

# Регистрация инструментов из Rust-ядра
agent.tool(tools.scan_vault_fast)
agent.tool(tools.read_file_fast)
# Регистрация Playwright и новых инструментов
agent.tool(tools.deep_analyze_website)
agent.tool(tools.rewrite_file)
agent.tool(tools.patch_file)
agent.tool(tools.view_file_range)
agent.tool(tools.add_task)
agent.tool(tools.search_memory)
agent.tool(tools.fetch_url)
agent.tool(tools.list_existing_notes)
agent.tool(tools.scout_website)
agent.tool(tools.expand_note_links)

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
            if t.name not in SAFE_AGENT_MCP_TOOLS:
                continue
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
        return f"\n\nFailed to retrieve MCP tools list: {type(e).__name__}"

@agent.tool
async def call_obsidian_tool(ctx: RunContext[OrangeDeps], tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Проксирует вызов к MCP-серверу Obsidian.
    
    Args:
        tool_name: Read-only MCP tool name (`list_notes` or `read_note`).
        arguments: Словарь с аргументами, которые ожидает инструмент.
    """
    if not ctx.deps.mcp_client or not ctx.deps.mcp_client._session:
        return "[NOT_CONFIGURED] MCP client is not connected."
    if tool_name not in SAFE_AGENT_MCP_TOOLS:
        from core import db

        db.add_audit_event(
            "mcp_tool",
            "denied",
            f"Agent MCP tool blocked: {str(tool_name)[:80]}",
        )
        return (
            "[APPROVAL_DENIED] Agent-initiated MCP writes are disabled. "
            "Use an approval-gated vault write tool instead."
        )
    if not isinstance(arguments, dict):
        return "[VALIDATION_ERROR] MCP tool arguments must be an object."

    try:
        result = await ctx.deps.mcp_client.call_tool(tool_name, arguments)
        
        # Parse MCP response
        if hasattr(result, "content") and result.content:
            text_outputs = []
            for item in result.content:
                if item.type == "text":
                    text_outputs.append(str(item.text)[:1_000_000])
                else:
                    text_outputs.append(str(item)[:10_000])
            return "\n".join(text_outputs)[:1_000_000]
            
        return str(result)[:1_000_000]
    except Exception as e:
        return f"[PROVIDER_ERROR] MCP tool '{tool_name}' failed: {type(e).__name__}"
