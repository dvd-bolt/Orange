from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from typing import Callable, Optional

from core import db
from core.agent import agent
from core.commands_handler import get_dynamic_instruction, parse_slash_command
from core.dependencies import OrangeDeps
from core.profiles import PROFILES

try:
    import orange_core
except Exception:
    orange_core = None


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

    def run_agent_sync(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self.run_agent(profile_name, user_prompt, attachment_paths_json),
            self._background_loop,
        )
        try:
            return future.result()
        except Exception as e:
            return f"Critical kernel error during processing: {str(e)}"

    async def run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        from core.agent import HEAVY_MODEL, LITE_MODEL

        chat_id = self._get_current_chat_id()
        if not chat_id:
            chat_id = db.create_chat("New chat")
            self._set_current_chat_id(chat_id)

        original_user_prompt = user_prompt
        parsed_cmd = parse_slash_command(user_prompt)
        dynamic_instruction = None
        if parsed_cmd:
            cmd_name, cmd_text = parsed_cmd
            dynamic_instruction = get_dynamic_instruction(self._deps.obsidian_vault_path, cmd_name)
            if dynamic_instruction:
                user_prompt = cmd_text if cmd_text.strip() else f"Execute slash command: {cmd_name}"
                print(f"[AgentRunner] Loaded dynamic system prompt for command: /{cmd_name}")

        db.add_message(chat_id, "user", original_user_prompt)
        history = db.get_chat_history(chat_id)
        history_context = await self._build_history_context(history)
        relevant_files_context = await self._build_rag_context(parsed_cmd, user_prompt)

        if profile_name == "auto" and not dynamic_instruction:
            profile_name = await self._classify_profile(user_prompt)

        if dynamic_instruction:
            current_model = HEAVY_MODEL
        else:
            current_model = HEAVY_MODEL if profile_name in ["deep_research", "coder"] else LITE_MODEL

        agent.model = current_model
        parts = self._load_attachments(attachment_paths_json)

        from core.graph import OrangeGraphState, orange_fsm_graph

        state = OrangeGraphState(
            user_prompt=user_prompt,
            profile_name=profile_name,
            dynamic_instruction=dynamic_instruction,
            chat_history_context=history_context,
            relevant_files_context=relevant_files_context,
            attachments=parts,
        )

        run_res = await orange_fsm_graph.run(state=state, deps=self._deps)
        response_text = run_res.data if hasattr(run_res, "data") else str(run_res)
        db.add_message(chat_id, "model", response_text)

        if len(history) == 1:
            asyncio.create_task(self.generate_chat_title(chat_id, user_prompt, response_text))

        return response_text

    async def _build_history_context(self, history) -> str:
        if len(history) <= 1:
            return ""
        try:
            from core.folding import fold_history

            api_key = self._deps.settings.gemini_api_key
            messages = await fold_history(history[:-1], api_key) if api_key else history[:-1]
        except Exception as e:
            print(f"[AgentRunner Wiki-Fold Error] Fallback to raw formatting: {e}")
            messages = history[:-1]

        context_lines = []
        for msg in messages:
            role_name = "USER" if msg["role"] == "user" else "AGENT"
            context_lines.append(f"{role_name}: {msg['content']}")
        return "PAST CONVERSATION CONTEXT IN THIS CHAT:\n" + "\n".join(context_lines) + "\n\n"

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
            print(f"[AgentRunner Indexer Error] Failed hybrid search: {e}")
            return ""

        context_chunks = []
        for filepath in relevant_files:
            filename = os.path.basename(filepath)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
                    file_content = file.read()
                context_chunks.append(f"### Obsidian Note: {filename}\n{file_content}")
                print(f"[AgentRunner] Injected relevant context from note: {filename}")
            except Exception as e:
                print(f"[AgentRunner Indexer Error] Could not read relevant file '{filepath}': {e}")

        if not context_chunks:
            return ""
        return "RELEVANT OBSIDIAN NOTES FROM YOUR VAULT:\n" + "\n\n".join(context_chunks) + "\n\n"

    async def _classify_profile(self, user_prompt: str) -> str:
        from core.agent import LITE_MODEL

        print(f"[Auto-Router] Classifying request: '{user_prompt[:50]}...'")
        classification_prompt = (
            "Analyze the user's request and classify it into one of three categories:\n"
            "1. 'coder' - if the user is asking to write code, develop a program, test a script, or perform calculations.\n"
            "2. 'deep_research' - if the user is asking to search something on the internet, conduct research, OSINT, gather fresh data, or verify facts.\n"
            "3. 'base' - for casual conversation, general questions, planning, or if the request doesn't relate to code/web search.\n\n"
            f"USER REQUEST:\n{user_prompt}\n\n"
            "Return ONLY one word in lowercase (no quotes or periods): coder, deep_research, or base."
        )
        try:
            class_res = await agent.run(classification_prompt, model=LITE_MODEL, deps=self._deps)
            class_out = getattr(class_res, "data", getattr(class_res, "output", str(class_res))).strip().lower()
            if "coder" in class_out:
                profile_name = "coder"
            elif "deep_research" in class_out:
                profile_name = "deep_research"
            else:
                profile_name = "base"
            print(f"[Auto-Router] Request classified as: {profile_name}")
            return profile_name
        except Exception as e:
            print(f"[Auto-Router Error] Classification failed, using base: {e}")
            return "base"

    def _load_attachments(self, attachment_paths_json: str):
        try:
            attachment_paths = json.loads(attachment_paths_json)
        except Exception:
            attachment_paths = []

        from pydantic_ai.messages import BinaryContent

        parts = []
        for path in attachment_paths:
            if not os.path.exists(path):
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
                print(f"[AgentRunner] Loaded staged file '{path}' ({len(file_bytes)} bytes)")
            except Exception as e:
                print(f"[AgentRunner Error] Failed to read staged file '{path}': {e}")
        return parts

    async def generate_chat_title(self, chat_id: str, first_user_msg: str, first_model_msg: str):
        from core.agent import LITE_MODEL

        try:
            print(f"[AgentRunner] Starting title generation for chat {chat_id}...")
            prompt = (
                "Come up with a very short title (2-4 words) for the chat that starts like this:\n"
                f"User: {first_user_msg}\nAI: {first_model_msg}\nReturn ONLY the title without quotes."
            )
            result = await agent.run(prompt, model=LITE_MODEL, deps=self._deps)
            title = getattr(result, "data", getattr(result, "output", str(result))).strip().strip('"\'')
            if title:
                db.update_chat_title(chat_id, title[:30] if len(title) <= 30 else title[:27] + "...")
                window = self._get_window()
                if window:
                    window.evaluate_js("if(typeof refreshChatList === 'function') refreshChatList();")
        except Exception as e:
            print(f"[AgentRunner ERROR] Error generating title: {e}")

    def push_background_task(self, profile_name: str, file_path: str):
        asyncio.run_coroutine_threadsafe(
            self.background_agent_task(profile_name, file_path),
            self._background_loop,
        )

    async def background_agent_task(self, profile_name: str, file_path: str):
        from core.agent import LITE_MODEL

        try:
            content = self._read_file(file_path)
            prompt = (
                "New inputs in Inbox. Analyze this text and propose safe actions. "
                "Do not modify files unless the user confirms the proposal. Text:\n"
                f"{content[:10000]}"
            )
            sys_prompt = PROFILES.get(profile_name, PROFILES["project_manager"])
            agent.model = LITE_MODEL
            result = await agent.run(
                prompt,
                model=LITE_MODEL,
                deps=self._deps,
                model_settings={"system_prompt": sys_prompt},
            )
            self._append_system_message(
                "Orange [Background]",
                "Background analysis completed: "
                + getattr(result, "data", getattr(result, "output", str(result))),
            )
        except Exception as e:
            self._append_system_message("Background Error", f"Background analysis failed: {e}")

    def _read_file(self, file_path: str) -> str:
        if orange_core and hasattr(orange_core, "read_file_fast"):
            return orange_core.read_file_fast(file_path)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            return file.read()

    def _append_system_message(self, sender: str, text: str):
        window = self._get_window()
        if not window:
            return
        window.evaluate_js(f"appendMessage({json.dumps(sender)}, {json.dumps(text)}, 'sys')")
