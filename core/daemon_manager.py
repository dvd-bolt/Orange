import asyncio
import os
import json
import datetime
import threading
from config.settings import get_settings

class DaemonManager:
    def __init__(self, api):
        self.api = api
        self.running = False
        self.task = None
        self.loop = api._background_loop
        self.telegram_client = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.run_coroutine_threadsafe(self._run_loop(), self.loop)
        print("[DaemonManager] Фоновые демоны запущены.")

    def stop(self):
        self.running = False
        if self.telegram_client and self.telegram_client != "MOCK":
            asyncio.run_coroutine_threadsafe(self.telegram_client.disconnect(), self.loop)
        print("[DaemonManager] Фоновые демоны остановлены.")

    async def _run_loop(self):
        print("[DaemonManager] Фоновый воркер запущен в цикле событий.")
        while self.running:
            try:
                # Читаем settings.json динамически для проверки тумблера
                daemon_enabled = False
                settings_path = 'config/settings.json'
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        daemon_enabled = data.get("telegram_daemon", "OFF") == "ON"
                
                if daemon_enabled:
                    # Если включен и не запущен, инициализируем
                    if not self.telegram_client:
                        await self._start_telegram_daemon()
                else:
                    # Если выключен и запущен, останавливаем
                    if self.telegram_client:
                        await self._stop_telegram_daemon()
            except Exception as e:
                print(f"[DaemonManager Error] {e}")
                
            await asyncio.sleep(5)

    async def _start_telegram_daemon(self):
        print("[DaemonManager] Запуск Telegram-демона...")
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone = os.getenv("TELEGRAM_PHONE")
        
        # Если API ключи не настроены, запускаем Mock-режим
        if not api_id or not api_hash:
            print("[DaemonManager] API ключи Telegram не настроены. Запуск MOCK-режима...")
            self.telegram_client = "MOCK"
            # Запускаем фоновую задачу симуляции
            asyncio.create_task(self._run_mock_telegram())
            self._log_to_telemetry("CONN", "MOCK_TG_ACTIVE: Running simulation mode")
            return

        from telethon import TelegramClient, events
        try:
            self.telegram_client = TelegramClient('config/orange_tg_session', int(api_id), api_hash)
            
            # Регистрируем обработчик событий
            @self.telegram_client.on(events.NewMessage)
            async def handler(event):
                await self._process_tg_message(event.sender_id, event.text)

            await self.telegram_client.start(phone=lambda: phone)
            print("[DaemonManager] Telegram-демон успешно подключен к API.")
            self._log_to_telemetry("CONN", "TG_CLIENT_CONNECTED: Listening for events...")
        except Exception as e:
            print(f"[DaemonManager Error] Ошибка запуска Telethon: {e}")
            self._log_to_telemetry("FAIL", f"TG_CONN_FAILED: {str(e)}")
            # Откат в MOCK
            self.telegram_client = "MOCK"
            asyncio.create_task(self._run_mock_telegram())

    async def _stop_telegram_daemon(self):
        print("[DaemonManager] Остановка Telegram-демона...")
        if self.telegram_client == "MOCK":
            self.telegram_client = None
            self._log_to_telemetry("OK", "TG_DAEMON_STOPPED")
        elif self.telegram_client:
            try:
                await self.telegram_client.disconnect()
            except Exception as e:
                print(f"[DaemonManager Error] {e}")
            self.telegram_client = None
            self._log_to_telemetry("OK", "TG_DAEMON_DISCONNECTED")

    async def _run_mock_telegram(self):
        print("[DaemonManager] Фоновая симуляция Telegram запущена.")
        mock_messages = [
            ("user_manager", "Orange, напомни завтра проверить логины пользователей"),
            ("dev_lead", "todo: исправить уязвимость path traversal в коде"),
            ("client_bot", "orange task: сформировать еженедельный отчет по MCP"),
        ]
        import random
        idx = 0
        while self.running and self.telegram_client == "MOCK":
            await asyncio.sleep(40)  # интервал симуляции
            if self.telegram_client != "MOCK":
                break
            sender, text = mock_messages[idx % len(mock_messages)]
            idx += 1
            await self._process_tg_message(sender, text)

    async def _process_tg_message(self, sender_info, text: str):
        # Проверяем триггеры
        triggers = ["orange", "todo", "task", "напомни"]
        text_lower = text.lower()
        if not any(trigger in text_lower for trigger in triggers):
            return

        timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[DaemonManager] Получен триггер от {sender_info}: {text}")
        self._log_to_telemetry("TG", f"MSG_RCVD from {sender_info}: {text[:40]}...")
        
        # Создаем заметку в test_vault
        try:
            vault_root = self.api._deps.obsidian_vault_path
            inbox_dir = os.path.join(vault_root, "_Inbox")
            os.makedirs(inbox_dir, exist_ok=True)
            
            filename = f"TG_Task_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = os.path.join(inbox_dir, filename)
            
            note_content = (
                f"# Telegram Task: {text}\n\n"
                f"- [ ] Выполнить поручение из Telegram\n"
                f"- **Отправитель**: {sender_info}\n"
                f"- **Время поступления**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- **Текст сообщения**: {text}\n"
            )
            
            from core.file_lock import safe_write_lock
            with safe_write_lock(filepath):
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(note_content)
                
            self._log_to_telemetry("OK", f"TASK_CREATED: {filename}")
            print(f"[DaemonManager] Создана заметка: {filepath}")
        except Exception as e:
            print(f"[DaemonManager Error] Не удалось создать заметку: {e}")
            self._log_to_telemetry("FAIL", f"FILE_WRITE_ERR: {str(e)}")

    def _log_to_telemetry(self, log_type, message):
        if self.api._window:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            # Полная санитизация для JS-строки в одинарных кавычках
            safe_msg = (message
                .replace('\\', '\\\\')
                .replace("'", "\\'")
                .replace('"', '\\"')
                .replace('\n', '\\n')
                .replace('\r', '\\r')
                .replace('`', '\\`')
                .replace('$', '\\$'))
            safe_type = log_type.replace("'", "\\'")
            js_code = f"if(typeof addTelemetryLog === 'function') addTelemetryLog('{timestamp}', '{safe_type}', '{safe_msg}');"
            self.api._window.evaluate_js(js_code)
