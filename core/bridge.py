import asyncio
import orange_core
from core.agent import agent
from core.profiles import PROFILES
from core.dependencies import OrangeDeps
from core import db
from core import tools

class BridgeAPI:
    """Класс-мост, функции которого будут доступны внутри JavaScript окна программы"""
    def __init__(self, background_loop: asyncio.AbstractEventLoop, deps: OrangeDeps):
        self._window = None
        self._background_loop = background_loop
        self._deps = deps
        self.current_chat_id = None

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
        
    def api_toggle_pin(self, chat_id: str) -> bool:
        """Закрепляет/открепляет чат"""
        return db.toggle_pin(chat_id)
        
    def api_export_chat(self) -> str:
        """Экспорт текущего чата в Obsidian"""
        if not self.current_chat_id:
            return "Ошибка: Нет активного чата для экспорта"
            
        future = asyncio.run_coroutine_threadsafe(
            tools.export_active_chat(self.current_chat_id, self._deps),
            self._background_loop
        )
        try:
            return future.result()
        except Exception as e:
            return f"Ошибка экспорта: {str(e)}"

    def api_upload_file(self) -> str:
        """
        Открывает нативное диалоговое окно выбора файла для импорта текстовых документов (.txt, .csv, .md)
        и инжектирует их содержимое в текущий чат как невидимый контекст.
        """
        import webview
        import os
        import json
        
        if not self._window:
            return json.dumps({"status": "error", "message": "Окно приложения не инициализировано"})
            
        if not self.current_chat_id:
            self.current_chat_id = db.create_chat("Новый диалог")
            
        try:
            file_types = ('Текстовые и PDF файлы (*.txt;*.csv;*.md;*.pdf)', 'Все файлы (*.*)')
            result = self._window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=file_types
            )
            
            if not result:
                return json.dumps({"status": "cancelled"})
                
            file_path = result[0]
            filename = os.path.basename(file_path)
            
            # Проверяем расширение
            _, ext = os.path.splitext(filename)
            if ext.lower() not in ['.txt', '.csv', '.md', '.pdf']:
                return json.dumps({"status": "error", "message": "Поддерживаются только форматы .txt, .csv, .md, .pdf"})
                
            # Читаем содержимое файла
            if ext.lower() == '.pdf':
                import pypdf
                print(f"[Bridge] Извлечение текста из PDF: {file_path}")
                reader = pypdf.PdfReader(file_path)
                pages_text = []
                for idx, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                content = "\n".join(pages_text)
            else:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
            # Инжектируем служебный контекст
            db.add_message(
                self.current_chat_id,
                "user",
                f"[Служебный системный контекст: Загружен документ '{filename}']\n{content}"
            )
            
            print(f"[Bridge] Файл {filename} успешно импортирован в чат {self.current_chat_id}")
            return json.dumps({"status": "success", "filename": filename})
            
        except Exception as e:
            print(f"[Bridge Error] Ошибка импорта файла: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    # --- Основной процесс вызова агента ---

    def run_agent(self, profile_name: str, user_prompt: str) -> str:
        """Синхронный вызов из JS, который перенаправляется в фоновый async цикл"""
        future = asyncio.run_coroutine_threadsafe(
            self._async_run_agent(profile_name, user_prompt), 
            self._background_loop
        )
        try:
            return future.result()
        except Exception as e:
            return f"Критическая ошибка ядра при обработке: {str(e)}"

    async def _async_run_agent(self, profile_name: str, user_prompt: str) -> str:
        from core.agent import LITE_MODEL, HEAVY_MODEL
        
        # Убеждаемся, что есть активный чат
        if not self.current_chat_id:
            self.current_chat_id = db.create_chat("Новый чат")
            
        # Запись сообщения пользователя
        db.add_message(self.current_chat_id, "user", user_prompt)
        
        # Получение истории
        history = db.get_chat_history(self.current_chat_id)
        
        # Формирование контекста из истории (кроме последнего сообщения, которое мы только что добавили)
        history_context = ""
        if len(history) > 1:
            context_lines = []
            for msg in history[:-1]:
                role_name = "ПОЛЬЗОВАТЕЛЬ" if msg['role'] == "user" else "AGENT"
                context_lines.append(f"{role_name}: {msg['content']}")
            history_context = "КОНТЕКСТ ПРОШЛОГО ОБЩЕНИЯ В ЭТОМ ЧАТЕ:\n" + "\n".join(context_lines) + "\n\n"
            
        final_prompt = history_context + f"НОВЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}"
        
        # Автоматическая классификация режима (Auto-Routing)
        if profile_name == "auto":
            print(f"[Auto-Router] Классификация запроса: '{user_prompt[:50]}...'")
            classification_prompt = (
                "Проанализируй запрос пользователя и классифицируй его в одну из трех категорий:\n"
                "1. 'coder' — если пользователь просит написать код, разработать программу, протестировать скрипт или выполнить вычисления.\n"
                "2. 'deep_research' — если пользователь просит найти что-то в интернете, провести исследование, OSINT, собрать свежие данные или проверить факты.\n"
                "3. 'base' — для обычного общения, ответов на общие вопросы, планирования или если запрос не относится к коду/поиску в сети.\n\n"
                f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}\n\n"
                "Верни ТОЛЬКО одно слово в нижнем регистре (без кавычек и точек): coder, deep_research или base."
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
                print(f"[Auto-Router] Запрос классифицирован как: {profile_name}")
            except Exception as e:
                print(f"[Auto-Router Error] Сбой классификации, использую base: {e}")
                profile_name = "base"

        sys_prompt = PROFILES.get(profile_name, PROFILES["base"])
        current_model = HEAVY_MODEL if profile_name in ["deep_research", "coder"] else LITE_MODEL
        agent.model = current_model
        
        # Запуск выполнения агента
        result = await agent.run(
            final_prompt,
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
        """Легкий фоновый запрос для генерации заголовка чата"""
        from core.agent import LITE_MODEL
        try:
            print(f"[BRIDGE DEBUG] Начинаю генерацию заголовка для чата {chat_id}...")
            prompt = f"Придумай очень короткий заголовок (2-4 слова) для чата, который начинается так:\nUser: {first_user_msg}\nAI: {first_model_msg}\nВерни ТОЛЬКО заголовок без кавычек."
            result = await agent.run(prompt, model=LITE_MODEL, deps=self._deps)
            title = getattr(result, 'data', getattr(result, 'output', str(result))).strip().strip('"\'')
            if title:
                # Ограничим длину на всякий случай
                if len(title) > 30:
                    title = title[:27] + "..."
                db.update_chat_title(chat_id, title)
                print(f"[BRIDGE DEBUG] Заголовок успешно обновлен: {title}")
                # Уведомим UI об обновлении списка чатов
                if self._window:
                    self._window.evaluate_js("if(typeof refreshChatList === 'function') refreshChatList();")
        except Exception as e:
            print(f"[BRIDGE ERROR] Ошибка генерации заголовка: {e}")

    def push_background_task(self, profile_name: str, file_path: str):
        """Запуск фонового анализа измененного файла"""
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
                f"Новые вводные в Inbox. Проанализируй этот текст и немедленно "
                f"распредели задачи по проектам, используя инструмент add_task. Текст:\n{text_snippet}\n"
                f"ВЫПОЛНЯЙ ВЫЗОВЫ add_task НЕМЕДЛЕННО В ФОНЕ. НЕ ПИШИ НИКАКОГО ТЕКСТА В ОТВЕТ."
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
                safe_text = response_text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
                self._window.evaluate_js(f"appendMessage('Orange [Background]', `Фоновый анализ завершен: {safe_text}`, 'sys')")
        except Exception as e:
            if self._window:
                safe_err = str(e).replace('\\', '\\\\').replace('`', '\\`')
                self._window.evaluate_js(f"appendMessage('Ошибка Фона', `Сбой фонового анализа: {safe_err}`, 'sys')")
