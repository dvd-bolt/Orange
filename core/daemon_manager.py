import asyncio
import os
import datetime
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from core.runtime_settings import load_runtime_settings

class DaemonManager:
    def __init__(self, api):
        self.api = api
        self.api._daemon_manager = self
        self.running = False
        self.task = None
        self.loop = api._background_loop
        self.telegram_client = None
        self._stop_event = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.run_coroutine_threadsafe(self._run_loop(), self.loop)
        print("[DaemonManager] Фоновые демоны запущены.")

    def stop(self):
        self.running = False
        if self._stop_event is not None:
            self.loop.call_soon_threadsafe(self._stop_event.set)
        if self.task and not self.task.done():
            try:
                self.task.result(timeout=7)
            except FutureTimeoutError:
                self.task.cancel()
            except Exception:
                pass
        self.task = None
        print("[DaemonManager] Фоновые демоны остановлены.")

    async def _run_loop(self):
        print("[DaemonManager] Фоновый воркер запущен в цикле событий.")
        self._stop_event = asyncio.Event()
        try:
            while self.running:
                try:
                    data = load_runtime_settings()
                    daemon_enabled = data.get("telegram_daemon", "OFF") == "ON"

                    if daemon_enabled:
                        if not self.telegram_client:
                            await self._start_telegram_daemon()
                    elif self.telegram_client:
                        await self._stop_telegram_daemon()
                except Exception as e:
                    print(f"[DaemonManager Error] {type(e).__name__}")

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self.telegram_client:
                await self._stop_telegram_daemon()
            self._stop_event = None

    async def _start_telegram_daemon(self):
        print("[DaemonManager] Запуск Telegram-демона...")
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone = os.getenv("TELEGRAM_PHONE")
        session_path = Path(__file__).resolve().parents[1] / "config" / "orange_tg_session"
        session_exists = Path(f"{session_path}.session").exists()
        
        if not api_id or not api_hash or (not phone and not session_exists):
            print("[DaemonManager] Telegram не настроен: нужны API credentials и телефон либо существующая session.")
            self.telegram_client = "NOT_CONFIGURED"
            self._log_to_telemetry("WARN", "TELEGRAM_NOT_CONFIGURED")
            return

        from telethon import TelegramClient, events
        try:
            self.telegram_client = TelegramClient(str(session_path), int(api_id), api_hash)
            
            # Регистрируем обработчик событий
            @self.telegram_client.on(events.NewMessage)
            async def handler(event):
                await self._process_tg_message(event.sender_id, event.text)

            await self.telegram_client.start(phone=lambda: phone)
            print("[DaemonManager] Telegram-демон успешно подключен к API.")
            self._log_to_telemetry("CONN", "TG_CLIENT_CONNECTED: Listening for events...")
        except Exception as e:
            print(f"[DaemonManager Error] Ошибка запуска Telethon: {type(e).__name__}")
            self._log_to_telemetry("FAIL", f"TG_CONN_FAILED: {type(e).__name__}")
            self.telegram_client = None

    async def _stop_telegram_daemon(self):
        print("[DaemonManager] Остановка Telegram-демона...")
        if self.telegram_client == "NOT_CONFIGURED":
            self.telegram_client = None
            self._log_to_telemetry("OK", "TG_DAEMON_STOPPED")
        elif self.telegram_client:
            try:
                await self.telegram_client.disconnect()
            except Exception as e:
                print(f"[DaemonManager Error] {type(e).__name__}")
            self.telegram_client = None
            self._log_to_telemetry("OK", "TG_DAEMON_DISCONNECTED")

    async def _process_tg_message(self, sender_info, text: str):
        # Проверяем триггеры
        if not isinstance(text, str) or not text.strip():
            return
        triggers = ["orange", "todo", "task", "напомни"]
        text_lower = text.lower()
        if not any(trigger in text_lower for trigger in triggers):
            return

        print(f"[DaemonManager] Получен Telegram-триггер ({len(text)} символов).")
        self._log_to_telemetry("TG", f"MSG_RCVD: {len(text)} chars")
        
        try:
            vault_root = self.api._deps.obsidian_vault_path
            filename = f"TG_Task_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.md"
            relative_path = f"_Inbox/{filename}"
            
            note_content = (
                f"# Telegram Task: {text}\n\n"
                f"- [ ] Выполнить поручение из Telegram\n"
                f"- **Отправитель**: {sender_info}\n"
                f"- **Время поступления**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- **Текст сообщения**: {text}\n"
            )

            from core.services.write_preview_service import (
                WritePreviewService,
                confirm_and_apply_plan,
            )

            writer = WritePreviewService(vault_root)
            plan = writer.build_plan(relative_path, note_content, action="telegram_capture")
            approved = await confirm_and_apply_plan(
                self.api._deps,
                plan,
                "telegram",
                f"Capture Telegram task in {relative_path}",
            )
            if not approved:
                self._log_to_telemetry("WARN", "TG_CAPTURE_DENIED_BY_USER")
                return
            self._log_to_telemetry("OK", f"TASK_CREATED: {filename}")
            print(f"[DaemonManager] Создана заметка: {relative_path}")
        except Exception as e:
            print(f"[DaemonManager Error] Не удалось создать заметку: {type(e).__name__}")
            self._log_to_telemetry("FAIL", f"FILE_WRITE_ERR: {type(e).__name__}")

    def _log_to_telemetry(self, log_type, message):
        from core.bridge import log_to_telemetry
        log_to_telemetry(log_type, message)

    async def collect_tasks(self) -> list[dict]:
        """
        Собирает чекбоксы напрямую из vault, включая путь и номер строки.
        """
        import re
        from core.path_safety import VaultPathResolver

        try:
            resolver = VaultPathResolver(self.api._deps.obsidian_vault_path)
            tasks = []
            pattern = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$")
            for file_path in resolver.iter_notes(exclude_generated=True):
                try:
                    relative_path = resolver.relative(file_path)
                except ValueError:
                    continue
                content = await asyncio.to_thread(
                    resolver.read_note_text,
                    file_path,
                    max_chars=1_000_000,
                )
                for line_num, line in enumerate(content.splitlines(), start=1):
                    match = pattern.match(line)
                    if not match:
                        continue
                    status_char, task_text = match.groups()
                    tasks.append({
                        "path": relative_path,
                        "line": line_num,
                        "completed": status_char.lower() == 'x',
                        "text": task_text.strip()
                    })
            return tasks
        except Exception as e:
            print(f"[DaemonManager Error] Failed to collect tasks: {type(e).__name__}")
            return []

    async def toggle_task(self, path: str, line_num: int) -> bool:
        """
        Builds and applies the exact task-toggle diff after user approval.
        """
        import re
        from core.path_safety import VaultPathResolver
        from core.services.write_preview_service import (
            WritePreviewService,
            confirm_and_apply_plan,
        )

        try:
            resolver = VaultPathResolver(self.api._deps.obsidian_vault_path)
            note_path = resolver.resolve_note(path, must_exist=True)
            content = await asyncio.to_thread(
                resolver.read_note_text,
                note_path,
                max_chars=2 * 1024 * 1024,
            )
            lines = content.splitlines(keepends=True)
            line_num = int(line_num)
            if line_num < 1 or line_num > len(lines):
                return False
            task_pattern = re.compile(r"^(\s*[-*]\s*)\[([ xX])\](.*)$")
            original_line = lines[line_num - 1]
            line_body = original_line.rstrip("\r\n")
            line_ending = original_line[len(line_body):]
            match = task_pattern.match(line_body)
            if not match:
                return False
            replacement = " " if match.group(2).lower() == "x" else "x"
            lines[line_num - 1] = (
                f"{match.group(1)}[{replacement}]{match.group(3)}{line_ending}"
            )
            new_content = "".join(lines)
            writer = WritePreviewService(str(resolver.root))
            plan = writer.build_plan(note_path, new_content, action="toggle_task")
            return await confirm_and_apply_plan(
                self.api._deps,
                plan,
                "task_toggle",
                f"Toggle task at {plan['relative_path']}:{line_num}",
            )
        except Exception as e:
            print(f"[DaemonManager Error] Failed to toggle task: {type(e).__name__}")
            return False
