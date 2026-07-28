try:
    import orange_core
except Exception:
    orange_core = None
from pydantic_ai import RunContext
from core.dependencies import OrangeDeps
import asyncio
import os
import datetime
from pathlib import Path
from core.path_safety import VaultNotConfiguredError, VaultPathResolver


def _tool_error(action: str, exc: Exception) -> str:
    if isinstance(exc, VaultNotConfiguredError):
        error_code = "NOT_CONFIGURED"
    elif isinstance(exc, (TypeError, ValueError)):
        error_code = "VALIDATION_ERROR"
    else:
        error_code = "PROVIDER_ERROR"
    return f"[{error_code}] {action}: {type(exc).__name__}"

def _orange_core_ready() -> bool:
    return orange_core is not None and hasattr(orange_core, "scan_vault_fast")

def _rust_build_hint() -> str:
    return "Rust-модуль orange_core не собран. Выполните: cd orange_core && maturin develop --release"

def validate_path(vault_root: str, user_path: str) -> str:
    """Backward-compatible wrapper around the shared vault path resolver."""
    resolver = VaultPathResolver(vault_root)
    raw_path = str(user_path)
    if raw_path.lower().endswith(".md"):
        return str(resolver.resolve_note(raw_path, search_by_name=True))
    direct = resolver.resolve(raw_path)
    if direct.exists() and direct.is_dir():
        return str(direct)
    return str(resolver.resolve_note(raw_path, search_by_name=True))

async def deep_analyze_website(ctx: RunContext, url: str) -> str:
    """Глубокий анализ веб-сайта с рендерингом JavaScript."""
    try:
        import asyncio
        from core.research import is_public_http_url
        from playwright.async_api import async_playwright

        if not await asyncio.to_thread(is_public_http_url, url):
            return "[VALIDATION_ERROR] Only public HTTP(S) URLs are allowed."
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                async def guard_request(route):
                    allowed = await asyncio.to_thread(
                        is_public_http_url,
                        route.request.url,
                    )
                    if allowed:
                        await route.continue_()
                    else:
                        await route.abort()

                await page.route("**/*", guard_request)
                await page.goto(url, wait_until="networkidle", timeout=30000)
                text = await page.evaluate("document.body.innerText")
            finally:
                await browser.close()
            
            if not text:
                return "Не удалось извлечь текст страницы."
                
            return text[:15000] if len(text) > 15000 else text
    except Exception as e:
        return f"[PROVIDER_ERROR] Website analysis failed: {type(e).__name__}"

def scan_vault_fast(ctx: RunContext[OrangeDeps], path: str) -> str:
    """Рекурсивный поиск .md файлов в хранилище Obsidian."""
    try:
        valid_path = validate_path(ctx.deps.obsidian_vault_path, path)
        if _orange_core_ready():
            md_files = orange_core.scan_vault_fast(valid_path)
            if not md_files:
                return f"В директории {valid_path} нет .md файлов."
            shown = "\n".join(f"- {file_path}" for file_path in md_files[:50])
            suffix = "\n...[остальные скрыты ради экономии контекста]" if len(md_files) > 50 else ""
            return f"Найдены заметки:\n{shown}{suffix}"
        md_files = []
        resolver = VaultPathResolver(ctx.deps.obsidian_vault_path)
        scan_root = Path(valid_path).resolve(strict=False)
        for file_path in resolver.iter_notes():
            try:
                file_path.relative_to(scan_root)
            except ValueError:
                continue
            md_files.append(str(file_path))
        if not md_files:
            return f"{_rust_build_hint()}\nВ директории {valid_path} нет .md файлов."
        shown = "\n".join(f"- {file_path}" for file_path in md_files[:50])
        suffix = "\n...[остальные скрыты ради экономии контекста]" if len(md_files) > 50 else ""
        return f"{_rust_build_hint()}\nFallback Python scan найден заметки:\n{shown}{suffix}"
    except Exception as e:
        return _tool_error("Vault scan failed", e)

async def read_file_fast(ctx: RunContext[OrangeDeps], file_path: str) -> str:
    """Чтение содержимого файла через интерфейс Obsidian CLI."""
    try:
        obsidian_root = ctx.deps.obsidian_vault_path
        valid_path = validate_path(obsidian_root, file_path)
        rel_path = os.path.relpath(valid_path, obsidian_root)
        rel_path = rel_path.replace('\\', '/')
        
        from core.markdown_ops import read_note_cli
        return await read_note_cli(rel_path, vault_path=obsidian_root)
    except Exception as e:
        return _tool_error("Note read failed", e)

from core.services.write_preview_service import WritePreviewService, confirm_and_apply_plan

async def rewrite_file(ctx: RunContext[OrangeDeps], file_path: str, content: str) -> str:
    """
    Безопасная и атомарная перезапись файла (особенно для заметок Obsidian).
    Использует временные файлы и механизм retry для обхода блокировок iCloud.
    """
    try:
        preview = WritePreviewService(ctx.deps.obsidian_vault_path)
        plan = preview.build_plan(file_path, content, action="rewrite_file")
        approved = await confirm_and_apply_plan(
            ctx.deps,
            plan,
            "vault_write",
            f"Rewrite note {plan['relative_path']}",
        )
        if not approved:
            return "Отклонено: файл не был изменен."
        return "Успех: файл перезаписан"
    except Exception as e:
        return _tool_error("Note rewrite failed", e)

import aiofiles
from core.markdown_ops import append_task_to_markdown

async def add_task(ctx: RunContext, file_path: str, task: str) -> str:
    """
    Инструмент для точечного добавления новой задачи (чекбокса) в markdown-файл.
    Сохраняет структуру Obsidian.
    """
    try:
        task = str(task or "").strip()
        if not task:
            return "[VALIDATION_ERROR] Task text is empty."
        if len(task.encode("utf-8")) > 10_000:
            return "[VALIDATION_ERROR] Task text exceeds 10 KB."

        # Keep the legacy year routing but discard any directory supplied by the model.
        file_name = Path(str(file_path).replace("\\", "/")).name
        file_name = "".join(
            character
            for character in file_name
            if character not in '<>:"/\\|?*\0'
        ).strip(" .")
        if not file_name:
            file_name = "Tasks.md"
        if not file_name.lower().endswith('.md'):
            file_name += '.md'
        current_year = str(datetime.date.today().year)
        safe_rel_path = os.path.join(current_year, file_name)
        obsidian_root = ctx.deps.obsidian_vault_path
        preview = WritePreviewService(obsidian_root)
        full_path = preview.resolve_vault_path(safe_rel_path)
        
        print("[add_task] Prepared an approval-gated task update.")
            
        # Чтение файла, если он существует, иначе создаем шаблон
        if full_path.exists():
            content = await asyncio.to_thread(
                VaultPathResolver(obsidian_root).read_note_text,
                full_path,
                max_chars=preview.max_write_bytes + 1,
            )
            if len(content.encode("utf-8")) > preview.max_write_bytes:
                return "[VALIDATION_ERROR] Target note exceeds the 2 MB write limit."
        else:
            content = "# Задачи\n\n"
            
        # Парсинг и модификация
        new_content = append_task_to_markdown(content, task)
        
        plan = preview.build_plan(full_path, new_content, action="add_task")
        approved = await confirm_and_apply_plan(
            ctx.deps,
            plan,
            "vault_write",
            f"Add task to {plan['relative_path']}",
        )
        if not approved:
            return "Отклонено: задача не была добавлена."
        
        return "Успех: задача добавлена в файл"
    except Exception as e:
        return _tool_error("Task write failed", e)

# --- ИНСТРУМЕНТЫ ПАМЯТИ ---

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СЕМАНТИЧЕСКОГО ПОИСКА ---

async def get_embedding(text: str, api_key: str) -> list:
    """Генерирует векторный эмбеддинг текста с использованием модели gemini-embedding-2"""
    import httpx
    model_name = os.environ.get("ORANGE_EMBEDDING_MODEL", "gemini-embedding-2")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    body = {
        "content": {"parts": [{"text": text}]}
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        return data["embedding"]["values"]

def cosine_similarity(v1: list, v2: list) -> float:
    import math
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)

async def _search_memory_like_fallback(ctx: RunContext, query: str) -> str:
    from core import db
    query = str(query or "").strip()[:500]
    escaped_query = (
        query.replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_")
    )
    search_term = f"%{escaped_query}%"
    with db.get_connection() as conn:
        cursor = conn.execute(
            '''SELECT m.*, c.title
               FROM messages m
               JOIN chats c ON m.chat_id = c.id
               WHERE m.content LIKE ? ESCAPE '!'
                 AND COALESCE(m.exclude_from_rag, 0) = 0
               ORDER BY COALESCE(m.is_pinned, 0) DESC, m.timestamp DESC, m.id DESC
               LIMIT 20''',
            (search_term,)
        )
        results = [dict(row) for row in cursor.fetchall()]
    if not results:
        return f"Ничего не найдено в памяти по запросу '{query}'"
        
    snippets = []
    for r in results[:12]:
        pin_marker = " [PINNED]" if bool(r.get("is_pinned")) else ""
        snippets.append(
            f"[Чат: {r['title']}]{pin_marker} "
            f"{r['role'].upper()}: {str(r['content'])[:1500]}"
        )
    return "\n---\n".join(snippets)

# --- ИНСТРУМЕНТЫ ПАМЯТИ ---

async def search_memory(ctx: RunContext, query: str) -> str:
    """
    Семантический поиск по базе данных (памяти) прошлых диалогов ИИ-ассистента с пользователем.
    Вычисляет сходство векторов через Gemini Embeddings API.
    """
    from core import db
    import json
    
    query = str(query or "").strip()[:500]
    if not query:
        return "[VALIDATION_ERROR] Memory query is empty."
    api_key = ctx.deps.settings.gemini_api_key
    embedding_model = os.environ.get(
        "ORANGE_EMBEDDING_MODEL",
        "gemini-embedding-2",
    )
    if not api_key:
        print("[RAG WARNING] Отсутствует gemini_api_key, переключаюсь на LIKE-фоллбек.")
        return await _search_memory_like_fallback(ctx, query)
        
    try:
        query_vector = await get_embedding(query, api_key)
    except Exception as e:
        print(f"[RAG WARNING] Embedding query failed ({type(e).__name__}); using LIKE fallback.")
        return await _search_memory_like_fallback(ctx, query)
        
    # Вытаскиваем все сообщения
    try:
        with db.get_connection() as conn:
            cursor = conn.execute(
                '''SELECT m.id, m.content, m.role, m.is_pinned, c.title
                   FROM messages m 
                   JOIN chats c ON m.chat_id = c.id
                   WHERE COALESCE(m.exclude_from_rag, 0) = 0
                   ORDER BY COALESCE(m.is_pinned, 0) DESC, m.timestamp DESC, m.id DESC
                   LIMIT 200'''
            )
            messages = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[RAG Error] Database search failed: {type(e).__name__}")
        return f"[PROVIDER_ERROR] Memory database search failed: {type(e).__name__}"
        
    if not messages:
        return f"Ничего не найдено в памяти по запросу '{query}' (история пуста)."
        
    scored_messages = []
    uncached_budget = 20
    for msg in messages:
        msg_id = msg["id"]
        content = msg["content"]
        # Игнорируем служебные сообщения
        if content.startswith("[Служебный системный контекст:"):
            continue
            
        emb_json = db.get_cached_embedding(msg_id, embedding_model)
        emb_vector = None
        if emb_json:
            try:
                emb_vector = json.loads(emb_json)
            except Exception:
                pass
                
        if not emb_vector:
            if uncached_budget <= 0:
                continue
            uncached_budget -= 1
            try:
                emb_vector = await get_embedding(content[:1000], api_key)
                db.save_cached_embedding(
                    msg_id,
                    json.dumps(emb_vector),
                    embedding_model,
                )
            except Exception as e:
                print(f"[RAG WARNING] Message embedding {msg_id} failed: {type(e).__name__}")
                continue
                
        similarity = cosine_similarity(query_vector, emb_vector)
        if bool(msg.get("is_pinned")):
            similarity += 0.08
        scored_messages.append((similarity, msg))
        
    # Сортируем по косинусному сходству
    scored_messages.sort(key=lambda x: x[0], reverse=True)
    
    # Отбираем топ-5 релевантных (сходство > 0.3)
    top_results = [item for item in scored_messages[:5] if item[0] > 0.3]
    if not top_results:
        return f"Семантически близких совпадений по запросу '{query}' не найдено."
        
    snippets = []
    for score, r in top_results:
        pin_marker = " [PINNED]" if bool(r.get("is_pinned")) else ""
        snippets.append(
            f"[Чат: {r['title']}]{pin_marker} "
            f"[Сходство: {score:.2f}] {r['role'].upper()}: "
            f"{str(r['content'])[:1500]}"
        )
        
    return "\n---\n".join(snippets)

async def export_active_chat(chat_id: str, deps) -> str:
    """Функция экспорта чата (вызывается напрямую из bridge.py, не как инструмент агента)"""
    from core import db
    import uuid
    
    history = db.get_chat_history(chat_id)
    if not history:
        return "Чат пуст."
    if not deps.settings.gemini_api_key:
        return "[NOT_CONFIGURED] GOOGLE_API_KEY is required to export a summarized chat."
        
    lines = []
    for msg in history:
        lines.append(f"**{msg['role'].upper()}**:\n{msg['content']}\n")
    full_chat = "\n".join(lines)
    if len(full_chat) > 100_000:
        full_chat = (
            "[Earlier messages omitted because the export context exceeded 100 KB.]\n\n"
            + full_chat[-100_000:]
        )
    
    from core.agent import agent as root_agent, HEAVY_MODEL
    prompt = (
        "Ты технический писатель. Скомпилируй из этого диалога сухую Markdown-статью. "
        "Выкинь воду, оставь решения, код и задачи.\n\n"
        f"ДИАЛОГ:\n{full_chat}"
    )
    
    import asyncio

    result = await asyncio.wait_for(
        root_agent.run(
            prompt,
            model=HEAVY_MODEL,
            deps=deps,
            model_settings={"timeout": 120.0},
        ),
        timeout=130.0,
    )
    markdown_result = getattr(result, 'data', getattr(result, 'output', str(result)))
    
    filename = f"Export_{uuid.uuid4().hex[:8]}.md"
    obsidian_root = deps.obsidian_vault_path
    target_path = os.path.join(obsidian_root, "04-projects", filename)
    
    preview = WritePreviewService(deps.obsidian_vault_path)
    plan = preview.build_plan(target_path, markdown_result, action="export_chat")
    approved = await confirm_and_apply_plan(
        deps,
        plan,
        "vault_write",
        f"Export active chat to {plan['relative_path']}",
    )
    if not approved:
        return "Отклонено: экспорт не был записан."
    return f"Успех! Чат экспортирован в {target_path}"

# --- ИНСТРУМЕНТЫ DEEP RESEARCH (OSINT) ---

async def fetch_url(ctx: RunContext, url: str) -> str:
    """
    Загружает веб-страницу по указанному URL, очищает её от HTML-тегов, скриптов и стилей,
    и возвращает чистый текстовый контент (лимит 12000 символов).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        from core.research import fetch_public_page

        print("[fetch_url] Loading a validated public page.")
        return await fetch_public_page(url)
    except Exception as e:
        return f"[VALIDATION_ERROR] URL could not be loaded: {type(e).__name__}"

# --- ИНСТРУМЕНТ ЛОКАЛЬНОГО ВЫПОЛНЕНИЯ КОДА (SANDBOX) ---

SAFE_PYTHON_IMPORTS = {
    "collections",
    "datetime",
    "decimal",
    "fractions",
    "itertools",
    "json",
    "math",
    "random",
    "re",
    "statistics",
}

BLOCKED_PYTHON_NAMES = {
    "__import__",
    "__builtins__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "getattr",
    "help",
    "input",
    "locals",
    "memoryview",
    "object",
    "open",
    "setattr",
    "delattr",
    "type",
    "vars",
}

BLOCKED_PYTHON_ATTRIBUTES = {
    "chmod",
    "chown",
    "connect",
    "exec",
    "fork",
    "kill",
    "mkdir",
    "open",
    "popen",
    "remove",
    "rename",
    "replace",
    "request",
    "rmdir",
    "run",
    "rmtree",
    "send",
    "socket",
    "spawn",
    "system",
    "unlink",
    "walk",
    "write",
}

MAX_EXECUTOR_OUTPUT_BYTES = 50 * 1024
MAX_EXECUTOR_CODE_BYTES = 100 * 1024

def validate_python_for_restricted_executor(code: str) -> None:
    """Rejects code that asks for file, process, network, or non-whitelisted imports."""
    import ast
    import re

    if len(code.encode("utf-8")) > MAX_EXECUTOR_CODE_BYTES:
        raise ValueError("Python code exceeds the 100 KB executor limit.")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_PYTHON_IMPORTS:
                    raise ValueError(f"Import '{alias.name}' is not permitted in restricted executor.")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            private_name = any(alias.name.startswith("_") for alias in node.names)
            if node.level or root not in SAFE_PYTHON_IMPORTS or private_name:
                raise ValueError(f"Import from '{node.module}' is not permitted in restricted executor.")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_PYTHON_NAMES:
            raise ValueError(f"Identifier '{node.id}' is blocked in restricted executor.")
        elif isinstance(node, ast.Attribute) and node.attr in BLOCKED_PYTHON_ATTRIBUTES:
            raise ValueError(f"Attribute '.{node.attr}' is blocked in restricted executor.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Private attribute access is blocked in restricted executor.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            path_parts = value.replace("\\", "/").split("/")
            if (
                value.startswith(("/", "~", "\\\\"))
                or re.match(r"^[A-Za-z]:[\\/]", value)
                or ".." in path_parts
            ):
                raise ValueError("Absolute path access is blocked in restricted executor.")


def _decode_limited_output(data: bytes) -> str:
    truncated = len(data) > MAX_EXECUTOR_OUTPUT_BYTES
    text = data[:MAX_EXECUTOR_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if truncated:
        text += "\n...[output truncated to 50 KB]"
    return text

async def execute_python_restricted(code: str, request_approval=None) -> str:
    """
    Runs Python in a restricted local subprocess after explicit user approval.
    This is not a VM boundary, but it blocks filesystem/network/process APIs and
    only allows a small import whitelist for calculations.
    """
    try:
        validate_python_for_restricted_executor(code)
    except Exception as e:
        return f"[VALIDATION_ERROR] Restricted executor rejected the code: {e}"

    if not request_approval:
        return "[NOT_CONFIGURED] Python execution approval callback is unavailable."
        
    approved = await request_approval(f"PYTHON_EXECUTION\n{code}")
    if not approved:
        return "[APPROVAL_DENIED] Python code was not executed."

    import sys
    import subprocess
    import asyncio
    import uuid
    
    print(f"[execute_python] Получен запрос на запуск Python-кода (длина: {len(code)} символов)")
    
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sandbox_root = os.path.join(project_root, ".orange_runtime", "sandbox")
    os.makedirs(sandbox_root, exist_ok=True)
    run_id = uuid.uuid4().hex
    temp_path = os.path.join(sandbox_root, f"user_{run_id}.py")
    stdout_path = os.path.join(sandbox_root, f"user_{run_id}.stdout")
    stderr_path = os.path.join(sandbox_root, f"user_{run_id}.stderr")
    process = None

    try:
        with open(temp_path, mode='w', encoding='utf-8') as temp_file:
            temp_file.write(code)

        executable_path = sys.executable.replace('\\', '/')
        script_path = temp_path.replace('\\', '/')

        with open(stdout_path, "wb") as stdout_file, open(stderr_path, "wb") as stderr_file:
            process = await asyncio.create_subprocess_exec(
                executable_path,
                "-I",
                "-c",
                _executor_bootstrap(),
                script_path,
                cwd=sandbox_root,
                env={
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONNOUSERSITE": "1",
                },
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            stop_reason = await _monitor_restricted_process(
                process,
                stdout_path,
                stderr_path,
            )

        stdout_bytes = _read_limited_file(stdout_path)
        stderr_bytes = _read_limited_file(stderr_path)
        stdout = _decode_limited_output(stdout_bytes)
        stderr = _decode_limited_output(stderr_bytes)

        if stop_reason == "timeout":
            return "[TIMEOUT] Python execution exceeded 10 seconds and was stopped."
        if stop_reason == "output_limit":
            return (
                "[VALIDATION_ERROR] Python execution exceeded the 50 KB output limit.\n\n"
                f"[STDOUT]\n{stdout or '<empty>'}\n\n[STDERR]\n{stderr or '<empty>'}"
            )
        if process.returncode != 0:
            return (
                f"[VALIDATION_ERROR] Python exited with code {process.returncode}.\n\n"
                f"[STDERR]\n{stderr or '<empty>'}\n\n"
                f"[STDOUT]\n{stdout or '<empty>'}"
            )

        output_lines = [f"=== EXECUTION RESULT (exit code: {process.returncode}) ==="]
        if stdout:
            output_lines.append(f"[STDOUT]\n{stdout}")
        if stderr:
            output_lines.append(f"[STDERR]\n{stderr}")
        if not stdout and not stderr:
            output_lines.append("[Process completed without output]")
        return "\n\n".join(output_lines)
    except Exception as e:
        return f"[PROVIDER_ERROR] Restricted executor failed: {type(e).__name__}"
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
        for runtime_path in (temp_path, stdout_path, stderr_path):
            try:
                os.remove(runtime_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


async def execute_python(ctx: RunContext[OrangeDeps], code: str) -> str:
    """Compatibility wrapper for callers that already provide an Orange RunContext."""
    return await execute_python_restricted(code, ctx.deps.request_override)


async def _monitor_restricted_process(process, stdout_path: str, stderr_path: str) -> str:
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10.0
    while process.returncode is None:
        output_size = _safe_file_size(stdout_path) + _safe_file_size(stderr_path)
        if output_size > MAX_EXECUTOR_OUTPUT_BYTES:
            process.kill()
            await process.wait()
            return "output_limit"
        remaining = deadline - loop.time()
        if remaining <= 0:
            process.kill()
            await process.wait()
            return "timeout"
        try:
            await asyncio.wait_for(process.wait(), timeout=min(0.05, remaining))
        except asyncio.TimeoutError:
            continue
    if _safe_file_size(stdout_path) + _safe_file_size(stderr_path) > MAX_EXECUTOR_OUTPUT_BYTES:
        return "output_limit"
    return "completed"


def _safe_file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _read_limited_file(path: str) -> bytes:
    try:
        with open(path, "rb") as file:
            return file.read(MAX_EXECUTOR_OUTPUT_BYTES + 1)
    except OSError:
        return b""


def _executor_bootstrap() -> str:
    """Set resource and audit limits inside isolated child Python."""
    return (
        "import os,runpy,sys\n"
        "try:\n"
        " import resource\n"
        " resource.setrlimit(resource.RLIMIT_CPU,(10,10))\n"
        f" resource.setrlimit(resource.RLIMIT_FSIZE,({MAX_EXECUTOR_OUTPUT_BYTES + 4096},{MAX_EXECUTOR_OUTPUT_BYTES + 4096}))\n"
        " resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))\n"
        " resource.setrlimit(resource.RLIMIT_CORE,(0,0))\n"
        " if hasattr(resource,'RLIMIT_AS'):\n"
        "  resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456))\n"
        "except Exception:\n"
        " pass\n"
        "_script=os.path.realpath(sys.argv[1])\n"
        "_read_roots=tuple(dict.fromkeys(os.path.realpath(p) for p in (sys.base_prefix,sys.prefix) if p))\n"
        "_blocked_prefixes=('socket.','subprocess.','ctypes.','http.client.','urllib.','ftplib.','smtplib.')\n"
        "_blocked_events={'os.chdir','os.chmod','os.chown','os.exec','os.fork','os.kill','os.link','os.mkdir','os.posix_spawn','os.remove','os.rename','os.rmdir','os.spawn','os.symlink','os.system','os.truncate','shutil.copyfile'}\n"
        "def _inside_read_roots(path):\n"
        " try:\n"
        "  return any(os.path.commonpath((path,root))==root for root in _read_roots)\n"
        " except (TypeError,ValueError):\n"
        "  return False\n"
        "def _audit(event,args):\n"
        " if event=='open':\n"
        "  path=args[0] if args else ''\n"
        "  mode=args[1] if len(args)>1 else 'r'\n"
        "  flags=args[2] if len(args)>2 else 0\n"
        "  if isinstance(path,int):\n"
        "   return\n"
        "  resolved=os.path.realpath(os.fspath(path))\n"
        "  write_mode=isinstance(mode,str) and any(ch in mode for ch in 'wax+')\n"
        "  write_flags=isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))\n"
        "  if write_mode or write_flags or (resolved!=_script and not _inside_read_roots(resolved)):\n"
        "   raise PermissionError('Restricted executor blocked file access')\n"
        " if event in _blocked_events or event.startswith(_blocked_prefixes):\n"
        "  raise PermissionError('Restricted executor blocked system access')\n"
        "sys.addaudithook(_audit)\n"
        "runpy.run_path(sys.argv[1],run_name='__main__')\n"
    )

# --- ИНСТРУМЕНТ СКАНИРОВАНИЯ ЗАМЕТОК (OBSIDIAN WIKILINKS) ---

async def list_existing_notes(ctx: RunContext) -> str:
    """
    Возвращает плоский список имен существующих заметок в хранилище Obsidian.
    Используется агентом, чтобы рекомендовать релевантные внутренние связи в формате [[Имя заметки]].
    """
    try:
        obsidian_root = ctx.deps.obsidian_vault_path
        resolver = VaultPathResolver(obsidian_root)
        notes = [
            path.relative_to(resolver.root).with_suffix("").as_posix()
            for path in resolver.iter_notes(exclude_generated=True)
        ]
                
        if not notes:
            return "Заметки в Obsidian не обнаружены."
            
        unique_notes = sorted(list(set(notes)))
        
        # Ограничение контекстного окна
        if len(unique_notes) > 200:
            return "Существующие заметки в Obsidian (первые 200):\n" + "\n".join(unique_notes[:200]) + "\n... [Список обрезан]"
            
        return "Существующие заметки в Obsidian:\n" + "\n".join(unique_notes)
    except Exception as e:
        return _tool_error("Note listing failed", e)

# --- ИНСТРУМЕНТЫ OSINT И АВТО-РАСКРЫТИЯ ССЫЛОК ---

async def scout_website(ctx: RunContext[OrangeDeps], url: str) -> str:
    """
    Выполняет быстрый аудит безопасности и технологий веб-сайта (OSINT).
    Проверяет CMS, заголовки сервера, HTTPS и наличие уязвимостей.
    """
    from bs4 import BeautifulSoup
    import urllib.parse
    import re
    from core.research import fetch_public_html

    # Normalize URL
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    report = [f"# Отчет об аудите домена: {url}\n"]
    try:
        response = await fetch_public_html(url)
        headers = {
            str(key).lower(): value
            for key, value in response["headers"].items()
        }
        html = response["text"]
        status = response["status"]

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Tech stack checks
        techs = []
        meta_generator = soup.find('meta', attrs={'name': 'generator'})
        if meta_generator:
            techs.append(f"CMS (Generator): {meta_generator.get('content')}")
        
        html_str = html.lower()
        if "wp-content" in html_str:
            techs.append("CMS: WordPress")
        if "bitrix" in html_str:
            techs.append("CMS: 1C-Bitrix")
        if "tilda" in html_str:
            techs.append("CMS: Tilda")
        if "webflow" in html_str:
            techs.append("CMS: Webflow")
        if "joomla" in html_str:
            techs.append("CMS: Joomla")
        if "drupal" in html_str:
            techs.append("CMS: Drupal")
        if "next/js" in html_str or "_next/static" in html_str:
            techs.append("Framework: Next.js")
        if "react" in html_str:
            techs.append("Framework: React")
        if "vue" in html_str:
            techs.append("Framework: Vue.js")

        server = headers.get("server", "Не указан")
        powered_by = headers.get("x-powered-by", "Не указан")

        report.append("## 🛠️ Технологический стек")
        report.append(f"- **Сервер**: `{server}`")
        report.append(f"- **Powered By**: `{powered_by}`")
        if techs:
            report.append("- **Обнаруженные технологии**:")
            for t in techs:
                report.append(f"  - {t}")
        else:
            report.append("- **Обнаруженные технологии**: Не определено (кастомный стек)")

        # 2. Security checks
        sec = []
        is_https = url.startswith("https://")
        if not is_https:
            sec.append("❌ Сайт работает по незащищенному протоколу HTTP.")
        else:
            sec.append("✅ Сайт работает по защищенному протоколу HTTPS.")

        hsts = headers.get("strict-transport-security")
        if hsts:
            sec.append("✅ Заголовок HSTS (Strict-Transport-Security) настроен.")
        else:
            sec.append("⚠️ Отсутствует заголовок HSTS.")

        csp = headers.get("content-security-policy")
        if csp:
            sec.append("✅ Заголовок CSP (Content-Security-Policy) настроен.")
        else:
            sec.append("⚠️ Отсутствует заголовок CSP (защита от XSS).")

        xfo = headers.get("x-frame-options")
        if xfo:
            sec.append("✅ Заголовок X-Frame-Options настроен (защита от кликджекинга).")
        else:
            sec.append("⚠️ Отсутствует заголовок X-Frame-Options.")

        report.append("\n## 🔒 Безопасность")
        for s in sec:
            report.append(s)

        # 3. Quick audit of common leaks
        parsed = urllib.parse.urlparse(url)
        git_url = f"{parsed.scheme}://{parsed.netloc}/.git/config"
        try:
            git_res = await fetch_public_html(git_url, limit=100_000)
            if git_res["status"] == 200 and "[core]" in git_res["text"]:
                report.append("\n🚨 **КРИТИЧЕСКАЯ УЯЗВИМОСТЬ: Обнаружена открытая папка .git!**")
                report.append(f"Доступна по адресу: {git_url}")
        except Exception:
            pass

        return "\n".join(report)

    except Exception as e:
        return f"[PROVIDER_ERROR] Website audit failed: {type(e).__name__}"

async def expand_note_links(ctx: RunContext[OrangeDeps], file_path: str) -> str:
    """
    Находит все внешние ссылки (HTTP/HTTPS) в заметке, скачивает их содержимое,
    делает краткую выжимку и дописывает в конец заметки как приложение.
    """
    import re
    valid_path = validate_path(ctx.deps.obsidian_vault_path, file_path)
    if not os.path.exists(valid_path):
        return f"Ошибка: файл {file_path} не найден."

    resolver = VaultPathResolver(ctx.deps.obsidian_vault_path)
    content = resolver.read_note_text(valid_path, max_chars=2 * 1024 * 1024 + 1)
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        return "[VALIDATION_ERROR] Note exceeds the 2 MB expansion limit."

    # Find raw markdown HTTP/HTTPS links
    urls = re.findall(r'https?://[^\s\)\>\]]+', content)
    if not urls:
        return "Внешних ссылок для раскрытия в заметке не найдено."

    # De-duplicate
    urls = sorted(set(urls))[:10]
    
    from bs4 import BeautifulSoup
    from core.folding import summarize_text
    from core.research import fetch_public_html
    
    appendix = ["\n\n## 🔗 Приложения и веб-источники (Авто-раскрытие)\n"]
    api_key = ctx.deps.settings.gemini_api_key
    if not api_key:
        return "Ошибка: Для саммаризации ссылок необходим GEMINI_API_KEY."

    for url in urls:
        if "127.0.0.1" in url or "localhost" in url:
            continue
        try:
            print("[Link Expansion] Loading a validated public source.")
            res = await fetch_public_html(url)
            if res["status"] != 200:
                continue
            soup = BeautifulSoup(res["text"], 'html.parser')
            text = soup.get_text()
            text = re.sub(r'\s+', ' ', text).strip()[:4000]
                
            summary = await summarize_text(f"Сайт: {url}\n\nТекст:\n{text}", api_key)
            title = soup.title.string if soup.title and soup.title.string else url
            appendix.append(f"### {title.strip()}\n- **Ссылка**: {url}\n- **Выжимка**:\n{summary}\n")
        except Exception as e:
            print(f"[Link Expansion Warning] Failed to expand a source: {type(e).__name__}")
            
    if len(appendix) > 1:
        new_content = content + "\n" + "\n".join(appendix)
        preview = WritePreviewService(ctx.deps.obsidian_vault_path)
        plan = preview.build_plan(valid_path, new_content, action="expand_note_links")
        approved = await confirm_and_apply_plan(
            ctx.deps,
            plan,
            "vault_write",
            f"Expand links in {plan['relative_path']}",
        )
        if not approved:
            return "Отклонено: ссылки не были добавлены в заметку."
        return f"Успешно раскрыто {len(appendix) - 1} ссылок(и) и добавлено в конец заметки."
        
    return "Не удалось раскрыть ссылки в заметке."

async def patch_file(ctx: RunContext[OrangeDeps], file_path: str, search_block: str, replace_block: str) -> str:
    """
    Точечное редактирование (патчинг) файла в хранилище.
    Заменяет уникальное совпадение search_block на replace_block.
    """
    try:
        if not isinstance(search_block, str) or not search_block:
            return "[VALIDATION_ERROR] Search block is empty."
        if not isinstance(replace_block, str):
            return "[VALIDATION_ERROR] Replacement block must be text."
        if len(search_block.encode("utf-8")) > 100_000 or len(replace_block.encode("utf-8")) > 100_000:
            return "[VALIDATION_ERROR] Patch blocks must be at most 100 KB each."
        valid_path = validate_path(ctx.deps.obsidian_vault_path, file_path)
        if not os.path.exists(valid_path):
            return f"Ошибка: файл {file_path} не найден."
        resolver = VaultPathResolver(ctx.deps.obsidian_vault_path)
        content = await asyncio.to_thread(
            resolver.read_note_text,
            valid_path,
            max_chars=2 * 1024 * 1024 + 1,
        )
        if len(content.encode("utf-8")) > 2 * 1024 * 1024:
            return "[VALIDATION_ERROR] Note exceeds the 2 MB patch limit."
            
        occurrences = content.count(search_block)
        if occurrences == 0:
            return f"Ошибка: блок поиска не найден в файле. Убедитесь в точном соответствии символов и пробелов."
        if occurrences > 1:
            return f"Ошибка: блок поиска найден {occurrences} раз(а). Блок поиска должен быть уникальным во избежание ошибочных замен."
            
        new_content = content.replace(search_block, replace_block, 1)
        preview = WritePreviewService(ctx.deps.obsidian_vault_path)
        plan = preview.build_plan(valid_path, new_content, action="patch_file")
        approved = await confirm_and_apply_plan(
            ctx.deps,
            plan,
            "vault_write",
            f"Patch note {plan['relative_path']}",
        )
        if not approved:
            return "Отклонено: файл не был отредактирован."
        return "Успех: файл успешно отредактирован."
    except Exception as e:
        return _tool_error("Note patch failed", e)

async def view_file_range(ctx: RunContext[OrangeDeps], file_path: str, start_line: int, end_line: int) -> str:
    """
    Чтение определенного диапазона строк файла с нумерацией строк (1-indexed).
    Помогает экономить контекст при работе с большими файлами.
    """
    try:
        valid_path = validate_path(ctx.deps.obsidian_vault_path, file_path)
        if not os.path.exists(valid_path):
            return f"Ошибка: файл {file_path} не найден."
            
        start_line = int(start_line)
        end_line = int(end_line)
        if end_line - start_line > 500:
            end_line = start_line + 500
        resolver = VaultPathResolver(ctx.deps.obsidian_vault_path)
        content = await asyncio.to_thread(
            resolver.read_note_text,
            valid_path,
            max_chars=2 * 1024 * 1024,
        )
        lines = content.splitlines(keepends=True)
            
        total_lines = len(lines)
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
        if start_line > end_line:
            return f"Ошибка: start_line ({start_line}) не может быть больше end_line ({end_line})."
            
        output = []
        for idx in range(start_line - 1, end_line):
            output.append(f"{idx + 1}: {lines[idx].rstrip(chr(13) + chr(10))}")
            if sum(len(item) for item in output) > 100_000:
                output.append("...[range output truncated]")
                break
            
        header = f"=== Просмотр файла {file_path} (Строки {start_line}-{end_line} из {total_lines}) ===\n"
        return header + "\n".join(output)
    except Exception as e:
        return _tool_error("Note range read failed", e)
