import os
import re
import ast
import sqlite3
import json
from dataclasses import dataclass, field, asdict
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
    session_id: str = "default_session"

# --- SQLite Serialization / Checkpointing Helpers ---

async def save_graph_state(session_id: str, step_name: str, state: OrangeGraphState):
    """Serializes the current OrangeGraphState into SQLite."""
    conn = sqlite3.connect("orange_memory.db")
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS graph_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                step_name TEXT,
                state_json TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Convert state to dict, handle non-serializable fields
        state_dict = asdict(state)
        state_dict["attachments"] = [str(x) for x in state_dict.get("attachments", [])]
        state_json = json.dumps(state_dict)
        conn.execute(
            "INSERT INTO graph_checkpoints (session_id, step_name, state_json) VALUES (?, ?, ?)",
            (session_id, step_name, state_json)
        )
        conn.commit()
    except Exception as e:
        print(f"[FSM Checkpoint Error] Failed to save state: {e}")
    finally:
        conn.close()

async def load_graph_state(session_id: str) -> Optional[OrangeGraphState]:
    """Retrieves the latest checkpointed OrangeGraphState from SQLite."""
    conn = sqlite3.connect("orange_memory.db")
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT state_json FROM graph_checkpoints WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            data = json.loads(row["state_json"])
            from dataclasses import fields
            valid_keys = {f.name for f in fields(OrangeGraphState)}
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            return OrangeGraphState(**filtered_data)
    except Exception as e:
        print(f"[FSM Checkpoint Error] Failed to load state: {e}")
    finally:
        conn.close()
    return None


# Create GraphBuilder
g = GraphBuilder(state_type=OrangeGraphState, deps_type=OrangeDeps, output_type=str)

@g.step
async def research_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> Union['draft_node', 'deep_research_node', 'project_manager_node']:
    """
    Research Node: Gathers context.
    Routes to profile-specific nodes: deep_research, project_manager, coder, base.
    """
    print(f"[FSM] Entering Research Node... Profile: {ctx.state.profile_name}")
    await save_graph_state(ctx.state.session_id, "research_node", ctx.state)
    
    # Profile-specific transitions
    if ctx.state.profile_name == "deep_research":
        return deep_research_node
    elif ctx.state.profile_name == "project_manager":
        return project_manager_node
    else:
        return draft_node

@g.step
async def deep_research_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> 'draft_node':
    """
    Deep Research Node: Gathers findings from OSINT / external research.
    """
    print("[FSM] Entering Deep Research Node...")
    ctx.state.relevant_files_context += "\n[OSINT Research: Mock external web search completed]"
    await save_graph_state(ctx.state.session_id, "deep_research_node", ctx.state)
    return draft_node

@g.step
async def project_manager_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> 'self_review_node':
    """
    Project Manager Node: Runs automated routing and task adding.
    """
    print("[FSM] Entering Project Manager Node...")
    from core.tools import add_task
    class MockRunContext:
        def __init__(self, deps):
            self.deps = deps
    ctx_mock = MockRunContext(ctx.deps)
    try:
        # PM profile routing: automatically add task
        res = await add_task(ctx_mock, "PM_Tasks.md", "Task created by PM node transition")
        ctx.state.draft_response = f"PM Action Result: {res}"
    except Exception as e:
        ctx.state.draft_response = f"PM Action Error: {e}"
        
    await save_graph_state(ctx.state.session_id, "project_manager_node", ctx.state)
    return self_review_node

@g.step
async def draft_node(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> Union['verify_node', 'self_review_node']:
    """
    Draft Node: Invokes the Orange agent to generate/update the response.
    """
    print(f"[FSM] Entering Draft Node (attempt {ctx.state.loop_count + 1})...")
    await save_graph_state(ctx.state.session_id, "draft_node", ctx.state)
    
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
        base_sys_prompt = ctx.state.dynamic_instruction
        current_model = HEAVY_MODEL
    else:
        base_sys_prompt = PROFILES.get(ctx.state.profile_name, PROFILES["base"])
        current_model = HEAVY_MODEL if ctx.state.profile_name in ["deep_research", "coder"] else LITE_MODEL
        
    # Slayered Context Walk-up scanning
    from core.profiles import buildSessionContext, buildIdentityContext
    import glob
    
    note_title_match = re.search(r"Obsidian Note:\s*'(.*?)'", ctx.state.user_prompt)
    current_note_path = None
    vault_path = ctx.deps.obsidian_vault_path
    if note_title_match:
        note_title = note_title_match.group(1)
        matches = glob.glob(os.path.join(vault_path, "**", f"{note_title}.md"), recursive=True)
        if matches:
            current_note_path = matches[0]
            
    identity_context = buildIdentityContext(vault_path) if vault_path else ""
    walkup_context = buildSessionContext(vault_path, current_note_path) if vault_path else ""
    
    # Загрузка динамических навыков (skills) на основе запроса пользователя
    from core.skills import load_relevant_skills
    skills_context = ""
    api_key = ctx.deps.settings.gemini_api_key
    if api_key and vault_path:
        skills_context = await load_relevant_skills(vault_path, ctx.state.user_prompt, api_key)
    
    sys_prompt = base_sys_prompt
    if identity_context:
        sys_prompt += identity_context
    if walkup_context:
        sys_prompt += f"\n\n=== SYSTEM DIRECTORIES CONTEXT ===\n{walkup_context}"
    if skills_context:
        sys_prompt += skills_context
    
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
    # For 'coder' profile, code block is mandatory for routing to verify.
    # For others, we might skip verify if not requested.
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
    Verify Node: Performs static AST validation and executes code.
    """
    print("[FSM] Entering Verify Node...")
    await save_graph_state(ctx.state.session_id, "verify_node", ctx.state)
    
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
    Self-Review Node: Finalizes output and performs Git auto-backup.
    """
    print("[FSM] Entering Self-Review Node. Finalizing response.")
    ctx.state.output_text = ctx.state.draft_response
    await save_graph_state(ctx.state.session_id, "self_review_node", ctx.state)
    
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
g.add(g.edge_from(research_node).to(deep_research_node))
g.add(g.edge_from(research_node).to(project_manager_node))
g.add(g.edge_from(research_node).to(draft_node))
g.add(g.edge_from(deep_research_node).to(draft_node))
g.add(g.edge_from(project_manager_node).to(self_review_node))
g.add(g.edge_from(draft_node).to(verify_node))
g.add(g.edge_from(draft_node).to(self_review_node))
g.add(g.edge_from(verify_node).to(draft_node))
g.add(g.edge_from(verify_node).to(self_review_node))
g.add(g.edge_from(self_review_node).to(g.end_node))

# Build graph runner
orange_fsm_graph = g.build()
