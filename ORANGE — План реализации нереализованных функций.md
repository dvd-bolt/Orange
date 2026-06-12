> Файлы проекта: `C:\orange\`  
> Стек: Python 3.11 + pywebview + pydantic-ai + SQLite | HTML/JS/Tailwind

---

## 🔴 ПРИОРИТЕТ 1 — Критические (запускать первыми)

---

### 1. Удаление чата

**Затрагиваемые файлы:**

- `core/db.py` — новая функция
- `core/bridge.py` — новый API-метод
- `ui/main.js` — кнопка + логика
- `ui/index.html` — (кнопка уже в chat-list, вставляется динамически)

#### `core/db.py` — добавить после `update_chat_title()`:

python

def delete_chat(chat_id: str) -> bool:

    """Удаляет чат и все его сообщения (CASCADE)"""

    with _lock:

        with get_connection() as conn:

            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

            conn.commit()

    return True

#### `core/bridge.py` — добавить новый метод:

python

def api_delete_chat(self, chat_id: str) -> bool:

    """Удаляет чат из БД. Если удаляем текущий — сбрасываем current_chat_id."""

    result = db.delete_chat(chat_id)

    if self.current_chat_id == chat_id:

        self.current_chat_id = None

    return result

#### `ui/main.js` — в функции `refreshChatList()`, в блоке создания кнопки чата, добавить кнопку удаления рядом с кнопкой pin:

javascript

const deleteBtn = document.createElement('span');

deleteBtn.className = "opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-error ml-1";

deleteBtn.innerText = "✕";

deleteBtn.title = "Удалить чат";

deleteBtn.onclick = async (e) => {

    e.stopPropagation();

    if (!confirm(`Удалить чат "${chat.title || 'Новый диалог'}"?`)) return;

    await window.pywebview.api.api_delete_chat(chat.id);

    // Если удалили активный — очищаем canvas

    if (chat.id === currentChatId) {

        currentChatId = null;

        if (container) container.innerHTML = '';

        appendMessage('Система', 'Чат удалён. Создайте новый сеанс.', 'sys');

    }

    refreshChatList();

};

item.appendChild(deleteBtn);

---

### 2. Переименование чата вручную

**Затрагиваемые файлы:**

- `core/bridge.py` — новый метод
- `ui/main.js` — inline-редактирование по двойному клику на заголовок

#### `core/bridge.py`:

python

def api_rename_chat(self, chat_id: str, new_title: str) -> bool:

    """Переименовывает чат"""

    if not new_title.strip():

        return False

    db.update_chat_title(chat_id, new_title.strip()[:50])

    return True

#### `ui/main.js` — в `refreshChatList()`, у элемента `title`:

javascript

// Заменить: title.innerText = ...

title.innerText = (isPinned ? '📌 ' : '') + (chat.title || 'Новый диалог');

title.title = "Двойной клик — переименовать";

title.ondblclick = async (e) => {

    e.stopPropagation();

    const newName = prompt("Новое название чата:", chat.title || '');

    if (newName && newName.trim()) {

        await window.pywebview.api.api_rename_chat(chat.id, newName.trim());

        refreshChatList();

    }

};

---

### 9. Поиск по чатам

**Затрагиваемые файлы:**

- `core/bridge.py` — новый метод
- `ui/index.html` — строка поиска в сайдбаре
- `ui/main.js` — логика поиска + отображение

#### `core/bridge.py`:

python

def api_search_chats(self, query: str):

    """Полнотекстовый поиск по сообщениям всех чатов"""

    if not query.strip():

        return []

    return db.search_messages(query.strip())

#### `ui/index.html` — добавить сразу после `<!-- Dynamic Chats List Container -->`:

html

<!-- Search Input -->

<div class="px-2 pb-2">

    <input 

        id="chat-search" 

        oninput="searchChats(this.value)"

        placeholder="> SEARCH..."

        class="w-full bg-transparent border border-outline text-on-surface font-label-mono text-[11px] px-3 py-2 focus:border-primary focus:ring-0 outline-none placeholder-on-surface placeholder-opacity-30"

    />

</div>

#### `ui/main.js`:

javascript

async function searchChats(query) {

    if (!query.trim()) {

        refreshChatList(); // сброс — показать все

        return;

    }

    if (!window.pywebview) return;

    try {

        const results = await window.pywebview.api.api_search_chats(query);

        const listEl = document.getElementById('chat-list');

        if (!listEl) return;

        listEl.innerHTML = '';

        if (!results.length) {

            listEl.innerHTML = '<div class="px-4 py-3 font-label-mono text-[11px] text-on-surface opacity-40">Ничего не найдено</div>';

            return;

        }

        results.forEach(msg => {

            const item = document.createElement('button');

            item.className = "w-full text-left font-label-mono text-label-mono text-on-surface hover:text-primary px-4 py-3 hover:bg-surface-variant flex flex-col gap-1 transition-colors";

            item.onclick = () => loadChat(msg.chat_id);

            item.innerHTML = `

                <span class="text-primary text-[10px] truncate">${escapeHTML(msg.title || 'Без названия')}</span>

                <span class="text-[10px] opacity-60 truncate">${escapeHTML(msg.content.substring(0, 60))}...</span>

            `;

            listEl.appendChild(item);

        });

    } catch(e) {

        console.error("Search error:", e);

    }

}

window.searchChats = searchChats;

---

## 🟠 ПРИОРИТЕТ 2 — Важные UX-улучшения

---

### 3. Вкладки настроек: SYSTEM PATHS и DEMONS

**Затрагиваемые файлы:**

- `ui/index.html` — добавить содержимое вкладок + tab-switching логику
- `ui/main.js` — функция `switchSettingsTab(tabName)`
- `core/bridge.py` — новый метод `api_get_system_status()`

#### Концепция:

Вкладка **SYSTEM PATHS** показывает:

- `OBSIDIAN_VAULT_PATH` — путь к Obsidian хранилищу
- `ORANGE_PORT` — порт HTTP сервера

Вкладка **DEMONS** показывает:

- **Watchdog** — статус (ON/OFF) + путь наблюдения
- **Telegram Daemon** — статус (MOCK/CONNECTED/OFF)
- **MCP Client** — статус (CONNECTED/DISCONNECTED)

#### `core/bridge.py` — новый метод:

python

def api_get_system_status(self) -> str:

    """Возвращает статусы всех подсистем"""

    import json, os

    from config.settings import get_settings

    settings = get_settings()

    # MCP статус

    mcp_connected = (

        self._deps.mcp_client is not None and 

        self._deps.mcp_client._session is not None

    )

    return json.dumps({

        "obsidian_vault_path": settings.obsidian_vault_path,

        "orange_port": settings.orange_port,

        "mcp_status": "CONNECTED" if mcp_connected else "OFFLINE",

        "watchdog_path": os.path.join(settings.obsidian_vault_path, "_Inbox"),

    })

#### `ui/index.html` — изменить вкладки настроек (превратить `<span>` в кликабельные кнопки):

html

<div class="flex gap-4 border-b border-outline-variant pb-2">

    <button onclick="switchSettingsTab('api')" id="tab-api"

        class="text-primary font-label-mono text-label-mono border-b border-primary pb-0.5">API & AUTH</button>

    <button onclick="switchSettingsTab('paths')" id="tab-paths"

        class="text-on-surface-variant font-label-mono text-label-mono">SYSTEM PATHS</button>

    <button onclick="switchSettingsTab('demons')" id="tab-demons"

        class="text-on-surface-variant font-label-mono text-label-mono">DEMONS</button>

</div>

<!-- Панель API & AUTH (уже существует, обернуть в div) -->

<div id="settings-panel-api" class="space-y-4">

    <!-- существующий контент auth_token + telemetry + telegram -->

</div>

<!-- Панель SYSTEM PATHS (новая) -->

<div id="settings-panel-paths" class="space-y-3 hidden">

    <div>

        <label class="text-[10px] text-on-surface-variant block mb-1">OBSIDIAN_VAULT_PATH</label>

        <div id="status-vault-path" class="font-label-mono text-[11px] text-primary border border-outline p-2 opacity-70">—</div>

    </div>

    <div>

        <label class="text-[10px] text-on-surface-variant block mb-1">HTTP_SERVER_PORT</label>

        <div id="status-orange-port" class="font-label-mono text-[11px] text-primary border border-outline p-2 opacity-70">—</div>

    </div>

</div>

<!-- Панель DEMONS (новая) -->

<div id="settings-panel-demons" class="space-y-3 hidden">

    <div class="flex justify-between items-center p-2 border border-outline">

        <span class="font-label-mono text-[11px]">WATCHDOG</span>

        <span id="status-watchdog" class="text-primary text-[10px] font-bold">ACTIVE</span>

    </div>

    <div class="flex justify-between items-center p-2 border border-outline">

        <span class="font-label-mono text-[11px]">TELEGRAM_DAEMON</span>

        <span id="status-telegram" class="text-[#00FF66] text-[10px] font-bold">MOCK</span>

    </div>

    <div class="flex justify-between items-center p-2 border border-outline">

        <span class="font-label-mono text-[11px]">MCP_CLIENT</span>

        <span id="status-mcp" class="text-on-surface-variant text-[10px] font-bold">OFFLINE</span>

    </div>

</div>

#### `ui/main.js`:

javascript

function switchSettingsTab(tabName) {

    ['api', 'paths', 'demons'].forEach(t => {

        document.getElementById(`settings-panel-${t}`)?.classList.add('hidden');

        const btn = document.getElementById(`tab-${t}`);

        if (btn) {

            btn.className = "text-on-surface-variant font-label-mono text-label-mono";

        }

    });

    document.getElementById(`settings-panel-${tabName}`)?.classList.remove('hidden');

    const activeBtn = document.getElementById(`tab-${tabName}`);

    if (activeBtn) {

        activeBtn.className = "text-primary font-label-mono text-label-mono border-b border-primary pb-0.5";

    }

    // Загружаем статусы при переходе на SYSTEM PATHS или DEMONS

    if ((tabName === 'paths' || tabName === 'demons') && window.pywebview) {

        window.pywebview.api.api_get_system_status().then(res => {

            const s = JSON.parse(res);

            document.getElementById('status-vault-path').textContent = s.obsidian_vault_path;

            document.getElementById('status-orange-port').textContent = `:${s.orange_port}`;

            document.getElementById('status-mcp').textContent = s.mcp_status;

        });

    }

}

window.switchSettingsTab = switchSettingsTab;

---

### 8. Telethon в requirements.txt

**Файл:** `requirements.txt`

Добавить строку:

```
telethon
```

---

## 🟡 ПРИОРИТЕТ 3 — Средние

---

### 4. MCP Dashboard — реальные статусы

**Затрагиваемые файлы:**

- `core/bridge.py` — метод `api_get_mcp_status()`
- `ui/main.js` — функция `openMCPDashboard()`
- `ui/index.html` — кнопка в топбаре + динамические статусы

#### `core/bridge.py`:

python

def api_get_mcp_status(self) -> str:

    """Возвращает статусы: SQLite, MCP-сервер"""

    import json, os

    mcp_connected = (

        self._deps.mcp_client is not None and 

        self._deps.mcp_client._session is not None

    )

    db_exists = os.path.exists("orange_memory.db")

    db_size_mb = round(os.path.getsize("orange_memory.db") / 1024 / 1024, 2) if db_exists else 0

    return json.dumps({

        "sqlite": {"status": "ONLINE" if db_exists else "ERROR", "size_mb": db_size_mb},

        "mcp": {"status": "CONNECTED" if mcp_connected else "OFFLINE"},

    })

#### `ui/main.js`:

javascript

async function openMCPDashboard() {

    if (window.pywebview) {

        const res = await window.pywebview.api.api_get_mcp_status();

        const s = JSON.parse(res);

        // Обновляем статусы в модале

        // SQLite

        const sqlEl = document.querySelector('#mcp-dashboard-modal [data-mcp="sqlite-status"]');

        if (sqlEl) sqlEl.textContent = s.sqlite.status;

        // MCP

        const mcpEl = document.querySelector('#mcp-dashboard-modal [data-mcp="mcp-status"]');

        if (mcpEl) mcpEl.textContent = s.mcp.status;

    }

    openModal('mcp-dashboard-modal');

}

window.openMCPDashboard = openMCPDashboard;

#### `ui/index.html` — добавить кнопку в топбар и data-атрибуты в модал:

html

<!-- В топбаре, рядом с EXPORT_TO_OBSIDIAN: -->

<button onclick="openMCPDashboard()" class="font-label-caps text-label-caps ...">

    <span class="material-symbols-outlined text-[16px]">hub</span>

    MCP_STATUS

</button>

<!-- В modals, изменить статичные блоки на динамические: -->

<span data-mcp="sqlite-status">LOADING...</span>

<span data-mcp="mcp-status">LOADING...</span>

---

### 5. PDF Attachment Config — выбор диапазона страниц

**Затрагиваемые файлы:**

- `core/bridge.py` — изменить `api_stage_file()`
- `ui/main.js` — вызов конфиг-модала для PDF

#### Логика:

1. При выборе PDF-файла — СНАЧАЛА показать модал конфигурации
2. После выбора режима — вызвать `api_stage_file_with_range(file_path, start_page, end_page)`

#### `core/bridge.py` — разбить на 2 метода:

python

def api_stage_file(self) -> str:

    """Открывает диалог, для PDF возвращает путь + кол-во страниц для конфигурации"""

    import webview, os, json

    if not self._window:

        return json.dumps({"status": "error", "message": "Окно не инициализировано"})

    try:

        result = self._window.create_file_dialog(dialog_type=webview.OPEN_DIALOG, allow_multiple=False,

            file_types=('Документы (*.txt;*.csv;*.md;*.pdf)', 'Все файлы (*.*)'))

        if not result:

            return json.dumps({"status": "cancelled"})

        file_path = result[0]

        _, ext = os.path.splitext(file_path)

        if ext.lower() == '.pdf':

            import pypdf

            reader = pypdf.PdfReader(file_path)

            page_count = len(reader.pages)

            return json.dumps({

                "status": "pdf_config_needed",

                "file_path": file_path,

                "filename": os.path.basename(file_path),

                "page_count": page_count

            })

        # Для остальных форматов — сразу читаем

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:

            content = f.read()

        return json.dumps({"status": "success", "filename": os.path.basename(file_path), "content": content})

    except Exception as e:

        return json.dumps({"status": "error", "message": str(e)})

def api_stage_pdf_with_range(self, file_path: str, start_page: int, end_page: int) -> str:

    """Извлекает текст из PDF по указанному диапазону страниц"""

    import json, os

    try:

        import pypdf

        filename = os.path.basename(file_path)

        reader = pypdf.PdfReader(file_path)

        total = len(reader.pages)

        s = max(0, start_page - 1)

        e = min(total, end_page)

        pages_text = [reader.pages[i].extract_text() or '' for i in range(s, e)]

        content = "\n".join(pages_text)

        return json.dumps({"status": "success", "filename": filename, "content": content})

    except Exception as ex:

        return json.dumps({"status": "error", "message": str(ex)})

#### `ui/main.js` — изменить `uploadFile()`:

javascript

async function uploadFile() {

    if (!window.pywebview) return;

    showLoader();

    try {

        const resultStr = await window.pywebview.api.api_stage_file();

        removeLoader();

        const result = JSON.parse(resultStr);

        if (result.status === 'success') {

            pendingAttachments.push({ filename: result.filename, content: result.content });

            renderAttachmentChips();

        } else if (result.status === 'pdf_config_needed') {

            // Показываем модал конфигурации PDF

            pendingPdfPath = result.file_path; // глобальная переменная

            document.getElementById('pdf-config-filename').textContent = `SOURCE: ${result.filename} (${result.page_count} pages)`;

            document.getElementById('pdf-page-count').value = result.page_count;

            openModal('attachment-config-modal');

        } else if (result.status !== 'cancelled') {

            appendMessage('Система', `Ошибка: ${result.message}`, 'sys');

        }

    } catch (e) {

        removeLoader();

        appendMessage('Система', `Сбой: ${e}`, 'sys');

    }

}

async function confirmPdfAttachment() {

    const allPages = document.getElementById('pdf-extract-all')?.checked;

    let startPage = 1, endPage = parseInt(document.getElementById('pdf-page-count').value);

    if (!allPages) {

        const rangeVal = document.getElementById('pdf-range-input').value;

        const match = rangeVal.match(/^(\d+)-(\d+)$/);

        if (match) { startPage = parseInt(match[1]); endPage = parseInt(match[2]); }

    }

    closeModal('attachment-config-modal');

    showLoader();

    const res = JSON.parse(await window.pywebview.api.api_stage_pdf_with_range(pendingPdfPath, startPage, endPage));

    removeLoader();

    if (res.status === 'success') {

        pendingAttachments.push({ filename: res.filename, content: res.content });

        renderAttachmentChips();

    }

}

window.confirmPdfAttachment = confirmPdfAttachment;

---

## 🔵 ПРИОРИТЕТ 4 — Низкий (большие задачи)

---

### 7. MCP Server (mcp_servers/index.ts)

**Файл:** `mcp_servers/index.ts`

MCP-сервер должен предоставлять инструменты для работы с Obsidian vault.

#### Минимальная реализация (Bun + MCP SDK):

typescript

import { Server } from "@modelcontextprotocol/sdk/server/index.js";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { readFileSync, readdirSync, writeFileSync, existsSync } from "fs";

import { join, extname } from "path";

const VAULT_PATH = process.env.OBSIDIAN_VAULT_PATH || "./test_vault";

const server = new Server(

    { name: "orange-obsidian-mcp", version: "1.0.0" },

    { capabilities: { tools: {} } }

);

server.setRequestHandler("tools/list", async () => ({

    tools: [

        {

            name: "read_note",

            description: "Читает содержимое .md заметки из Obsidian vault",

            inputSchema: {

                type: "object",

                properties: { path: { type: "string", description: "Относительный путь к заметке" } },

                required: ["path"]

            }

        },

        {

            name: "list_notes",

            description: "Возвращает список всех .md файлов в vault",

            inputSchema: { type: "object", properties: {} }

        },

        {

            name: "write_note",

            description: "Создаёт или перезаписывает заметку",

            inputSchema: {

                type: "object",

                properties: {

                    path: { type: "string" },

                    content: { type: "string" }

                },

                required: ["path", "content"]

            }

        }

    ]

}));

server.setRequestHandler("tools/call", async (request) => {

    const { name, arguments: args } = request.params;

    if (name === "list_notes") {

        const getAllMd = (dir: string): string[] => {

            const files: string[] = [];

            for (const f of readdirSync(dir, { withFileTypes: true })) {

                const fullPath = join(dir, f.name);

                if (f.isDirectory()) files.push(...getAllMd(fullPath));

                else if (extname(f.name) === ".md") files.push(fullPath.replace(VAULT_PATH + "/", ""));

            }

            return files;

        };

        return { content: [{ type: "text", text: getAllMd(VAULT_PATH).join("\n") }] };

    }

    if (name === "read_note") {

        const fullPath = join(VAULT_PATH, args.path as string);

        if (!existsSync(fullPath)) return { content: [{ type: "text", text: "Файл не найден" }] };

        return { content: [{ type: "text", text: readFileSync(fullPath, "utf-8") }] };

    }

    if (name === "write_note") {

        const fullPath = join(VAULT_PATH, args.path as string);

        writeFileSync(fullPath, args.content as string, "utf-8");

        return { content: [{ type: "text", text: `Записано: ${args.path}` }] };

    }

    throw new Error(`Unknown tool: ${name}`);

});

const transport = new StdioServerTransport();

await server.connect(transport);

**Также нужно:**

1. Установить MCP SDK: `bun add @modelcontextprotocol/sdk`
2. В `.env` указать путь к скрипту в `MCP_SERVER_URL=mcp_servers/index.ts`

---

### 6. Inline Assets & Code Actions Modal

**Затрагиваемые файлы:**

- `ui/main.js` — функция `openInlineAssetsModal()`
- `ui/index.html` — сделать список файлов динамическим + подключить Execute

Логика: при клике на кнопку `[ EXECUTE ]` рядом с блоком кода в сообщении агента — открыть этот модал с уже заполненным кодом и дать возможность запустить через `execute_python`.

javascript

async function executeCodeFromModal(code) {

    closeModal('inline-assets-modal');

    appendMessage('Система', 'Запуск кода через sandbox...', 'sys');

    showLoader();

    try {

        const result = await window.pywebview.api.run_agent('coder', 

            `Запусти этот код через execute_python и покажи результат:\n\`\`\`python\n${code}\n\`\`\``);

        removeLoader();

        appendMessage('Orange [Coder]', result, 'sys');

    } catch(e) {

        removeLoader();

        appendMessage('Orange', `Ошибка: ${e}`, 'sys');

    }

}

---

### 10. orange_core (Rust) — инструкция по сборке

**Новый файл:** `orange_core/BUILD.md`

markdown

# Сборка orange_core (Rust → Python модуль)

## Требования

- Rust toolchain: https://rustup.rs/

- maturin: `pip install maturin`

## Сборка

```bash

cd orange_core

maturin develop --release

После этого модуль `orange_core` будет доступен в текущем .venv.

## В Cargo.toml должно быть:

toml

[lib]

name = "orange_core"

crate-type = ["cdylib"]

[dependencies]

pyo3 = { version = "0.21", features = ["extension-module"] }

## Экспортируемые функции (src/lib.rs):

- `scan_vault_fast(path: str) -> str` — рекурсивный поиск .md файлов
- `read_file_fast(path: str) -> str` — быстрое чтение файла
- `fetch_website_fast(url: str) -> str` — HTTP GET запрос

---

## Итоговая очередь реализации

[1] delete_chat → db.py + bridge.py + main.js (~30 мин) [2] rename_chat → bridge.py + main.js (~15 мин) [9] search_chats → bridge.py + index.html + main.js (~45 мин) [3] settings tabs → index.html + main.js + bridge.py (~60 мин) [8] telethon в req.txt → requirements.txt (~2 мин) [4] MCP Dashboard → bridge.py + main.js + index.html (~45 мин) [5] PDF range config → bridge.py + main.js (~60 мин) [7] MCP Server → mcp_servers/index.ts (~2 часа) [6] Inline Assets modal → main.js (~45 мин) [10] orange_core docs → orange_core/BUILD.md (~15 мин)