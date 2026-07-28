from __future__ import annotations
import os
import re
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Union
from pydantic_graph import GraphBuilder, StepContext, End, BaseNode, GraphRunContext
from core.dependencies import OrangeDeps
from core.db import DB_PATH

@dataclass
class OrangeGraphState:
    user_prompt: str
    profile_name: str
    research_query: Optional[str] = None
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
    conn = sqlite3.connect(DB_PATH)
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
        state_dict["attachments"] = []
        state_json = json.dumps(state_dict)
        conn.execute(
            "INSERT INTO graph_checkpoints (session_id, step_name, state_json) VALUES (?, ?, ?)",
            (session_id, step_name, state_json)
        )
        conn.execute(
            """
            DELETE FROM graph_checkpoints
            WHERE session_id = ?
              AND id NOT IN (
                  SELECT id FROM graph_checkpoints
                  WHERE session_id = ?
                  ORDER BY id DESC
                  LIMIT 20
              )
            """,
            (session_id, session_id),
        )
        conn.commit()
    except Exception as e:
        print(f"[FSM Checkpoint Error] Failed to save state: {type(e).__name__}")
    finally:
        conn.close()

async def load_graph_state(session_id: str) -> Optional[OrangeGraphState]:
    """Retrieves the latest checkpointed OrangeGraphState from SQLite."""
    conn = sqlite3.connect(DB_PATH)
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
        print(f"[FSM Checkpoint Error] Failed to load state: {type(e).__name__}")
    finally:
        conn.close()
    return None


async def delete_graph_state(session_id: str) -> None:
    """Remove checkpoints for transient, non-chat runs."""
    def delete_rows():
        conn = sqlite3.connect(DB_PATH)
        try:
            try:
                conn.execute(
                    "DELETE FROM graph_checkpoints WHERE session_id = ?",
                    (session_id,),
                )
            except sqlite3.OperationalError:
                return
            conn.commit()
        finally:
            conn.close()

    import asyncio

    await asyncio.to_thread(delete_rows)


# --- Class-Based BaseNode Topologies ---

@dataclass
class ResearchNode(BaseNode[OrangeGraphState, OrangeDeps, str]):
    """
    Research Node: Gathers context.
    Routes to profile-specific nodes: deep_research, project_manager, coder, base.
    """
    async def run(self, ctx: GraphRunContext[OrangeGraphState, OrangeDeps]) -> DraftNode | DeepResearchNode | ProjectManagerNode:
        print(f"[FSM] Entering Research Node... Profile: {ctx.state.profile_name}")
        from core.bridge import log_to_telemetry
        log_to_telemetry("EXEC", f"FSM: Entering Research Node (profile: {ctx.state.profile_name})")
        await save_graph_state(ctx.state.session_id, "research_node", ctx.state)
        
        # Profile-specific transitions
        if ctx.state.profile_name == "deep_research":
            return DeepResearchNode()
        elif ctx.state.profile_name == "project_manager":
            return ProjectManagerNode()
        else:
            return DraftNode()

@dataclass
class DeepResearchNode(BaseNode[OrangeGraphState, OrangeDeps, str]):
    """
    Deep Research Node: Gathers findings from OSINT / external research.
    """
    async def run(self, ctx: GraphRunContext[OrangeGraphState, OrangeDeps]) -> DraftNode | End[str]:
        print("[FSM] Entering Deep Research Node...")
        from core.bridge import log_to_telemetry
        log_to_telemetry("EXEC", "FSM: Entering Deep Research Node")
        await save_graph_state(ctx.state.session_id, "deep_research_node", ctx.state)
        from core.research import (
            ResearchProviderError,
            ResearchUnavailableError,
            collect_web_research,
            format_research_context,
        )

        try:
            research = await collect_web_research(
                ctx.state.research_query or ctx.state.user_prompt
            )
        except ResearchUnavailableError as exc:
            message = f"[NOT_CONFIGURED] {exc}"
            log_to_telemetry("WARN", message)
            return End(message)
        except ResearchProviderError as exc:
            message = f"[PROVIDER_ERROR] {exc}"
            log_to_telemetry("WARN", message)
            return End(message)

        ctx.state.relevant_files_context += format_research_context(research)
        return DraftNode()

@dataclass
class ProjectManagerNode(BaseNode[OrangeGraphState, OrangeDeps, str]):
    """
    Project Manager Node: Runs automated routing and task adding.
    """
    async def run(self, ctx: GraphRunContext[OrangeGraphState, OrangeDeps]) -> DraftNode:
        print("[FSM] Entering Project Manager Node...")
        from core.bridge import log_to_telemetry
        log_to_telemetry("EXEC", "FSM: Entering Project Manager Node")
        await save_graph_state(ctx.state.session_id, "project_manager_node", ctx.state)
        return DraftNode()

@dataclass
class DraftNode(BaseNode[OrangeGraphState, OrangeDeps, str]):
    """
    Draft Node: Invokes the Orange agent to generate/update the response.
    """
    async def run(self, ctx: GraphRunContext[OrangeGraphState, OrangeDeps]) -> SelfReviewNode:
        print(f"[FSM] Entering Draft Node (attempt {ctx.state.loop_count + 1})...")
        from core.bridge import log_to_telemetry
        log_to_telemetry("EXEC", f"FSM: Entering Draft Node (attempt {ctx.state.loop_count + 1})")
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
            
        # Layered context walk-up scanning
        from core.profiles import buildSessionContext, buildIdentityContext
        from core.path_safety import VaultPathResolver
        
        note_title_match = re.search(r"Obsidian Note:\s*'(.*?)'", ctx.state.user_prompt)
        current_note_path = None
        vault_path = ctx.deps.obsidian_vault_path
        if note_title_match:
            note_title = note_title_match.group(1)
            try:
                current_note_path = str(
                    VaultPathResolver(vault_path).resolve_note(
                        note_title,
                        must_exist=True,
                        search_by_name=True,
                    )
                )
            except ValueError:
                current_note_path = None
                
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
        log_to_telemetry("EXEC", f"FSM: Running agent on model {current_model}")
        run_payload = [full_prompt] + ctx.state.attachments
        res = await agent.run(
            run_payload,
            model=current_model,
            deps=ctx.deps,
            instructions=sys_prompt,
            model_settings={"timeout": 120.0},
            metadata={
                "orange_profile": ctx.state.profile_name,
                "orange_tier": "heavy" if current_model == HEAVY_MODEL else "lite",
            },
        )
        
        response_text = getattr(res, 'data', getattr(res, 'output', str(res)))
        ctx.state.draft_response = response_text
        
        print("[FSM] Draft completed. Code blocks require an explicit Execute action in the UI.")
        log_to_telemetry("OK", "FSM: Draft completed without automatic code execution")
        return SelfReviewNode()

@dataclass
class SelfReviewNode(BaseNode[OrangeGraphState, OrangeDeps, str]):
    """
    Self-Review Node: Finalizes output and performs Git auto-backup.
    """
    async def run(self, ctx: GraphRunContext[OrangeGraphState, OrangeDeps]) -> End[str]:
        print("[FSM] Entering Self-Review Node. Finalizing response.")
        from core.bridge import log_to_telemetry
        log_to_telemetry("EXEC", "FSM: Entering Self-Review Node (Finalizing)")
        ctx.state.output_text = ctx.state.draft_response
        await save_graph_state(ctx.state.session_id, "self_review_node", ctx.state)
        
        # Trigger Git auto-backup only when explicitly enabled in runtime settings.
        from core.runtime_settings import runtime_flag
        if ctx.deps.obsidian_vault_path and runtime_flag("auto_backup_enabled", "OFF"):
            try:
                from core.git_backup import auto_backup_vault
                push_enabled = runtime_flag("auto_push_enabled", "OFF")
                print("[FSM] Triggering automatic Git backup.")
                log_to_telemetry("EXEC", "Git backup triggered")
                backup_res = await auto_backup_vault(ctx.deps.obsidian_vault_path, push=push_enabled)
                print(f"[FSM] Git backup status: {backup_res}")
                if isinstance(backup_res, dict):
                    successful_statuses = {
                        "success",
                        "success_local_only",
                        "no_changes",
                    }
                    backup_status = (
                        "OK"
                        if backup_res.get("status") in successful_statuses
                        else "FAIL"
                    )
                    backup_msg = backup_res.get("message", "done")
                else:
                    backup_res_str = str(backup_res)
                    backup_status = "OK" if "success" in backup_res_str.lower() or "ok" in backup_res_str.lower() else "FAIL"
                    backup_msg = backup_res_str
                from core import db
                db.add_audit_event("git_backup", backup_status.lower(), backup_msg)
                log_to_telemetry(backup_status, f"Git backup status: {backup_msg}")
            except Exception as e:
                print(
                    f"[FSM Warning] Failed to run Git backup: {type(e).__name__}"
                )
                log_to_telemetry(
                    "WARN",
                    f"Git backup failed: {type(e).__name__}",
                )
                
        return End(ctx.state.output_text)

# Build the graph
g = GraphBuilder(state_type=OrangeGraphState, deps_type=OrangeDeps, output_type=str)

@g.step
async def start_step(ctx: StepContext[OrangeGraphState, OrangeDeps, None]) -> ResearchNode:
    return ResearchNode()

g.add(
    g.node(ResearchNode),
    g.node(DeepResearchNode),
    g.node(ProjectManagerNode),
    g.node(DraftNode),
    g.node(SelfReviewNode),
    g.edge_from(g.start_node).to(start_step)
)

orange_fsm_graph = g.build()

# Backward compatibility aliases
research_node = ResearchNode
deep_research_node = DeepResearchNode
project_manager_node = ProjectManagerNode
draft_node = DraftNode
self_review_node = SelfReviewNode
