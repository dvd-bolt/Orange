from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import uuid
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Callable, Optional

from core import db
from core.agent import agent
from core.commands_handler import get_dynamic_instruction, parse_slash_command
from core.dependencies import OrangeDeps
from core.profiles import PROFILES


class AgentNotConfiguredError(RuntimeError):
    """Raised before a run when its selected provider has no credentials."""


class AgentRunner:
    """Runs the Orange agent while BridgeAPI stays a thin JS facade."""

    def __init__(
        self,
        background_loop: asyncio.AbstractEventLoop,
        deps: OrangeDeps,
        get_window: Callable[[], object],
        get_current_chat_id: Callable[[], Optional[str]],
        set_current_chat_id: Callable[[Optional[str]], None],
    ):
        self._background_loop = background_loop
        self._deps = deps
        self._get_window = get_window
        self._get_current_chat_id = get_current_chat_id
        self._set_current_chat_id = set_current_chat_id
        self._run_semaphore = asyncio.Semaphore(3)
        self._background_tasks = set()
        try:
            configured_timeout = int(
                os.environ.get("ORANGE_AGENT_TIMEOUT_SECONDS", "240")
            )
        except ValueError:
            configured_timeout = 240
        self._agent_timeout_seconds = max(30, min(configured_timeout, 300))

    def run_agent_sync(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self.run_agent(profile_name, user_prompt, attachment_paths_json),
            self._background_loop,
        )
        try:
            return future.result(timeout=300)
        except FutureTimeoutError:
            future.cancel()
            return "[TIMEOUT] ORANGE stopped the request because it exceeded the runtime limit."
        except ValueError as exc:
            return f"[VALIDATION_ERROR] {exc}"
        except AgentNotConfiguredError as exc:
            return f"[NOT_CONFIGURED] {exc}"
        except Exception as e:
            print(f"[AgentRunner Error] {type(e).__name__}")
            return f"[PROVIDER_ERROR] Agent request failed: {type(e).__name__}"

    async def run_agent(
        self,
        profile_name: str,
        user_prompt: str,
        attachment_paths_json: str = "[]",
        *,
        routing_prompt: Optional[str] = None,
        rag_query: Optional[str] = None,
        persist_chat: bool = True,
    ) -> str:
        try:
            await asyncio.wait_for(self._run_semaphore.acquire(), timeout=5.0)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Agent is busy; no execution slot became available.") from exc
        try:
            return await self._run_agent_locked(
                profile_name,
                user_prompt,
                attachment_paths_json,
                routing_prompt=routing_prompt,
                rag_query=rag_query,
                persist_chat=persist_chat,
            )
        finally:
            self._run_semaphore.release()

    async def _run_agent_locked(
        self,
        profile_name: str,
        user_prompt: str,
        attachment_paths_json: str = "[]",
        *,
        routing_prompt: Optional[str] = None,
        rag_query: Optional[str] = None,
        persist_chat: bool = True,
    ) -> str:
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("Agent prompt must be non-empty text.")
        if len(user_prompt.encode("utf-8")) > 100_000:
            raise ValueError("Agent prompt exceeds the 100 KB limit.")
        if len(str(attachment_paths_json).encode("utf-8")) > 100_000:
            raise ValueError("Attachment metadata exceeds the 100 KB limit.")
        allowed_profiles = {
            "auto",
            "base",
            "coder",
            "deep_research",
            "project_manager",
        }
        if profile_name not in allowed_profiles:
            raise ValueError(f"Unsupported agent profile: {profile_name}")

        original_user_prompt = user_prompt
        parsed_cmd = parse_slash_command(user_prompt)
        dynamic_instruction = None
        if parsed_cmd:
            cmd_name, cmd_text = parsed_cmd
            dynamic_instruction = get_dynamic_instruction(self._deps.obsidian_vault_path, cmd_name)
            if dynamic_instruction:
                user_prompt = cmd_text if cmd_text.strip() else f"Execute slash command: {cmd_name}"
                print(f"[AgentRunner] Loaded dynamic system prompt for command: /{cmd_name}")

        if profile_name == "auto" and not dynamic_instruction:
            profile_name = await self._classify_profile(routing_prompt or user_prompt)
        self._ensure_model_configured(profile_name, bool(dynamic_instruction))

        chat_id = self._get_current_chat_id() if persist_chat else None
        if not chat_id:
            chat_id = (
                db.create_chat("New chat")
                if persist_chat
                else f"http-{uuid.uuid4().hex}"
            )
            if persist_chat:
                self._set_current_chat_id(chat_id)

        if persist_chat:
            db.add_message(chat_id, "user", original_user_prompt)
            history = db.get_chat_history(chat_id)
        else:
            history = []
        history_context = await self._build_history_context(history)
        relevant_files_context = await self._build_rag_context(
            parsed_cmd,
            rag_query or user_prompt,
        )

        parts, staged_paths, attachment_warnings = self._load_attachments(
            attachment_paths_json
        )
        if attachment_warnings:
            relevant_files_context += (
                "ATTACHMENT VALIDATION WARNINGS:\n- "
                + "\n- ".join(attachment_warnings)
                + "\n\n"
            )

        from core.graph import OrangeGraphState, delete_graph_state, orange_fsm_graph

        state = OrangeGraphState(
            user_prompt=user_prompt,
            profile_name=profile_name,
            research_query=routing_prompt or user_prompt,
            dynamic_instruction=dynamic_instruction,
            chat_history_context=history_context,
            relevant_files_context=relevant_files_context,
            attachments=parts,
            session_id=chat_id,
        )
        try:
            run_res = await asyncio.wait_for(
                orange_fsm_graph.run(state=state, deps=self._deps),
                timeout=self._agent_timeout_seconds,
            )
            response_text = str(run_res)
            if persist_chat:
                db.add_message(chat_id, "model", response_text)
        finally:
            self._cleanup_runtime_attachments(staged_paths)
            if not persist_chat:
                await delete_graph_state(chat_id)

        api_key = self._deps.settings.gemini_api_key
        if persist_chat and api_key and (state.loop_count > 0 or len(history) > 4):
            try:
                from core.skills import crystallize_skill

                self._spawn_background_task(
                    crystallize_skill(chat_id, self._deps, api_key)
                )
            except Exception as e:
                print(f"[AgentRunner Skills Error] Skill crystallization skipped: {type(e).__name__}")

        if persist_chat and len(history) == 1:
            self._spawn_background_task(
                self.generate_chat_title(
                    chat_id,
                    original_user_prompt,
                    response_text,
                )
            )

        return response_text

    def _spawn_background_task(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)

        def finish(completed_task):
            self._background_tasks.discard(completed_task)
            if completed_task.cancelled():
                return
            try:
                completed_task.exception()
            except Exception:
                pass

        task.add_done_callback(finish)

    async def shutdown(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _build_history_context(self, history) -> str:
        if len(history) <= 1:
            return ""

        source_messages = [
            message
            for message in history[:-1]
            if not bool(message.get("exclude_from_rag"))
        ]
        indexed = list(enumerate(source_messages))
        pinned = [
            item for item in indexed if bool(item[1].get("is_pinned"))
        ]
        recent = [
            item for item in indexed if not bool(item[1].get("is_pinned"))
        ][-12:]
        selected_indexes = self._select_history_indexes(
            pinned,
            budget=8_000,
            per_message=2_000,
        )
        selected_indexes.update(
            self._select_history_indexes(
                recent,
                budget=10_000,
                per_message=1_500,
            )
        )
        if not selected_indexes:
            return ""

        lines = []
        for index, message in indexed:
            if index not in selected_indexes:
                continue
            role_name = "USER" if message.get("role") == "user" else "AGENT"
            pinned_marker = " [PINNED]" if bool(message.get("is_pinned")) else ""
            per_message = 2_000 if pinned_marker else 1_500
            content = str(message.get("content") or "")
            if len(content) > per_message:
                content = content[:per_message] + "\n...[message truncated]"
            lines.append(f"{role_name}{pinned_marker}: {content}")
        return "CONVERSATION CONTEXT (chronological):\n" + "\n".join(lines) + "\n\n"

    def _select_history_indexes(
        self,
        indexed_messages,
        *,
        budget: int,
        per_message: int,
    ):
        selected = set()
        used = 0
        for index, message in reversed(indexed_messages):
            role_name = "USER" if message.get("role") == "user" else "AGENT"
            content = str(message.get("content") or "")
            content_length = min(len(content), per_message) + (
                len("\n...[message truncated]")
                if len(content) > per_message
                else 0
            )
            estimated_length = len(role_name) + content_length + 12
            if used + estimated_length > budget:
                continue
            selected.add(index)
            used += estimated_length
        return selected

    async def _build_rag_context(self, parsed_cmd, user_prompt: str) -> str:
        if parsed_cmd:
            return ""
        try:
            from core.hybrid_search import hybrid_search

            relevant_files = await hybrid_search(
                user_prompt,
                self._deps.obsidian_vault_path,
                api_key=self._deps.settings.gemini_api_key,
                limit=3,
            )
        except Exception as e:
            print(f"[AgentRunner Indexer Error] Failed hybrid search: {type(e).__name__}")
            return ""

        context_chunks = []
        for filepath in relevant_files:
            filename = os.path.basename(filepath)
            try:
                from core.markdown_ops import read_note_cli

                file_content = await read_note_cli(filepath, vault_path=self._deps.obsidian_vault_path)
                if file_content.startswith(("[ERROR]", "Error reading note")):
                    print(f"[AgentRunner Indexer Warning] Skipping unreadable note: {filepath}")
                    continue
                context_chunks.append(
                    f"### Obsidian Note: {filename}\n"
                    f"Source path: {filepath}\n"
                    f"{file_content[:12000]}"
                )
                print(f"[AgentRunner] Injected relevant context from note: {filename}")
            except Exception as e:
                print(f"[AgentRunner Indexer Error] Could not read relevant file: {type(e).__name__}")

        if not context_chunks:
            return ""
        return "RELEVANT OBSIDIAN NOTES FROM YOUR VAULT:\n" + "\n\n".join(context_chunks) + "\n\n"

    async def _classify_profile(self, user_prompt: str) -> str:
        profile_name = self._classify_profile_locally(user_prompt)
        print(f"[Auto-Router] Local classification: {profile_name}")
        return profile_name

    def _ensure_model_configured(
        self,
        profile_name: str,
        has_dynamic_instruction: bool,
    ) -> None:
        from core.agent import HEAVY_MODEL, LITE_MODEL

        coder_models = os.environ.get("ORANGE_CODER_MODELS", "").strip()
        if (
            profile_name == "coder"
            and coder_models
            and os.environ.get("OPENROUTER_API_KEY")
        ):
            return

        selected_model = (
            HEAVY_MODEL
            if has_dynamic_instruction
            or profile_name in {"coder", "deep_research"}
            else LITE_MODEL
        )
        if selected_model.startswith(("google:", "google-gla:")):
            google_key = (
                self._deps.settings.gemini_api_key
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
            )
            if not google_key:
                raise AgentNotConfiguredError(
                    "GOOGLE_API_KEY is required for the selected model."
                )
        elif selected_model.startswith("openrouter:") and not os.environ.get(
            "OPENROUTER_API_KEY"
        ):
            raise AgentNotConfiguredError(
                "OPENROUTER_API_KEY is required for the selected model."
            )

    def _classify_profile_locally(self, user_prompt: str) -> str:
        return classify_profile_locally(user_prompt)

    def _load_attachments(self, attachment_paths_json: str):
        parse_warning = ""
        try:
            attachment_paths = json.loads(attachment_paths_json)
        except Exception:
            attachment_paths = []
            parse_warning = "Attachment metadata was not valid JSON."
        if not isinstance(attachment_paths, list):
            attachment_paths = []
            parse_warning = "Attachment metadata must be a list."

        from pydantic_ai.messages import BinaryContent

        parts = []
        cleanup_paths = []
        warnings = [parse_warning] if parse_warning else []
        total_bytes = 0
        allowed_extensions = {".txt", ".csv", ".md", ".pdf"}
        runtime_directory = (
            Path(__file__).resolve().parents[2]
            / ".orange_runtime"
            / "attachments"
        )
        if runtime_directory.parent.is_symlink() or runtime_directory.is_symlink():
            return [], [], ["Attachment runtime directory is not safe."]
        runtime_root = runtime_directory.resolve()
        for raw_path in attachment_paths[:10]:
            if not isinstance(raw_path, str):
                warnings.append("A non-string attachment path was ignored.")
                continue
            candidate = Path(raw_path).expanduser()
            if candidate.is_symlink():
                warnings.append("Attachment symlinks are not allowed.")
                continue
            try:
                resolved_path = candidate.resolve(strict=True)
                resolved_path.relative_to(runtime_root)
            except (OSError, ValueError):
                warnings.append("Attachment is outside the staged runtime directory.")
                continue
            path = str(resolved_path)
            cleanup_paths.append(path)
            extension = Path(path).suffix.lower()
            if extension not in allowed_extensions:
                warnings.append(f"Unsupported attachment type: {extension or '<none>'}.")
                continue
            if not os.path.isfile(path):
                warnings.append(f"Attachment was not found: {Path(path).name}.")
                continue
            try:
                file_size = os.path.getsize(path)
            except OSError:
                continue
            if file_size > 10 * 1024 * 1024:
                print("[AgentRunner Warning] Attachment exceeds 10 MB and was skipped.")
                warnings.append(f"Attachment exceeds 10 MB: {Path(path).name}.")
                continue
            if total_bytes + file_size > 25 * 1024 * 1024:
                warnings.append("Combined attachments exceed the 25 MB request limit.")
                continue
            mime_type, _ = mimetypes.guess_type(path)
            if not mime_type:
                ext = os.path.splitext(path)[1].lower()
                if ext == ".pdf":
                    mime_type = "application/pdf"
                elif ext in [".md", ".txt", ".csv"]:
                    mime_type = "text/plain"
                else:
                    mime_type = "application/octet-stream"
            try:
                with open(path, "rb") as file:
                    file_bytes = file.read()
                parts.append(BinaryContent(data=file_bytes, media_type=mime_type))
                total_bytes += len(file_bytes)
                print(f"[AgentRunner] Loaded staged attachment ({len(file_bytes)} bytes)")
            except Exception as e:
                print(f"[AgentRunner Error] Failed to read staged file: {type(e).__name__}")
                warnings.append(f"Attachment could not be read: {Path(path).name}.")
        if len(attachment_paths) > 10:
            warnings.append("Only the first 10 attachments were considered.")
        return parts, list(dict.fromkeys(cleanup_paths)), warnings

    def _cleanup_runtime_attachments(self, paths):
        runtime_directory = (
            Path(__file__).resolve().parents[2]
            / ".orange_runtime"
            / "attachments"
        )
        if runtime_directory.parent.is_symlink() or runtime_directory.is_symlink():
            return
        runtime_root = runtime_directory.resolve()
        for raw_path in paths:
            path = Path(raw_path).resolve(strict=False)
            try:
                path.relative_to(runtime_root)
            except ValueError:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                print(f"[AgentRunner Warning] Could not remove staged attachment: {type(exc).__name__}")

    async def generate_chat_title(self, chat_id: str, first_user_msg: str, first_model_msg: str):
        from core.agent import LITE_MODEL

        try:
            print(f"[AgentRunner] Starting title generation for chat {chat_id}...")
            prompt = (
                "Come up with a very short title (2-4 words) for the chat that starts like this:\n"
                f"User: {first_user_msg[:2000]}\n"
                f"AI: {first_model_msg[:4000]}\n"
                "Return ONLY the title without quotes."
            )
            result = await asyncio.wait_for(
                agent.run(
                    prompt,
                    model=LITE_MODEL,
                    deps=self._deps,
                    model_settings={"timeout": 30.0},
                ),
                timeout=35.0,
            )
            title = getattr(result, "data", getattr(result, "output", str(result))).strip().strip('"\'')
            if title:
                db.update_chat_title(chat_id, title[:30] if len(title) <= 30 else title[:27] + "...")
                window = self._get_window()
                if window:
                    window.evaluate_js("if(typeof refreshChatList === 'function') refreshChatList();")
        except Exception as e:
            print(f"[AgentRunner ERROR] Chat title generation failed: {type(e).__name__}")

def classify_profile_locally(user_prompt: str) -> str:
    lowered = str(user_prompt or "").lower()
    coder_markers = (
        "```", "python", "javascript", "typescript", "код", "скрипт",
        "функци", "ошибк", "traceback", "рефактор", "тест",
    )
    research_markers = (
        "найди в интернете", "поищи в интернете", "deep research",
        "osint", "свежие данные", "последние новости", "источники",
        "verify online", "search the web",
    )
    if any(marker in lowered for marker in research_markers):
        return "deep_research"
    if any(marker in lowered for marker in coder_markers):
        return "coder"
    return "base"
