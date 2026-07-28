import asyncio
from typing import Optional
from core.dependencies import OrangeDeps
from core import db
from core import tools
from core.services.agent_runner import AgentRunner
from core.services.attachment_service import AttachmentService
from core.services.audio_service import AudioService
from core.services.chat_service import ChatService
from core.services.dashboard_service import DashboardService
from core.services.inbox_service import InboxService
from core.services.memory_service import MemoryService
from core.services.project_pages_service import ProjectPagesService
from core.services.settings_service import SettingsService
from core.services.vault_intelligence_service import VaultIntelligenceService
from core.services.weekly_review_service import WeeklyReviewService
from core.services.write_preview_service import WritePreviewService

import functools
import json
from concurrent.futures import TimeoutError as FutureTimeoutError
from core.path_safety import VaultNotConfiguredError
from core.service_result import normalize


def public_error_payload(exc: Exception, context: str, **extra) -> dict:
    explicit_code = getattr(exc, "error_code", "")
    error_code = explicit_code or (
        "NOT_CONFIGURED"
        if isinstance(exc, VaultNotConfiguredError)
        else "TIMEOUT"
        if isinstance(exc, TimeoutError)
        else "VALIDATION_ERROR"
        if isinstance(exc, (TypeError, ValueError))
        else "PROVIDER_ERROR"
    )
    return {
        "status": "error",
        "error_code": error_code,
        "message": f"{context}: {type(exc).__name__}",
        **extra,
    }

def settings_error_handler(func):
    """Декоратор для обработки ошибок методов настроек с возвратом JSON"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            res = func(*args, **kwargs)
            if isinstance(res, dict):
                return json.dumps(normalize(res), ensure_ascii=False)
            return json.dumps({"status": "success", "result": res})
        except Exception as e:
            return json.dumps(
                public_error_payload(e, "Settings operation failed"),
                ensure_ascii=False,
            )
    return wrapper

import datetime
import hashlib

active_bridge_instance = None

def log_to_telemetry(log_type: str, message: str):
    """
    Отправляет лог в боковую панель телеметрии в UI
    """
    global active_bridge_instance
    if active_bridge_instance and active_bridge_instance._window:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        js_code = (
            "if(typeof addTelemetryLog === 'function') "
            f"addTelemetryLog({json.dumps(timestamp)}, {json.dumps(str(log_type))}, {json.dumps(str(message))});"
        )
        try:
            active_bridge_instance._window.evaluate_js(js_code)
        except Exception:
            pass

class BridgeAPI:
    """Класс-мост, функции которого будут доступны внутри JavaScript окна программы"""
    def __init__(self, background_loop: asyncio.AbstractEventLoop, deps: OrangeDeps):
        global active_bridge_instance
        active_bridge_instance = self
        self._window = None
        self._background_loop = background_loop
        self._deps = deps
        self.current_chat_id = None
        self._override_future = None
        self._override_lock = None
        self._http_host = "127.0.0.1"
        self._http_port = getattr(deps.settings, "orange_port", 8080)

        vault_path = self._deps.obsidian_vault_path

        self._chat_service = ChatService()
        self._inbox_service = InboxService(vault_path)
        self._memory_service = MemoryService()
        self._dashboard_service = DashboardService(vault_path)
        self._vault_intelligence_service = VaultIntelligenceService(vault_path)
        self._project_pages_service = ProjectPagesService(vault_path)
        self._weekly_review_service = WeeklyReviewService(vault_path)
        self._write_preview_service = WritePreviewService(vault_path)
        self._attachment_service = AttachmentService(vault_path)
        self._audio_service = AudioService(deps)
        self._settings_service = SettingsService(deps, self._get_http_endpoint)
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

    async def shutdown(self):
        """Stops background service work before the application event loop exits."""
        await self._agent_runner.shutdown()

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
            return future.result(timeout=180)
        except FutureTimeoutError:
            future.cancel()
            return "[TIMEOUT] Chat export exceeded 180 seconds."
        except Exception as e:
            return f"[PROVIDER_ERROR] Export failed: {type(e).__name__}"

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

    def api_discard_staged_attachment(self, file_path: str) -> str:
        """Removes a staged attachment that the user discarded before sending."""
        return self._attachment_service.to_json(
            self._attachment_service.discard_staged_file(file_path)
        )

    # --- Аудио транскрибация ---

    def api_transcribe_audio(
        self,
        base64_audio: str,
        media_type: str = "audio/webm",
    ) -> str:
        """Синхронный вызов из JS для транскрибации голосовых директив"""
        future = asyncio.run_coroutine_threadsafe(
            self._async_transcribe_audio(base64_audio, media_type),
            self._background_loop
        )
        try:
            return future.result(timeout=120)
        except FutureTimeoutError:
            future.cancel()
            return "[TIMEOUT] Audio transcription exceeded 120 seconds."
        except Exception as e:
            print(f"[Bridge Error] Audio transcription failed: {type(e).__name__}")
            return f"[PROVIDER_ERROR] Audio transcription failed: {type(e).__name__}"

    async def _async_transcribe_audio(
        self,
        base64_audio: str,
        media_type: str = "audio/webm",
    ) -> str:
        return await self._audio_service.transcribe(base64_audio, media_type)

    # --- Основной процесс вызова агента ---

    def run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        """Синхронный вызов из JS, который перенаправляется в фоновый async цикл"""
        return self._agent_runner.run_agent_sync(profile_name, user_prompt, attachment_paths_json)

    def api_execute_python(self, code: str) -> str:
        """Runs the code shown in the UI only after the normal approval dialog."""
        future = asyncio.run_coroutine_threadsafe(
            tools.execute_python_restricted(str(code), self.request_execution_override),
            self._background_loop,
        )
        try:
            result = future.result(timeout=140)
            status = "applied" if result.startswith("=== EXECUTION RESULT") else "error"
            db.add_audit_event(
                "python_execution",
                status,
                f"Restricted Python execution ({len(str(code))} chars)",
                f"sha256={hashlib.sha256(str(code).encode('utf-8')).hexdigest()}",
            )
            return result
        except FutureTimeoutError:
            future.cancel()
            db.add_audit_event("python_execution", "error", "Python execution bridge timed out")
            return "[TIMEOUT] Python execution request timed out."
        except Exception as exc:
            db.add_audit_event("python_execution", "error", type(exc).__name__)
            return f"[PROVIDER_ERROR] Restricted executor failed: {type(exc).__name__}"

    async def _async_run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        return await self._agent_runner.run_agent(profile_name, user_prompt, attachment_paths_json)

    async def _async_run_http_query(
        self,
        profile_name: str,
        full_prompt: str,
        user_query: str,
    ) -> str:
        return await self._agent_runner.run_agent(
            profile_name,
            full_prompt,
            "[]",
            routing_prompt=user_query,
            rag_query=user_query,
            persist_chat=False,
        )
        
    async def _generate_chat_title(self, chat_id: str, first_user_msg: str, first_model_msg: str):
        """Light background request to generate chat title"""
        await self._agent_runner.generate_chat_title(chat_id, first_user_msg, first_model_msg)

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
            return json.dumps(
                normalize(self._settings_service.get_system_status()),
                ensure_ascii=False,
            )
        except Exception as e:
            print(f"[Bridge] api_get_system_status error: {type(e).__name__}")
            return json.dumps(
                public_error_payload(
                    e,
                    "System status failed",
                    obsidian_vault_path="—",
                    orange_port=self._http_port,
                    http_base_url=f"http://{self._http_host}:{self._http_port}",
                    mcp_status="OFFLINE",
                    watchdog_path="—",
                ),
                ensure_ascii=False,
            )

    def api_get_mcp_status(self) -> str:
        """Возвращает статусы: SQLite БД и MCP-сервер для MCP Dashboard"""
        return json.dumps(
            normalize(self._settings_service.get_mcp_status()),
            ensure_ascii=False,
        )

    def api_handle_override_response(self, approved: bool):
        """Вызывается из JS при клике на Permit/Deny в окне подтверждения команды"""
        if self._override_future and not self._override_future.done():
            self._background_loop.call_soon_threadsafe(self._override_future.set_result, approved)

    async def request_execution_override(self, command: str) -> bool:
        """
        Асинхронно запрашивает подтверждение выполнения команды у пользователя.
        Вызывает JS оверлей и ожидает решения.
        """
        if not self._window:
            print("[Bridge] Окно не инициализировано, автоотклонение команды.")
            db.add_audit_event("approval", "denied", "Window missing for execution approval")
            return False

        if self._override_lock is None:
            self._override_lock = asyncio.Lock()

        async with self._override_lock:
            self._override_future = self._background_loop.create_future()
            self._window.evaluate_js(f"showExecutionOverride({json.dumps(command)})")
            try:
                approved = await asyncio.wait_for(self._override_future, timeout=120)
                status = "approved" if approved else "denied"
                action_name = str(command).splitlines()[0][:120] or "unknown action"
                db.add_audit_event(
                    "approval",
                    status,
                    f"Approval response: {action_name}",
                    f"payload_chars={len(str(command))}",
                )
                return approved
            except asyncio.TimeoutError:
                db.add_audit_event("approval", "denied", "Approval request timed out")
                return False
            except Exception as e:
                print(f"[Bridge Error] Approval wait failed: {type(e).__name__}")
                db.add_audit_event("approval", "error", type(e).__name__)
                return False
            finally:
                self._override_future = None

    def trigger_panic(self, error_message: str):
        """Вызывает оверлей критической ошибки (системной паники) в JS"""
        if self._window:
            self._window.evaluate_js(f"triggerSystemPanic({json.dumps(error_message)})")

    # --- API для управления задачами через CLI ---

    def api_collect_tasks(self) -> str:
        """Сбор всех активных чекбоксов через CLI в JSON"""
        if not hasattr(self, "_daemon_manager") or not self._daemon_manager:
            return json.dumps({"error": "Daemon manager not initialized"})
            
        future = asyncio.run_coroutine_threadsafe(
            self._daemon_manager.collect_tasks(),
            self._background_loop
        )
        try:
            return json.dumps(future.result(timeout=30))
        except FutureTimeoutError:
            future.cancel()
            return json.dumps({
                "status": "error",
                "error_code": "TIMEOUT",
                "message": "Task collection timed out.",
            })
        except Exception as e:
            return json.dumps(public_error_payload(e, "Task collection failed"))

    def api_toggle_task(self, path: str, line: int) -> bool:
        """Изменение статуса задачи через CLI"""
        if not hasattr(self, "_daemon_manager") or not self._daemon_manager:
            return False
            
        future = asyncio.run_coroutine_threadsafe(
            self._daemon_manager.toggle_task(path, line),
            self._background_loop
        )
        try:
            return future.result(timeout=120)
        except FutureTimeoutError:
            future.cancel()
            return False
        except Exception:
            return False

    # --- API для сервисов (Vault Intelligence, Previews, Audit, Memory Editor) ---

    def api_get_memory_items(self, limit: int = 200) -> str:
        return self.api_list_memory_messages(limit)

    def api_update_memory_item(self, message_id: int, is_pinned: Optional[bool] = None, exclude_from_rag: Optional[bool] = None) -> str:
        return self.api_update_message_memory_flags(message_id, is_pinned, exclude_from_rag)

    def api_delete_memory_item(self, message_id: int) -> str:
        return self.api_delete_memory_message(message_id)

    def api_get_http_base_url(self) -> str:
        """Returns the actual HTTP endpoint bound by main.py."""
        return self._settings_service.get_http_base_url()

    def api_run_git_backup(self) -> str:
        """Runs a manual vault backup. Push only happens when auto_push_enabled is ON."""
        from core.git_backup import auto_backup_vault
        from core.runtime_settings import runtime_flag

        push_enabled = runtime_flag("auto_push_enabled", "OFF")
        future = asyncio.run_coroutine_threadsafe(
            auto_backup_vault(self._deps.obsidian_vault_path, push=push_enabled),
            self._background_loop
        )
        try:
            result = future.result(timeout=180)
            db.add_audit_event("git_backup", result.get("status", "unknown"), result.get("message", "Manual backup"))
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except FutureTimeoutError:
            future.cancel()
            db.add_audit_event("git_backup", "error", "Manual backup timed out")
            return json.dumps({
                "status": "error",
                "error_code": "TIMEOUT",
                "message": "Git backup timed out.",
            })
        except Exception as e:
            db.add_audit_event("git_backup", "error", type(e).__name__)
            return json.dumps(public_error_payload(e, "Git backup failed"))

    def api_list_memory_messages(self, limit: int = 200) -> str:
        return json.dumps(
            normalize(self._memory_service.list_items(limit)),
            ensure_ascii=False,
        )

    def api_update_message_memory_flags(self, message_id: int, is_pinned: Optional[bool] = None, exclude_from_rag: Optional[bool] = None) -> str:
        return json.dumps(
            normalize(self._memory_service.update_item(
                message_id,
                is_pinned,
                exclude_from_rag,
            )),
            ensure_ascii=False,
        )

    def api_delete_memory_message(self, message_id: int) -> str:
        return json.dumps(
            normalize(self._memory_service.delete_item(message_id)),
            ensure_ascii=False,
        )

    def propose_inbox_review(self, file_path: str):
        if not self._window:
            return
        try:
            proposal = self._inbox_service.build_proposal(file_path)
            db.add_audit_event(
                "smart_inbox",
                "proposed",
                f"Proposal for {proposal.get('relative_path', file_path)}",
                json.dumps({
                    "proposal_id": proposal.get("proposal_id", ""),
                    "relative_path": proposal.get("relative_path", ""),
                    "content_hash": proposal.get("content_hash", ""),
                    "category": proposal.get("category", ""),
                }),
            )
            self._window.evaluate_js(f"addSmartInboxProposal({json.dumps(proposal)})")
        except Exception as e:
            payload = public_error_payload(
                e,
                "Smart Inbox proposal failed",
                file_path=file_path,
                filename=file_path,
            )
            self._window.evaluate_js(f"addSmartInboxProposal({json.dumps(payload)})")

    def api_get_inbox_proposals(self) -> str:
        try:
            items = self._inbox_service.list_proposals()
            return json.dumps(
                normalize({"status": "success", "items": items}, data=items),
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                normalize(public_error_payload(e, "Inbox scan failed", items=[]), data=[]),
                ensure_ascii=False,
            )

    def api_apply_inbox_proposal(
        self,
        file_path: str,
        category: str = "",
        proposal_id: str = "",
    ) -> str:
        future = asyncio.run_coroutine_threadsafe(
            self._inbox_service.apply_proposal(file_path, category, proposal_id),
            self._background_loop,
        )
        try:
            result = future.result(timeout=30)
            audit_status = {
                "STALE_PREVIEW": "stale",
                "APPROVAL_DENIED": "rejected",
            }.get(result.get("error_code"), result.get("outcome", result.get("status", "unknown")))
            db.add_audit_event(
                "smart_inbox",
                audit_status,
                result.get("message", "Applied inbox proposal"),
                json.dumps({
                    "proposal_id": result.get("proposal_id", proposal_id),
                    "relative_path": result.get("relative_path", ""),
                    "content_hash": result.get("content_hash", ""),
                    "category": result.get("category", category),
                }),
            )
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except FutureTimeoutError:
            future.cancel()
            db.add_audit_event("smart_inbox", "error", "Inbox apply timed out")
            return json.dumps({
                "status": "error",
                "error_code": "TIMEOUT",
                "message": "Inbox apply timed out.",
            })
        except Exception as e:
            db.add_audit_event("smart_inbox", "error", type(e).__name__)
            return json.dumps(
                normalize(public_error_payload(e, "Inbox apply failed")),
                ensure_ascii=False,
            )

    def api_get_morning_dashboard(self) -> str:
        try:
            dashboard = self._dashboard_service.build_morning_dashboard()
            return json.dumps(
                normalize(
                    {"status": "success", "dashboard": dashboard},
                    data=dashboard,
                ),
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                normalize(public_error_payload(e, "Dashboard failed")),
                ensure_ascii=False,
            )

    def api_get_vault_time_machine(self, days: int = 90) -> str:
        try:
            result = self._vault_intelligence_service.build_time_machine(int(days))
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Time Machine failed"))

    def api_find_contradictions(self) -> str:
        try:
            result = self._vault_intelligence_service.find_contradictions()
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Contradiction scan failed", findings=[]))

    def api_run_agent_debate(self, topic: str = "") -> str:
        try:
            result = self._vault_intelligence_service.run_agent_debate(topic)
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Agent Debate failed"))

    def api_get_dormant_projects(self, stale_days: int = 30) -> str:
        try:
            result = self._vault_intelligence_service.find_dormant_projects(int(stale_days))
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Dormant project scan failed", items=[]))

    def api_get_operating_manual(self) -> str:
        try:
            result = self._vault_intelligence_service.build_operating_manual()
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Operating Manual failed"))

    def api_get_project_pages_preview(self) -> str:
        try:
            result = self._project_pages_service.preview_project_pages()
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Project Pages preview failed", plans=[]))

    def api_apply_project_pages(self, preview_id: str = "") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self._project_pages_service.apply_project_pages(preview_id),
            self._background_loop,
        )
        try:
            result = future.result(timeout=120)
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except FutureTimeoutError:
            future.cancel()
            return json.dumps({"status": "error", "error_code": "TIMEOUT", "message": "Project Pages apply timed out."})
        except Exception as e:
            db.add_audit_event("project_pages", "error", type(e).__name__)
            return json.dumps({"status": "error", "error_code": "VALIDATION_ERROR", "message": type(e).__name__})

    def api_reject_project_pages(self, preview_id: str = "") -> str:
        result = self._project_pages_service.reject_project_pages(preview_id)
        return json.dumps(normalize(result, data=result), ensure_ascii=False)

    def api_get_weekly_review_preview(self) -> str:
        try:
            result = self._weekly_review_service.preview_weekly_review()
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except Exception as e:
            return json.dumps(public_error_payload(e, "Weekly Review preview failed"))

    def api_apply_weekly_review(self, preview_id: str = "") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self._weekly_review_service.apply_weekly_review(preview_id),
            self._background_loop,
        )
        try:
            result = future.result(timeout=120)
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except FutureTimeoutError:
            future.cancel()
            return json.dumps({"status": "error", "error_code": "TIMEOUT", "message": "Weekly Review apply timed out."})
        except Exception as e:
            db.add_audit_event("weekly_review", "error", type(e).__name__)
            return json.dumps({"status": "error", "error_code": "VALIDATION_ERROR", "message": type(e).__name__})

    def api_reject_weekly_review(self, preview_id: str = "") -> str:
        result = self._weekly_review_service.reject_weekly_review(preview_id)
        return json.dumps(normalize(result, data=result), ensure_ascii=False)

    def api_get_audit_log(self, limit: int = 200) -> str:
        try:
            items = db.list_audit_events(max(1, min(int(limit), 500)))
            return json.dumps(
                normalize({"status": "success", "items": items}, data=items),
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(public_error_payload(e, "Audit log failed", items=[]))

    def api_get_write_preview(self, file_path: str, proposed_content: str) -> str:
        try:
            result = self._write_preview_service.build_preview(file_path, proposed_content)
            db.add_audit_event(
                "file_write",
                "proposed",
                f"Write preview for {result.get('relative_path', '')}",
                self._write_preview_service.audit_details(result.get("preview", {})),
            )
            return json.dumps(normalize(result), ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"Write preview failed: {type(e).__name__}",
            })

    def api_reject_write_preview(self, preview_id: str = "") -> str:
        result = self._write_preview_service.reject_preview(preview_id)
        if result.get("status") == "success":
            db.add_audit_event(
                "file_write",
                "rejected",
                result.get("message", "Write preview rejected"),
            )
        return json.dumps(normalize(result, data=result), ensure_ascii=False)

    def api_apply_write_preview(self, file_path: str, proposed_content: str, preview_id: str = "") -> str:
        future = asyncio.run_coroutine_threadsafe(
            self._apply_write_preview(file_path, proposed_content, preview_id),
            self._background_loop,
        )
        try:
            result = future.result(timeout=120)
            audit_status = {
                "APPROVAL_DENIED": "rejected",
                "STALE_PREVIEW": "stale",
            }.get(result.get("error_code"), result.get("status", "unknown"))
            db.add_audit_event(
                "file_write",
                audit_status,
                result.get("message", "Applied write preview"),
                json.dumps({"relative_path": result.get("relative_path", "")}),
            )
            return json.dumps(normalize(result, data=result), ensure_ascii=False)
        except FutureTimeoutError:
            future.cancel()
            return json.dumps({"status": "error", "error_code": "TIMEOUT", "message": "Write preview apply timed out."})
        except Exception as e:
            db.add_audit_event("file_write", "error", type(e).__name__)
            return json.dumps({"status": "error", "error_code": "VALIDATION_ERROR", "message": type(e).__name__})

    async def _apply_write_preview(self, file_path: str, proposed_content: str, preview_id: str = "") -> dict:
        plan = (
            self._write_preview_service.get_preview(preview_id)
            if preview_id
            else self._write_preview_service.get_latest_preview(file_path, proposed_content)
        )
        if plan is None:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Pending write preview is missing or expired. Build a new preview.",
            }
        elif plan["path"] != str(self._write_preview_service.resolve_vault_path(file_path)) or plan["new_content"] != proposed_content:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Preview content does not match the requested write.",
            }
        approved = await self.request_execution_override(
            f"DIFF_PREVIEW_REQUIRED\nWrite {plan['relative_path']}\n\n{plan['diff']}"
        )
        if not approved:
            plan["status"] = "rejected"
            return {
                "status": "error",
                "error_code": "APPROVAL_DENIED",
                "message": "Write was denied by the user.",
                "preview_id": plan["preview_id"],
                "relative_path": plan["relative_path"],
            }
        return await self._write_preview_service.apply_write(
            file_path,
            proposed_content,
            plan["preview_id"],
        )
