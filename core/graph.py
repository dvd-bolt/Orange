import os
import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from pydantic_graph import GraphBuilder, StepContext, End
from core.dependencies import OrangeDeps

@dataclass
class OrangeGraphState:
    user_prompt: str
    profile_name: str
    dynamic_instruction: Optional[str] = None
    chat_history_context: str = ""
    relevant_files_context: str = ""
    code_to_verify: Optional[str] = None
    verification_feedback: Optional[str] = None
    draft_response: Optional[str] = None
    output_text: Optional[str] = None
    loop_count: int = 0
    executed_code_output: Optional[str] = None
    attachments: List[Any] = field(default_factory=list)

# Create GraphBuilder
g = GraphBuilder(state_type=OrangeGraphState, deps_type=OrangeDeps, output_type=str)

@g.step
async def research_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> 'draft_node':
    """
    Research Node: Gathers context.
    Since history and BM25 hybrid search are already calculated in bridge.py,
    it verifies state variables and proceeds to draft.
    """
    print("[FSM] Entering Research Node...")
    # Ready to draft
    return draft_node

@g.step
async def draft_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> Union['verify_node', 'self_review_node']:
    """
    Draft Node: Invokes the Orange agent to generate/update the response.
    Injects any previous verification feedback if we are in a correction loop.
    """
    print(f"[FSM] Entering Draft Node (attempt {ctx.state.loop_count + 1})...")
    from core.agent import agent, HEAVY_MODEL, LITE_MODEL
    from core.profiles import PROFILES
    
    # 1. Prepare prompt payload
    prompt = ctx.state.user_prompt
    if ctx.state.verification_feedback:
        prompt = (
            f"Предыдущий запуск кода завершился ошибкой:\n"
            f"{ctx.state.verification_feedback}\n\n"
            f"Пожалуйста, исправь код и сгенерируй новый ответ.\n\n"
            f"Исходный запрос: {prompt}"
        )

    # Combine context
    full_prompt = ctx.state.chat_history_context + ctx.state.relevant_files_context + prompt
    
    # Select system prompt
    if ctx.state.dynamic_instruction:
        sys_prompt = ctx.state.dynamic_instruction
        current_model = HEAVY_MODEL
    else:
        sys_prompt = PROFILES.get(ctx.state.profile_name, PROFILES["base"])
        current_model = HEAVY_MODEL if ctx.state.profile_name in ["deep_research", "coder"] else LITE_MODEL
    
    # 2. Run agent
    print(f"[FSM] Running agent on model {current_model}...")
    run_payload = [full_prompt] + ctx.state.attachments
    res = await agent.run(
        run_payload,
        model=current_model,
        deps=ctx.deps,
        model_settings={"system_prompt": sys_prompt}
    )
    
    response_text = getattr(res, 'data', getattr(res, 'output', str(res)))
    ctx.state.draft_response = response_text
    
    # 3. Detect Python code block for verification
    code_blocks = re.findall(r"```python\n(.*?)```", response_text, re.DOTALL)
    if code_blocks:
        ctx.state.code_to_verify = code_blocks[-1].strip() # Check the last code block
        print(f"[FSM] Found Python code block. Routing to Verify Node.")
        return verify_node
    
    print(f"[FSM] No Python code block found. Routing to Self-Review Node.")
    return self_review_node

@g.step
async def verify_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> Union['draft_node', 'self_review_node']:
    """
    Verify Node: Performs pre-run static AST validation and executes code if permitted.
    """
    print("[FSM] Entering Verify Node...")
    code = ctx.state.code_to_verify
    if not code:
        return self_review_node
        
    # 1. Pre-run AST Syntax validation
    try:
        ast.parse(code)
    except SyntaxError as se:
        print(f"[FSM Verifier Warning] Static AST check failed: {se}")
        ctx.state.verification_feedback = f"Ошибка синтаксиса Python (AST check):\n{se}"
        ctx.state.loop_count += 1
        if ctx.state.loop_count < 3:
            return draft_node
        else:
            ctx.state.draft_response += f"\n\n**Ошибка валидации кода:**\n```text\n{se}\n```"
            return self_review_node

    # 2. Path and import validation (Safe local executor rules)
    # Check for disallowed system/subprocess imports for extra safety
    banned_imports = ["subprocess", "pty", "ctypes", "pickle"]
    found_banned = [imp for imp in banned_imports if re.search(fr"\b(import\s+{imp}|from\s+{imp})\b", code)]
    if found_banned:
        msg = f"Безопасность: Импорт библиотек {found_banned} запрещен в песочнице."
        print(f"[FSM Verifier Warning] Security violation: {msg}")
        ctx.state.verification_feedback = msg
        ctx.state.loop_count += 1
        if ctx.state.loop_count < 3:
            return draft_node
        else:
            ctx.state.draft_response += f"\n\n**Ошибка безопасности:**\n{msg}"
            return self_review_node

    # 3. Execution (Post-run)
    try:
        from core.tools import execute_python
        print("[FSM] Executing python sandbox via execute_python tool...")
        result = await execute_python(ctx, code)
        
        # If output reports CalledProcessError execution failure
        if "Ошибка выполнения скрипта" in result or "Критическая ошибка" in result:
            print("[FSM Verifier Warning] Sandbox execution failed.")
            ctx.state.verification_feedback = result
            ctx.state.loop_count += 1
            if ctx.state.loop_count < 3:
                return draft_node
            else:
                ctx.state.draft_response += f"\n\n{result}"
                return self_review_node
        
        # Success
        print("[FSM] Sandbox execution succeeded.")
        ctx.state.executed_code_output = result
        # Append results to draft response cleanly
        ctx.state.draft_response += f"\n\n### Результат выполнения кода:\n{result}"
        return self_review_node
        
    except Exception as e:
        print(f"[FSM Verifier Error] Exception during execution: {e}")
        ctx.state.verification_feedback = str(e)
        ctx.state.loop_count += 1
        if ctx.state.loop_count < 3:
            return draft_node
        else:
            ctx.state.draft_response += f"\n\n**Ошибка запуска песочницы:**\n{e}"
            return self_review_node

@g.step
async def self_review_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> End[str]:
    """
    Self-Review Node: Finalizes the output.
    Runs automatic Git backup of the vault, then terminates.
    """
    print("[FSM] Entering Self-Review Node. Finalizing response.")
    ctx.state.output_text = ctx.state.draft_response
    
    # Trigger Git auto-backup
    if ctx.deps.obsidian_vault_path:
        try:
            from core.git_backup import auto_backup_vault
            print(f"[FSM] Triggering automatic Git backup for vault: {ctx.deps.obsidian_vault_path}")
            backup_res = await auto_backup_vault(ctx.deps.obsidian_vault_path)
            print(f"[FSM] Git backup status: {backup_res}")
        except Exception as e:
            print(f"[FSM Warning] Failed to run Git backup: {e}")
            
    return End(ctx.state.output_text)


# Build the graph
g.add(g.edge_from(g.start_node).to(research_node))
g.add(g.edge_from(research_node).to(draft_node))
g.add(g.edge_from(draft_node).to(verify_node))
g.add(g.edge_from(draft_node).to(self_review_node))
g.add(g.edge_from(verify_node).to(draft_node))
g.add(g.edge_from(verify_node).to(self_review_node))
g.add(g.edge_from(self_review_node).to(g.end_node))

# Build graph runner
orange_fsm_graph = g.build()
