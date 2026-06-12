from typing import Any, Dict
from pydantic_ai import Agent, RunContext
from core.dependencies import OrangeDeps
from core import tools

import os
import subprocess
import time
import asyncio
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

LITE_MODEL = 'google:gemini-3.1-flash-lite'
HEAVY_MODEL = 'google:gemini-3.1-flash'

_heavy_limiter_lock = asyncio.Lock()
_lite_limiter_lock = asyncio.Lock()
_last_heavy_time = 0.0
_last_lite_time = 0.0

def get_openrouter_model(model_name: str) -> OpenAIModel:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    provider = OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    return OpenAIModel(
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
        usage=None,
        **kwargs
    ):
        # 1. Check if it's the CODER profile
        is_coder = False
        if model_settings and "system_prompt" in model_settings:
            sys_prompt = model_settings["system_prompt"]
            if "Coder mode" in sys_prompt:
                is_coder = True

        if is_coder:
            # Route to OpenRouter free coder models with cascade failover
            coder_models = ["qwen/qwen3-coder:free", "nex-agi/nex-n2-pro:free", "openrouter/free"]
            last_err = None
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
                        usage=usage,
                        **kwargs
                    )
                except Exception as e:
                    print(f"[ModelRouter Warning] Coder model {coder_m_name} failed: {e}")
                    last_err = e
            # If all failed, throw the error
            raise last_err or RuntimeError("All free OpenRouter coder models failed.")

        # 2. Base / RAG profile with Automatic Failover for Gemini 429/503
        try:
            # Map default model names to google: prefix if not present to avoid deprecation warnings
            target_model = model
            if isinstance(target_model, str):
                if target_model == 'gemini-3.1-flash-lite':
                    target_model = LITE_MODEL
                elif target_model == 'gemini-3.5-flash':
                    target_model = HEAVY_MODEL
            
            # Local Rate Limiter checks before calling Google API
            resolved_model = target_model or self.model
            if resolved_model == HEAVY_MODEL:
                async with _heavy_limiter_lock:
                    global _last_heavy_time
                    now = time.time()
                    elapsed = now - _last_heavy_time
                    if elapsed < 12.0:
                        sleep_time = 12.0 - elapsed
                        print(f"[COOLING_DOWN] Оптимизация частоты для Heavy-модели. Пауза {sleep_time:.2f}с...")
                        await asyncio.sleep(sleep_time)
                    _last_heavy_time = time.time()
            elif resolved_model == LITE_MODEL:
                async with _lite_limiter_lock:
                    global _last_lite_time
                    now = time.time()
                    elapsed = now - _last_lite_time
                    if elapsed < 4.0:
                        sleep_time = 4.0 - elapsed
                        await asyncio.sleep(sleep_time)
                    _last_lite_time = time.time()
            
            return await super().run(
                user_prompt,
                deps=deps,
                model=target_model,
                message_history=message_history,
                model_settings=model_settings,
                usage=usage,
                **kwargs
            )
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "resource exhausted" in err_str or "resource_exhausted" in err_str or "503" in err_str:
                print(f"[ModelRouter] Gemini returned 429/503. Starting cascade failover to OpenRouter...")
                failover_models = ["google/gemma-4-26b-a4b-it:free", "meta-llama/llama-3.3-70b-instruct:free"]
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
                            usage=usage,
                            **kwargs
                        )
                    except Exception as fe:
                        print(f"[ModelRouter Warning] Failover model {f_model} failed: {fe}")
            # Re-raise the error if failover didn't handle it or failed too
            raise e

# Инициализируем агента с моделью gemini-3.1-flash-lite и зависимостями OrangeDeps
agent = OrangeAgent(
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
