import asyncio
import orange_core
from core.agent import agent
from core.profiles import PROFILES
from core.dependencies import OrangeDeps
from core import db
from core import tools

import functools
import json
import mimetypes
from core.commands_handler import parse_slash_command, get_dynamic_instruction

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

    # --- API для работы с чатами из JS ---
    
    def api_get_chats(self):
        """Возвращает список всех чатов для сайдбара"""
        return db.get_all_chats()
        
    def api_create_chat(self, title: str = "Новый чат") -> str:
        """Создает новый чат и делает его текущим"""
        chat_id = db.create_chat(title)
        self.current_chat_id = chat_id
        return chat_id
        
    def api_load_chat(self, chat_id: str):
        """Загружает историю чата и устанавливает его как текущий"""
        self.current_chat_id = chat_id
        return db.get_chat_history(chat_id)
        
    def api_get_current_chat_id(self) -> str:
        """Возвращает ID текущего активного чата"""
        return self.current_chat_id or ""
        
    def api_toggle_pin(self, chat_id: str) -> bool:
        """Закрепляет/открепляет чат"""
        return db.toggle_pin(chat_id)

    def api_delete_chat(self, chat_id: str) -> bool:
        """Удаляет чат из БД. Если удаляем текущий — сбрасываем current_chat_id."""
        result = db.delete_chat(chat_id)
        if self.current_chat_id == chat_id:
            self.current_chat_id = None
        return result

    def api_rename_chat(self, chat_id: str, new_title: str) -> bool:
        """Переименовывает чат (не более 50 символов)"""
        if not new_title.strip():
            return False
        db.update_chat_title(chat_id, new_title.strip()[:50])
        return True

    def api_search_chats(self, query: str):
        """Полнотекстовый поиск по сообщениям всех чатов"""
        if not query.strip():
            return []
        return db.search_messages(query.strip())

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
        import webview
        import os
        import json
        
        if not self._window:
            return json.dumps({"status": "error", "message": "Application window is not initialized"})
            
        try:
            file_types = ('Text and PDF files (*.txt;*.csv;*.md;*.pdf)', 'All files (*.*)')
            result = self._window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=file_types
            )
            
            if not result:
                return json.dumps({"status": "cancelled"})
                
            file_path = result[0]
            filename = os.path.basename(file_path)
            
            # Check extension
            _, ext = os.path.splitext(filename)
            if ext.lower() not in ['.txt', '.csv', '.md', '.pdf']:
                return json.dumps({"status": "error", "message": "Only .txt, .csv, .md, and .pdf formats are supported"})
                
            # For PDF — request page range config
            if ext.lower() == '.pdf':
                import pypdf
                reader = pypdf.PdfReader(file_path)
                page_count = len(reader.pages)
                return json.dumps({
                    "status": "pdf_config_needed",
                    "file_path": file_path,
                    "filename": filename,
                    "page_count": page_count
                })

            print(f"[Bridge] File staged: {filename} -> {file_path}")
            return json.dumps({"status": "success", "filename": filename, "file_path": file_path})
            
        except Exception as e:
            print(f"[Bridge Error] Error staging file: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def api_stage_pdf_with_range(self, file_path: str, start_page: int, end_page: int) -> str:
        """Extracts text from PDF page range, writes to a temp file, and returns file path metadata"""
        import os
        import uuid
        import json
        try:
            import pypdf
            filename = os.path.basename(file_path)
            reader = pypdf.PdfReader(file_path)
            total = len(reader.pages)
            s = max(0, start_page - 1)
            e = min(total, end_page)
            pages_text = [reader.pages[i].extract_text() or '' for i in range(s, e)]
            content = "\n".join(pages_text)
            
            # Save to temporary scratch file
            scratch_dir = "scratch"
            os.makedirs(scratch_dir, exist_ok=True)
            temp_filename = f"pdf_extract_{uuid.uuid4().hex}.txt"
            temp_file_path = os.path.abspath(os.path.join(scratch_dir, temp_filename))
            with open(temp_file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            print(f"[Bridge] PDF {filename} pages {start_page}-{end_page} extracted to {temp_file_path}")
            return json.dumps({"status": "success", "filename": filename, "file_path": temp_file_path})
        except Exception as ex:
            return json.dumps({"status": "error", "message": str(ex)})

    # --- Основной процесс вызова агента ---

    def run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        """Синхронный вызов из JS, который перенаправляется в фоновый async цикл"""
        future = asyncio.run_coroutine_threadsafe(
            self._async_run_agent(profile_name, user_prompt, attachment_paths_json), 
            self._background_loop
        )
        try:
            return future.result()
        except Exception as e:
            return f"Critical kernel error during processing: {str(e)}"

    async def _async_run_agent(self, profile_name: str, user_prompt: str, attachment_paths_json: str = "[]") -> str:
        from core.agent import LITE_MODEL, HEAVY_MODEL
        import os
        import json
        
        # Ensure there is an active chat
        if not self.current_chat_id:
            self.current_chat_id = db.create_chat("New chat")
            
        original_user_prompt = user_prompt
        
        # Check for dynamic slash command instructions
        parsed_cmd = parse_slash_command(user_prompt)
        dynamic_instruction = None
        if parsed_cmd:
            cmd_name, cmd_text = parsed_cmd
            dynamic_instruction = get_dynamic_instruction(self._deps.obsidian_vault_path, cmd_name)
            if dynamic_instruction:
                # Override the prompt content to just the arguments text, or original prompt if empty
                user_prompt = cmd_text if cmd_text.strip() else f"Execute slash command: {cmd_name}"
                print(f"[Bridge] Loaded dynamic system prompt for command: /{cmd_name}")
            
        # Log user message
        db.add_message(self.current_chat_id, "user", original_user_prompt)
        
        # Load history
        history = db.get_chat_history(self.current_chat_id)
        
        # Format history context
        history_context = ""
        if len(history) > 1:
            context_lines = []
            for msg in history[:-1]:
                role_name = "USER" if msg['role'] == "user" else "AGENT"
                context_lines.append(f"{role_name}: {msg['content']}")
            history_context = "PAST CONVERSATION CONTEXT IN THIS CHAT:\n" + "\n".join(context_lines) + "\n\n"
            
        # Fast search index for relevant Markdown files in Vault
        relevant_files_context = ""
        if not parsed_cmd:
            try:
                from core.markdown_ops import search_relevant_files
                vault_path = self._deps.obsidian_vault_path
                relevant_files = search_relevant_files(vault_path, user_prompt, limit=3)
                if relevant_files:
                    context_chunks = []
                    for filepath in relevant_files:
                        filename = os.path.basename(filepath)
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                                file_content = f.read()
                            context_chunks.append(f"### Obsidian Note: {filename}\n{file_content}")
                            print(f"[Bridge] Injected relevant context from note: {filename}")
                        except Exception as e:
                            print(f"[Bridge Indexer Error] Could not read relevant file '{filepath}': {e}")
                    if context_chunks:
                        relevant_files_context = "RELEVANT OBSIDIAN NOTES FROM YOUR VAULT:\n" + "\n\n".join(context_chunks) + "\n\n"
            except Exception as e:
                print(f"[Bridge Indexer Error] Failed search: {e}")
            
        final_prompt = history_context + relevant_files_context + f"NEW USER REQUEST:\n{user_prompt}"
        
        # Auto-Routing classification
        if profile_name == "auto" and not dynamic_instruction:
            print(f"[Auto-Router] Classifying request: '{user_prompt[:50]}...'")
            classification_prompt = (
                "Analyze the user's request and classify it into one of three categories:\n"
                "1. 'coder' — if the user is asking to write code, develop a program, test a script, or perform calculations.\n"
                "2. 'deep_research' — if the user is asking to search something on the internet, conduct research, OSINT, gather fresh data, or verify facts.\n"
                "3. 'base' — for casual conversation, general questions, planning, or if the request doesn't relate to code/web search.\n\n"
                f"USER REQUEST:\n{user_prompt}\n\n"
                "Return ONLY one word in lowercase (no quotes or periods): coder, deep_research, or base."
            )
            try:
                class_res = await agent.run(classification_prompt, model=LITE_MODEL, deps=self._deps)
                class_out = getattr(class_res, 'data', getattr(class_res, 'output', str(class_res))).strip().lower()
                if "coder" in class_out:
                    profile_name = "coder"
                elif "deep_research" in class_out:
                    profile_name = "deep_research"
                else:
                    profile_name = "base"
                print(f"[Auto-Router] Request classified as: {profile_name}")
            except Exception as e:
                print(f"[Auto-Router Error] Classification failed, using base: {e}")
                profile_name = "base"

        # Apply system prompts
        if dynamic_instruction:
            sys_prompt = dynamic_instruction
            # Default to HEAVY_MODEL for specialized dynamic commands to ensure best output quality
            current_model = HEAVY_MODEL
        else:
            sys_prompt = PROFILES.get(profile_name, PROFILES["base"])
            current_model = HEAVY_MODEL if profile_name in ["deep_research", "coder"] else LITE_MODEL
            
        agent.model = current_model
        
        # Parse and load attachments natively
        parts = []
        try:
            attachment_paths = json.loads(attachment_paths_json)
        except Exception:
            attachment_paths = []
            
        from pydantic_ai.messages import BinaryContent
        for path in attachment_paths:
            if os.path.exists(path):
                # Guess mime type
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
                    with open(path, "rb") as f:
                        file_bytes = f.read()
                    parts.append(BinaryContent(data=file_bytes, media_type=mime_type))
                    print(f"[Bridge] Loaded staged file '{path}' ({len(file_bytes)} bytes) as native Gemini Part")
                except Exception as ex:
                    print(f"[Bridge Error] Failed to read staged file '{path}': {ex}")

        # Assemble prompt payload
        run_payload = [final_prompt]
        for part in parts:
            run_payload.append(part)

        # Run agent
        result = await agent.run(
            run_payload,
            model=current_model,
            deps=self._deps,
            model_settings={"system_prompt": sys_prompt}
        )
        
        response_text = getattr(result, 'data', getattr(result, 'output', str(result)))
        
        # Запись ответа агента
        db.add_message(self.current_chat_id, "model", response_text)
        
        # Генерация заголовка для нового чата
        if len(history) == 1:
            asyncio.create_task(self._generate_chat_title(self.current_chat_id, user_prompt, response_text))
            
        return response_text
        
    async def _generate_chat_title(self, chat_id: str, first_user_msg: str, first_model_msg: str):
        """Light background request to generate chat title"""
        from core.agent import LITE_MODEL
        try:
            print(f"[BRIDGE DEBUG] Starting title generation for chat {chat_id}...")
            prompt = f"Come up with a very short title (2-4 words) for the chat that starts like this:\nUser: {first_user_msg}\nAI: {first_model_msg}\nReturn ONLY the title without quotes."
            result = await agent.run(prompt, model=LITE_MODEL, deps=self._deps)
            title = getattr(result, 'data', getattr(result, 'output', str(result))).strip().strip('"\'')
            if title:
                # Limit title length
                if len(title) > 30:
                    title = title[:27] + "..."
                db.update_chat_title(chat_id, title)
                print(f"[BRIDGE DEBUG] Chat title successfully updated: {title}")
                # Refresh chat list in UI
                if self._window:
                    self._window.evaluate_js("if(typeof refreshChatList === 'function') refreshChatList();")
        except Exception as e:
            print(f"[BRIDGE ERROR] Error generating title: {e}")

    def push_background_task(self, profile_name: str, file_path: str):
        """Run background analysis of modified file"""
        asyncio.run_coroutine_threadsafe(
            self._background_agent_task(profile_name, file_path),
            self._background_loop
        )
        
    async def _background_agent_task(self, profile_name: str, file_path: str):
        from core.agent import LITE_MODEL
        try:
            content = orange_core.read_file_fast(file_path)
            text_snippet = content[:10000]
            
            prompt = (
                f"New inputs in Inbox. Analyze this text and immediately "
                f"distribute tasks across projects using the add_task tool. Text:\n{text_snippet}\n"
                f"EXECUTE add_task CALLS IMMEDIATELY IN THE BACKGROUND. DO NOT WRITE ANY TEXT IN RESPONSE."
            )
            
            sys_prompt = PROFILES.get(profile_name, PROFILES["project_manager"])
            agent.model = LITE_MODEL
            
            result = await agent.run(
                prompt,
                model=LITE_MODEL,
                deps=self._deps,
                model_settings={"system_prompt": sys_prompt}
            )
            
            if self._window:
                response_text = getattr(result, 'data', getattr(result, 'output', str(result)))
                safe_text = (response_text
                    .replace('\\', '\\\\')
                    .replace("'", "\\'")
                    .replace('\n', '\\n')
                    .replace('\r', '\\r'))
                self._window.evaluate_js(f"appendMessage('Orange [Background]', 'Background analysis completed: {safe_text}', 'sys')")
        except Exception as e:
            if self._window:
                safe_err = (str(e)
                    .replace('\\', '\\\\')
                    .replace("'", "\\'")
                    .replace('\n', '\\n')
                    .replace('\r', '\\r'))
                self._window.evaluate_js(f"appendMessage('Background Error', 'Background analysis failed: {safe_err}', 'sys')")

    # --- API для настроек и системных вызовов (Panic/Override) ---
    
    @settings_error_handler
    def api_get_settings(self) -> dict:
        """Считывает настройки из config/settings.json"""
        import os
        path = 'config/settings.json'
        default_config = {"auth_token": "************************", "telemetry_stream": "ON", "language": "ru"}
        if not os.path.exists(path):
            os.makedirs('config', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            return default_config
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "language" not in data:
                    data["language"] = "ru"
                return data
        except Exception:
            return default_config

    @settings_error_handler
    def api_save_settings(self, data) -> bool:
        """Сохраняет настройки в config/settings.json с объединением с существующими"""
        import os
        path = 'config/settings.json'
        if isinstance(data, str):
            data = json.loads(data)
        
        existing = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
                
        existing.update(data)
        
        os.makedirs('config', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=4)
        print("[Bridge] Настройки сохранены в config/settings.json")
        return True

    @settings_error_handler
    def set_language(self, lang: str) -> bool:
        """Сохраняет выбранный язык в config/settings.json"""
        import os
        path = 'config/settings.json'
        config = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except Exception:
                config = {}
        config["language"] = lang
        os.makedirs('config', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        print(f"[Bridge] Язык сохранен: {lang}")
        return True

    def api_get_i18n(self) -> str:
        """Возвращает содержимое config/i18n.json"""
        import os
        path = 'config/i18n.json'
        if not os.path.exists(path):
            return "{}"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return "{}"

    def api_get_system_status(self) -> str:
        """Возвращает статусы всех подсистем для вкладок SYSTEM PATHS и DEMONS"""
        import os
        from config.settings import get_settings
        try:
            settings = get_settings()
            mcp_connected = (
                self._deps.mcp_client is not None
                and hasattr(self._deps.mcp_client, '_session')
                and self._deps.mcp_client._session is not None
            )
            vault_path = str(getattr(settings, 'obsidian_vault_path', '') or '—')
            orange_port = getattr(settings, 'orange_port', 8000)
            return json.dumps({
                "obsidian_vault_path": vault_path,
                "orange_port": orange_port,
                "mcp_status": "CONNECTED" if mcp_connected else "OFFLINE",
                "watchdog_path": os.path.join(vault_path, "_Inbox"),
            })
        except Exception as e:
            print(f"[Bridge] api_get_system_status error: {e}")
            return json.dumps({"obsidian_vault_path": "—", "orange_port": 8000, "mcp_status": "OFFLINE", "watchdog_path": "—"})

    def api_get_mcp_status(self) -> str:
        """Возвращает статусы: SQLite БД и MCP-сервер для MCP Dashboard"""
        import os
        mcp_connected = (
            self._deps.mcp_client is not None
            and hasattr(self._deps.mcp_client, '_session')
            and self._deps.mcp_client._session is not None
        )
        db_path = "orange_memory.db"
        db_exists = os.path.exists(db_path)
        db_size_mb = round(os.path.getsize(db_path) / 1024 / 1024, 2) if db_exists else 0
        return json.dumps({
            "sqlite": {"status": "ONLINE" if db_exists else "ERROR", "size_mb": db_size_mb},
            "mcp": {"status": "CONNECTED" if mcp_connected else "OFFLINE"},
        })

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
