import asyncio
from core.dependencies import OrangeDeps
from core import db
from core import tools
from core.services.agent_runner import AgentRunner
from core.services.attachment_service import AttachmentService
from core.services.chat_service import ChatService
from core.services.dashboard_service import DashboardService
from core.services.inbox_service import InboxService
from core.services.settings_service import SettingsService

import functools
import json

def settings_error_handler(func):
    """Декоратор для обработки ошибок методов настроек с возвратом JSON"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            res = func(*args, **kwargs)
            if isinstance(res, dict):
                return json.dumps(res)
            return json.dumps({"status": "success", "result": res})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
    return wrapper

class BridgeAPI:
    """Класс-мост, функции которого будут доступны внутри JavaScript окна программы"""
    def __init__(self, background_loop: asyncio.AbstractEventLoop, deps: OrangeDeps):
        self._window = None
        self._background_loop = background_loop
        self._deps = deps
        self.current_chat_id = None
        self._override_future = None
        self._http_host = "127.0.0.1"
        self._http_port = getattr(deps.settings, "orange_port", 8080)
        self._chat_service = ChatService()
        self._settings_service = SettingsService(deps, self._get_http_endpoint)
        self._attachment_service = AttachmentService()
        self._inbox_service = InboxService(deps.obsidian_vault_path)
        self._dashboard_service = DashboardService(deps.obsidian_vault_path)
        self._agent_runner = AgentRunner(
            background_loop,
            deps,
            lambda: self._window,
            lambda: self.current_chat_id,
            self._set_current_chat_id,
        )

    def set_http_endpoint(self, host: str, port: int):
        """Stores the actual bound local HTTP endpoint for UI integrations."""
        self._http_host = host
        self._http_port = port

    def _get_http_endpoint(self):
        return self._http_host, self._http_port

    def _set_current_chat_id(self, chat_id):
        self.current_chat_id = chat_id

    # --- API для работы с чатами из JS ---
    
    def api_get_chats(self):
        """Возвращает список всех чатов для сайдбара"""
        return self._chat_service.list_chats()
        
    def api_create_chat(self, title: str = "Новый чат") -> str:
        """Создает новый чат и делает его текущим"""
        chat_id = self._chat_service.create_chat(title)
        self.current_chat_id = chat_id
        return chat_id
        
    def api_load_chat(self, chat_id: str):
        """Загружает историю чата и устанавливает его как текущий"""
        self.current_chat_id = chat_id
        return self._chat_service.load_chat(chat_id)
        
    def api_get_current_chat_id(self) -> str:
        """Возвращает ID текущего активного чата"""
        return self.current_chat_id or ""
        
    def api_toggle_pin(self, chat_id: str) -> bool:
        """Закрепляет/открепляет чат"""
        return self._chat_service.toggle_pin(chat_id)

    def api_delete_chat(self, chat_id: str) -> bool:
        """Удаляет чат из БД. Если удаляем текущий — сбрасываем current_chat_id."""
        result = self._chat_service.delete_chat(chat_id)
        if self.current_chat_id == chat_id:
            self.current_chat_id = None
        return result

    def api_rename_chat(self, chat_id: str, new_title: str) -> bool:
        """Переименовывает чат (не более 50 символов)"""
        return self._chat_service.rename_chat(chat_id, new_title)

    def api_search_chats(self, query: str):
        """Полнотекстовый поиск по сообщениям всех чатов"""
        return self._chat_service.search_chats(query)

    def api_export_chat(self) -> str:
        """Export current chat to Obsidian"""
        if not self.current_chat_id:
            return "Error: No active chat to export"
            
        future = asyncio.run_coroutine_threadsafe(
            tools.export_active_chat(self.current_chat_id, self._deps),
            self._background_loop
        )
        try:
            return future.result()
        except Exception as e:
            return f"Export error: {str(e)}"

    def api_stage_file(self) -> str:
        """
        Opens native file dialog for txt, csv, md, pdf.
        Returns JSON with file path metadata.
        """
        return self._attachment_service.to_json(self._attachment_service.stage_file(self._window))

    def api_stage_pdf_with_range(self, file_path: str, start_page: int, end_page: int) -> str:
        """Extracts text from PDF page range, writes to a temp file, and returns file path metadata"""
        return self._attachment_service.to_json(
            self._attachment_service.stage_pdf_with_range(file_path, start_page, end_page)
        )

    # --- Аудио транскрибация ---

    def api_transcribe_audio(self, base64_audio: str) -> str:
        """Синхронный вызов из JS для транскрибации голосовых директив"""
        future = asyncio.run_coroutine_threadsafe(
            self._async_transcribe_audio(base64_audio),
            self._background_loop
        )
        try:
            return future.result()
        except Exception as e:
            print(f"[Bridge Error] Audio transcription failed: {e}")
            return f"[Error: {str(e)}]"

    async def _async_transcribe_audio(self, base64_audio: str) -> str:
        import base64
        from pydantic_ai import Agent
        from pydantic_ai.messages import BinaryContent
        from core.agent import LITE_MODEL
        
        try:
            audio_bytes = base64.b64decode(base64_audio)
            binary_part = BinaryContent(data=audio_bytes, media_type="audio/webm")
            
            # Use a clean agent for transcription to avoid polluting/triggering system prompts or tools
            transcriber = Agent(LITE_MODEL)
            res = await transcriber.run([
                "Пожалуйста, транскрибируй эту аудиозапись в текст. Твоя задача — вернуть ТОЛЬКО текст транскрипции на русском языке, без объяснений, комментариев и форматирования. Если в аудио тишина или нет речи, просто ничего не возвращай.",
                binary_part
            ])
            
            transcript = res.output.strip() if hasattr(res, 'output') else ""
            print(f"[Bridge] Audio transcription completed: '{transcript}'")
            return transcript
        except Exception as e:
            print(f"[Bridge Error] Transcription async failed: {e}")
            return f"[Error transcribing audio: {str(e)}]"

    # --- Основной процесс вызова агента ---

    def run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        """Синхронный вызов из JS, который перенаправляется в фоновый async цикл"""
        return self._agent_runner.run_agent_sync(profile_name, user_prompt, attachment_paths_json)

    async def _async_run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        return await self._agent_runner.run_agent(profile_name, user_prompt, attachment_paths_json)
        
    async def _generate_chat_title(self, chat_id: str, first_user_msg: str, first_model_msg: str):
        """Light background request to generate chat title"""
        await self._agent_runner.generate_chat_title(chat_id, first_user_msg, first_model_msg)

    def push_background_task(self, profile_name: str, file_path: str):
        """Run background analysis of modified file"""
        self._agent_runner.push_background_task(profile_name, file_path)
        
    async def _background_agent_task(self, profile_name: str, file_path: str):
        await self._agent_runner.background_agent_task(profile_name, file_path)

    # --- API для настроек и системных вызовов (Panic/Override) ---
    
    @settings_error_handler
    def api_get_settings(self) -> dict:
        """Считывает настройки из config/settings.json"""
        return self._settings_service.get_settings()

    @settings_error_handler
    def api_save_settings(self, data) -> bool:
        """Сохраняет настройки в config/settings.json с объединением с существующими"""
        return self._settings_service.save_settings(data)

    @settings_error_handler
    def set_language(self, lang: str) -> bool:
        """Сохраняет выбранный язык в config/settings.json"""
        return self._settings_service.set_language(lang)

    def api_get_i18n(self) -> str:
        """Возвращает содержимое config/i18n.json"""
        return self._settings_service.get_i18n_json()

    def api_get_system_status(self) -> str:
        """Возвращает статусы всех подсистем для вкладок SYSTEM PATHS и DEMONS"""
        try:
            return json.dumps(self._settings_service.get_system_status())
        except Exception as e:
            print(f"[Bridge] api_get_system_status error: {e}")
            return json.dumps({"obsidian_vault_path": "—", "orange_port": 8080, "http_base_url": "http://127.0.0.1:8080", "mcp_status": "OFFLINE", "watchdog_path": "—"})

    def api_get_http_base_url(self) -> str:
        """Returns the actual HTTP endpoint bound by main.py."""
        return self._settings_service.get_http_base_url()

    def api_run_git_backup(self) -> str:
        """Runs a manual local-only backup for the configured Obsidian vault."""
        from core.git_backup import auto_backup_vault
        future = asyncio.run_coroutine_threadsafe(
            auto_backup_vault(self._deps.obsidian_vault_path, push=False),
            self._background_loop
        )
        try:
            return json.dumps(future.result())
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def api_get_mcp_status(self) -> str:
        """Возвращает статусы: SQLite БД и MCP-сервер для MCP Dashboard"""
        return json.dumps(self._settings_service.get_mcp_status())

    def api_get_memory_items(self, limit: int = 200) -> str:
        """Returns recent messages/facts for Memory Editor."""
        try:
            return json.dumps({"status": "success", "items": db.list_memory_messages(int(limit))})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e), "items": []})

    def api_update_memory_item(self, message_id: int, is_pinned=None, exclude_from_rag=None) -> str:
        """Updates Memory Editor flags."""
        try:
            def coerce(value):
                if value is None:
                    return None
                if isinstance(value, str):
                    return value.lower() in {"1", "true", "yes", "on"}
                return bool(value)

            ok = db.update_message_memory_flags(
                int(message_id),
                is_pinned=coerce(is_pinned),
                exclude_from_rag=coerce(exclude_from_rag),
            )
            return json.dumps({"status": "success" if ok else "error", "message": "updated" if ok else "message not found"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def api_delete_memory_item(self, message_id: int) -> str:
        """Deletes a single message from memory."""
        try:
            ok = db.delete_message(int(message_id))
            return json.dumps({"status": "success" if ok else "error", "message": "deleted" if ok else "message not found"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def propose_inbox_review(self, file_path: str):
        """Pushes an inbox proposal to the UI without modifying vault files."""
        if not self._window:
            return
        try:
            proposal = self._inbox_service.build_proposal(file_path)
            self._window.evaluate_js(f"addSmartInboxProposal({json.dumps(proposal)})")
        except Exception as e:
            payload = {"status": "error", "file_path": file_path, "filename": file_path, "message": str(e)}
            self._window.evaluate_js(f"addSmartInboxProposal({json.dumps(payload)})")

    def api_get_inbox_proposals(self) -> str:
        try:
            return json.dumps({"status": "success", "items": self._inbox_service.list_proposals()})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e), "items": []})

    def api_apply_inbox_proposal(self, file_path: str, category: str = "") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self._inbox_service.apply_proposal(file_path, category),
            self._background_loop,
        )
        try:
            return json.dumps(future.result())
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def api_get_morning_dashboard(self) -> str:
        try:
            return json.dumps({"status": "success", "dashboard": self._dashboard_service.build_morning_dashboard()})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def api_handle_override_response(self, approved: bool):
        """Вызывается из JS при клике на Permit/Deny в окне подтверждения команды"""
        if self._override_future and not self._override_future.done():
            self._override_future.set_result(approved)

    async def request_execution_override(self, command: str) -> bool:
        """
        Асинхронно запрашивает подтверждение выполнения команды у пользователя.
        Вызывает JS оверлей и ожидает решения.
        """
        if not self._window:
            print("[Bridge] Окно не инициализировано, автоотклонение команды.")
            return False

        self._override_future = self._background_loop.create_future()
        safe_cmd = command.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
        
        # Показываем оверлей в JS
        self._window.evaluate_js(f"showExecutionOverride(`{safe_cmd}`)")
        
        try:
            approved = await self._override_future
            return approved
        except Exception as e:
            print(f"[Bridge Error] Ошибка ожидания подтверждения: {e}")
            return False

    def trigger_panic(self, error_message: str):
        """Вызывает оверлей критической ошибки (системной паники) в JS"""
        if self._window:
            safe_msg = error_message.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
            self._window.evaluate_js(f"triggerSystemPanic(`{safe_msg}`)")
