> **Дата обновления:** 2026-06-10  
> **Репозиторий:** [https://github.com/dvd-bolt/Orange](https://github.com/dvd-bolt/Orange)  
> **Рабочая директория:** `C:\orange\`

---

## 🧠 Что такое ORANGE?

**ORANGE** — локальная экосистема персонального ИИ-агента, работающая полностью на машине пользователя без облаков. Это не просто чат-бот — это автономная система с:

- **Долгосрочной памятью** (SQLite + семантический поиск через Gemini Embeddings)
- **Доступом к файловой системе** (чтение/запись в Obsidian Vault)
- **Исполнением кода** (Python sandbox с подтверждением пользователя)
- **Веб-исследованиями** (DuckDuckGo + Playwright + BeautifulSoup)
- **Интеграцией с Obsidian** (HTTP сервер + Watchdog + MCP клиент)
- **Фоновыми демонами** (Telegram мониторинг → автосоздание задач)

### Для чего используется:

- Личный AI-ассистент с памятью всех прошлых разговоров
- Автоматизация задач из Obsidian (парсинг заметок → задачи в проекты)
- OSINT и deep research по любым темам
- Локальное выполнение Python-кода с проверкой агентом
- Мониторинг Telegram-чатов с автосозданием задач в Obsidian

---

## ⚙️ Технический стек

|Слой|Технология|Назначение|
|---|---|---|
|**GUI**|`pywebview`|Нативное окно с Edge/WebKit движком|
|**Frontend**|HTML + Tailwind CSS + Vanilla JS|Интерфейс терминального стиля|
|**AI Framework**|`pydantic-ai` + Google Gemini API|Агент с инструментами|
|**LLM (lite)**|`gemini-3.1-flash-lite`|Классификация, заголовки чатов|
|**LLM (heavy)**|`gemini-3.5-flash`|Deep research, Coder, Export|
|**База данных**|SQLite (через `sqlite3`)|Чаты, сообщения, эмбеддинги|
|**Эмбеддинги**|Gemini Embedding API|Семантический поиск по памяти|
|**Файловый поиск**|`orange_core` (Rust/PyO3)|Быстрый скан vault, чтение файлов|
|**Obsidian интеграция**|HTTP сервер + `watchdog`|Прием запросов + слежение за Inbox|
|**MCP**|`mcp` Python SDK + TypeScript сервер|Инструменты для работы с vault|
|**Telegram**|`telethon`|Мониторинг сообщений (опционально)|
|**Web scraping**|`httpx` + `beautifulsoup4`|fetch_url инструмент|
|**Browser automation**|`playwright`|deep_analyze_website|
|**Web search**|`duckduckgo-search`|deep_research инструмент|
|**Markdown**|`mistletoe`|AST-парсинг для append_task|
|**PDF**|`pypdf`|Извлечение текста из PDF|
|**Async write**|`aiofiles` + `tenacity`|Атомарная запись в Obsidian|
|**Settings**|`pydantic-settings` + `.env`|Конфигурация|

---

## 📁 Структура проекта

C:\orange\

├── main.py                          # Точка входа: запуск pywebview + HTTP сервер + watchdog

├── requirements.txt                 # Все Python-зависимости

├── .env                             # API ключи (GOOGLE_API_KEY, OBSIDIAN_VAULT_PATH и др.)

├── .gitignore

│

├── config/

│   ├── settings.py                  # Pydantic-Settings модель конфигурации

│   └── settings.json                # Runtime-настройки (auth_token, telemetry, telegram_daemon)

│

├── core/

│   ├── agent.py                     # Инициализация pydantic-ai агента + регистрация инструментов

│   ├── bridge.py                    # BridgeAPI: Python-JS мост (все методы api_*)

│   ├── tools.py                     # Инструменты агента (scan_vault, rewrite_file, add_task, search_memory, execute_python и др.)

│   ├── db.py                        # SQLite CRUD: чаты, сообщения, эмбеддинги

│   ├── dependencies.py              # OrangeDeps (dataclass зависимостей для агента)

│   ├── profiles.py                  # Системные промпты для режимов: base, deep_research, coder, project_manager

│   ├── daemon_manager.py            # Фоновый демон Telegram (MOCK + реальный через telethon)

│   ├── watcher.py                   # Watchdog: слушатель изменений в Obsidian _Inbox

│   ├── mcp_client.py                # Асинхронный MCP клиент (SSE или stdio)

│   ├── file_ops.py                  # Атомарная запись файлов (iCloud-safe)

│   └── markdown_ops.py              # AST-парсинг markdown для append_task

│

├── ui/

│   ├── index.html                   # Вся HTML-разметка (1 страница + 6 модальных окон)

│   ├── main.js                      # Вся JS-логика (700+ строк)

│   └── style.css                    # Дополнительные CSS стили

│

├── integrations/

│   └── obsidian/

│       └── query_orange.py          # CLI-скрипт для вызова ORANGE из Obsidian (CustomJS/Templater)

│

├── mcp_servers/

│   ├── index.ts                     # MCP TypeScript сервер (STUB — не реализован)

│   ├── package.json

│   └── bun.lock

│

├── orange_core/                     # Rust-модуль (PyO3)

│   ├── src/                         # Исходники на Rust

│   ├── Cargo.toml

│   └── pyproject.toml

│

├── orange_memory.db                 # SQLite база данных (в .gitignore)

├── test_vault/                      # Тестовое Obsidian-хранилище

└── stitch_orange_terminal_interface/ # Архив дизайн-референсов (не runtime)

---

## 🏗️ Архитектура

┌─────────────────────────────────────────────────────────┐

│                    pywebview (Edge)                      │

│  ┌───────────────┐         ┌──────────────────────────┐  │

│  │  ui/index.html │◄──────►│      ui/main.js          │  │

│  │  (Tailwind UI) │        │   (700+ строк логики)    │  │

│  └───────┬────────┘        └──────────┬───────────────┘  │

│          │                            │ window.pywebview.api.*

└──────────┼────────────────────────────┼──────────────────┘

           │                            │

           ▼                            ▼

┌──────────────────────────────────────────────────────────┐

│                  core/bridge.py (BridgeAPI)               │

│   api_get_chats()  api_create_chat()  api_load_chat()    │

│   api_toggle_pin() api_stage_file()  api_export_chat()   │

│   api_get_settings() api_save_settings()                 │

│   api_handle_override_response()  trigger_panic()        │

│   run_agent()  push_background_task()                    │

└──────────┬───────────────────────────────────────────────┘

           │

    ┌──────┴──────┬──────────────┬─────────────┐

    ▼             ▼              ▼             ▼

┌────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────┐

│ core/  │  │ core/   │  │ core/    │  │ core/        │

│ db.py  │  │ agent.py│  │ tools.py │  │ daemon_mgr.py│

│(SQLite)│  │(pydantic│  │(14 tools)│  │(Telegram bg) │

└────────┘  │  -ai)   │  └──────────┘  └──────────────┘

            └────┬────┘

                 │ Google Gemini API

                 ▼

          ┌─────────────┐

          │ LLM (Gemini │

          │ Flash/Lite) │

          └─────────────┘

Параллельные сервисы:

┌──────────────────┐   ┌───────────────────┐

│ ThreadingHTTP    │   │ Watchdog Observer  │

│ Server (:8000)   │   │ (Obsidian _Inbox)  │

│ /query endpoint  │   │ → push_bg_task()  │

└──────────────────┘   └───────────────────┘

---

## ✅ Реализованные функции

### Чат и память

-  Создание нового чата
-  Загрузка и просмотр истории чата
-  Список всех чатов в сайдбаре
-  Закрепление/открепление чатов (📌)
-  Авто-генерация заголовка чата (через LLM)
-  Контекст истории в промпте (передаётся агенту)
-  Семантический поиск по памяти (через `search_memory` инструмент)
-  Экспорт чата в Obsidian (через `export_active_chat`)

### Агент и режимы

-  **AUTO** — автоматическая классификация запроса → coder/deep_research/base
-  **BASE** — обычный диалог + доступ к памяти
-  **DEEP RESEARCH** — DuckDuckGo + fetch_url + синтез отчёта
-  **CODER** — написание и локальное выполнение Python (sandbox)
-  **PROJECT MANAGER** — фоновый: парсинг inbox → add_task

### Инструменты агента (14 штук)

-  `scan_vault_fast` — рекурсивный поиск .md файлов (Rust)
-  `read_file_fast` — быстрое чтение файла (Rust)
-  `fetch_website_fast` — HTTP GET (Rust)
-  `deep_analyze_website` — Playwright + JS рендеринг
-  `rewrite_file` — атомарная перезапись заметки Obsidian
-  `add_task` — добавление задачи в .md файл (AST-парсинг)
-  `search_memory` — семантический поиск по диалогам (Gemini Embeddings)
-  `fetch_url` — HTTP + BeautifulSoup (чистый текст)
-  `deep_research` — DuckDuckGo + multi-page synthesis
-  `execute_python` — локальный Python sandbox (subprocess, таймаут 10с)
-  `list_existing_notes` — список всех заметок в vault
-  `call_obsidian_tool` — прокси к MCP серверу
-  Path traversal защита (`validate_path`)

### Безопасность

-  `request_execution_override` — пользователь подтверждает каждый запуск кода
-  Execution Override модал (PERMIT/DENY)
-  System Panic оверлей (критическая ошибка)
-  XSS-санитизация в evaluate_js вызовах

### Вложения

-  Загрузка файлов через нативный диалог (.txt, .md, .csv, .pdf)
-  Attachment Chips (визуальный превью + кнопка удаления)
-  Автодобавление содержимого файла в промпт

### UI

-  Терминальный дизайн (оранжевый / чёрный, JetBrains Mono)
-  Copy-кнопка в каждом блоке кода
-  Loader анимация при запросах
-  Telemetry Sidebar (системные логи)
-  Toast-уведомление при экспорте
-  Настройки (auth_token, telemetry ON/OFF, telegram ON/OFF)
-  Telegram Daemon toggle в настройках

### Интеграция с Obsidian

-  HTTP сервер (порт 8000+) с `/query` endpoint
-  `integrations/obsidian/query_orange.py` — CLI скрипт
-  Watchdog: слежение за `_Inbox/` папкой
-  Авто-анализ новых файлов в Inbox → add_task
-  MCP клиент (SSE и stdio режимы)

### Фоновые демоны

-  DaemonManager: запуск/остановка Telegram демона
-  MOCK-режим симуляции Telegram (без ключей)
-  Логирование в telemetry sidebar из Python

### Код и качество

-  Полный `requirements.txt` (14+ зависимостей)
-  `settings_error_handler` декоратор
-  Thread-safe SQLite через `threading.Lock`
-  Atomic file writes (fsync + rename)
-  Retry логика для файловых операций

---

## ❌ Нереализованные функции (очередь)

|#|Функция|Приоритет|Файлы|
|---|---|---|---|
|1|**Удаление чата**|🔴 Критический|db.py, bridge.py, main.js|
|2|**Переименование чата вручную**|🔴 Критический|bridge.py, main.js|
|3|**Вкладки настроек** (SYSTEM PATHS, DEMONS)|🟠 Высокий|index.html, main.js, bridge.py|
|4|**MCP Dashboard** — реальные статусы|🟠 Высокий|bridge.py, main.js|
|5|**PDF range config** (диапазон страниц)|🟡 Средний|bridge.py, main.js|
|6|**Inline Assets modal** — подключить Execute|🟡 Средний|main.js|
|7|**MCP Server** (mcp_servers/index.ts)|🔵 Низкий|index.ts|
|8|**telethon** в requirements.txt|🟠 Быстрый|requirements.txt|
|9|**Поиск по чатам**|🟠 Высокий|bridge.py, index.html, main.js|
|10|**orange_core BUILD инструкция**|🔵 Низкий|orange_core/BUILD.md|

Подробный план реализации каждой функции: **feature_implementation_plan.md**

---

## 🚀 Как запустить

### 1. Настройка окружения

bash

cd C:\orange

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

playwright install chromium  # для deep_analyze_website

### 2. Сборка Rust-модуля

bash

pip install maturin

cd orange_core

maturin develop --release

cd ..

### 3. Настройка `.env`

env

GOOGLE_API_KEY=ваш_ключ_gemini

OBSIDIAN_VAULT_PATH=C:\Users\вы\Documents\ObsidianVault

ORANGE_PORT=8000

# Опционально для Telegram:

TELEGRAM_API_ID=12345678

TELEGRAM_API_HASH=abc123...

TELEGRAM_PHONE=+79001234567

# Опционально для MCP:

MCP_SERVER_URL=mcp_servers/index.ts

### 4. Запуск

bash

python main.py

---

## 🔑 Переменные окружения

|Переменная|Обязательная|Описание|
|---|---|---|
|`GOOGLE_API_KEY`|✅ Да|API ключ Google Gemini|
|`OBSIDIAN_VAULT_PATH`|Рекомендуется|Путь к хранилищу Obsidian|
|`ORANGE_PORT`|Нет (default: 8000)|Порт HTTP сервера|
|`TELEGRAM_API_ID`|Нет|ID для Telegram API|
|`TELEGRAM_API_HASH`|Нет|Hash для Telegram API|
|`TELEGRAM_PHONE`|Нет|Телефон Telegram аккаунта|
|`MCP_SERVER_URL`|Нет|URL или путь к MCP серверу|

---

## 📡 API Bridge (Python → JS)

Все методы доступны через `window.pywebview.api.*`:

|Метод|Описание|Возвращает|
|---|---|---|
|`api_get_chats()`|Список всех чатов|`List[Dict]`|
|`api_create_chat(title)`|Создать чат|`str` (chat_id)|
|`api_load_chat(chat_id)`|Загрузить историю|`List[Dict]`|
|`api_toggle_pin(chat_id)`|Закрепить/открепить|`bool`|
|`api_export_chat()`|Экспорт в Obsidian|`str` (статус)|
|`api_stage_file()`|Нативный диалог файла|`JSON str`|
|`api_get_settings()`|Читать settings.json|`JSON str`|
|`api_save_settings(data)`|Сохранить настройки|`JSON str`|
|`api_handle_override_response(approved)`|Ответ на override|`None`|
|`run_agent(profile, prompt)`|Запустить агент|`str` (ответ)|

**JS → Python (evaluate_js из Python):**

|Функция в JS|Вызывается из|
|---|---|
|`appendMessage(sender, text, type)`|bridge.py, daemon_manager.py|
|`addTelemetryLog(time, type, msg)`|daemon_manager.py|
|`refreshChatList()`|bridge.py (после авто-заголовка)|
|`showExecutionOverride(command)`|bridge.py|
|`triggerSystemPanic(error)`|bridge.py|

---

## 🗄️ Схема базы данных

sql

-- Чаты

CREATE TABLE chats (

    id TEXT PRIMARY KEY,          -- UUID

    title TEXT,                   -- Заголовок (авто или ручной)

    is_pinned BOOLEAN DEFAULT 0,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

-- Сообщения

CREATE TABLE messages (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    chat_id TEXT,                 -- FK → chats.id

    role TEXT,                    -- 'user' | 'model'

    content TEXT,

    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE

);

-- Кэш эмбеддингов (для семантического поиска)

CREATE TABLE message_embeddings (

    message_id INTEGER PRIMARY KEY,

    embedding TEXT,               -- JSON-список float значений

    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE

);

---

## 🎨 UI Компоненты

### Модальные окна (6 штук)

|ID|Название|Статус|
|---|---|---|
|`settings-modal`|Глобальные настройки|✅ Работает|
|`mcp-dashboard-modal`|Статусы подключений|⚠️ Статичный|
|`execution-override-modal`|Подтверждение кода|✅ Работает|
|`system-panic-modal`|Критическая ошибка|✅ Работает|
|`attachment-config-modal`|Конфигурация PDF|❌ Не подключён|
|`inline-assets-modal`|Inline код/файлы|❌ Не подключён|

### Режимы агента (4 штуки)

|ID|Профиль|LLM|Описание|
|---|---|---|---|
|`auto`|auto-router|lite→heavy|Автоклассификация запроса|
|`base`|base|lite|Обычный диалог|
|`deep_research`|deep_research|heavy|OSINT исследование|
|`coder`|coder|heavy|Python sandbox|