import orange_core
from pydantic_ai import RunContext
from core.dependencies import OrangeDeps
import os
import datetime

def validate_path(vault_root: str, user_path: str) -> str:
    """
    Resolves the path to an absolute normalized path.
    Checks if it is inside the absolute vault root using os.path.commonpath.
    Raises ValueError with a clear error message if the path resides outside the vault root.
    """
    abs_vault_root = os.path.abspath(os.path.normpath(vault_root))
    if os.path.isabs(user_path):
        resolved_path = os.path.abspath(os.path.normpath(user_path))
    else:
        resolved_path = os.path.abspath(os.path.normpath(os.path.join(abs_vault_root, user_path)))
        
    try:
        common = os.path.commonpath([abs_vault_root, resolved_path])
    except ValueError as e:
        raise ValueError(f"Путь находится вне хранилища: {user_path}. Ошибка: {e}")
        
    if common != abs_vault_root:
        raise ValueError(f"Путь находится вне хранилища: {resolved_path} не входит в {abs_vault_root}")
        
    return resolved_path

async def deep_analyze_website(ctx: RunContext, url: str) -> str:
    """Глубокий анализ веб-сайта с рендерингом JavaScript."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            text = await page.evaluate("document.body.innerText")
            await browser.close()
            
            if not text:
                return "Не удалось извлечь текст страницы."
                
            return text[:15000] if len(text) > 15000 else text
    except Exception as e:
        return f"Ошибка при глубоком анализе сайта: {str(e)}"

def scan_vault_fast(ctx: RunContext[OrangeDeps], path: str) -> str:
    """Рекурсивный поиск .md файлов в хранилище Obsidian."""
    try:
        valid_path = validate_path(ctx.deps.obsidian_vault_path, path)
        return orange_core.scan_vault_fast(valid_path)
    except Exception as e:
        return f"Ошибка: {str(e)}"

def read_file_fast(ctx: RunContext[OrangeDeps], file_path: str) -> str:
    """Быстрое чтение содержимого файла с диска."""
    try:
        valid_path = validate_path(ctx.deps.obsidian_vault_path, file_path)
        return orange_core.read_file_fast(valid_path)
    except Exception as e:
        return f"Ошибка: {str(e)}"

def fetch_website_fast(url: str) -> str:
    """Загрузка HTML-кода веб-сайта для OSINT-анализа."""
    return orange_core.fetch_website_fast(url)

from core.file_ops import atomic_write_obsidian_note

async def rewrite_file(ctx: RunContext[OrangeDeps], file_path: str, content: str) -> str:
    """
    Безопасная и атомарная перезапись файла (особенно для заметок Obsidian).
    Использует временные файлы и механизм retry для обхода блокировок iCloud.
    """
    try:
        valid_path = validate_path(ctx.deps.obsidian_vault_path, file_path)
        await atomic_write_obsidian_note(valid_path, content)
        return "Успех: файл перезаписан"
    except Exception as e:
        return f"Ошибка: {str(e)}"

import aiofiles
from core.markdown_ops import append_task_to_markdown

async def add_task(ctx: RunContext, file_path: str, task: str) -> str:
    """
    Инструмент для точечного добавления новой задачи (чекбокса) в markdown-файл.
    Сохраняет структуру Obsidian.
    """
    try:
        # Жесткая защита: извлекаем только имя файла и принудительно кладем в папку текущего года
        file_name = os.path.basename(file_path)
        if not file_name.lower().endswith('.md'):
            file_name += '.md'
        current_year = str(datetime.date.today().year)
        safe_rel_path = os.path.join(current_year, file_name)
        obsidian_root = ctx.deps.obsidian_vault_path
        full_path = os.path.join(obsidian_root, safe_rel_path)
        full_path = os.path.normpath(full_path)
        
        print(f"[DEBUG add_task] Агент передал: {file_path} | Реально пишем в: {full_path}")
            
        # Убедимся, что родительские директории существуют
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
        # Чтение файла, если он существует, иначе создаем шаблон
        if os.path.exists(full_path):
            async with aiofiles.open(full_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
        else:
            content = "# Задачи\n\n"
            
        # Парсинг и модификация
        new_content = append_task_to_markdown(content, task)
        
        # Безопасное сохранение
        await atomic_write_obsidian_note(full_path, new_content)
        
        return "Успех: задача добавлена в файл"
    except Exception as e:
        return f"Ошибка при добавлении задачи: {str(e)}"

# --- ИНСТРУМЕНТЫ ПАМЯТИ ---

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СЕМАНТИЧЕСКОГО ПОИСКА ---

async def get_embedding(text: str, api_key: str) -> list:
    """Генерирует векторный эмбеддинг текста с использованием модели gemini-embedding-2"""
    import httpx
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent"
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
    results = db.search_messages(query)
    if not results:
        return f"Ничего не найдено в памяти по запросу '{query}'"
        
    snippets = []
    for r in results:
        snippets.append(f"[Чат: {r['title']}] {r['role'].upper()}: {r['content']}")
    all_text = "\n---\n".join(snippets)
    
    from core.agent import agent as root_agent, LITE_MODEL
    prompt = f"Пользователь ищет информацию по запросу '{query}'. Сделай краткую выжимку из этих сообщений:\n\n{all_text}"
    result = await root_agent.run(prompt, model=LITE_MODEL, deps=ctx.deps)
    return getattr(result, 'data', getattr(result, 'output', str(result)))

# --- ИНСТРУМЕНТЫ ПАМЯТИ ---

async def search_memory(ctx: RunContext, query: str) -> str:
    """
    Семантический поиск по базе данных (памяти) прошлых диалогов ИИ-ассистента с пользователем.
    Вычисляет сходство векторов через Gemini Embeddings API.
    """
    from core import db
    import json
    
    api_key = ctx.deps.settings.gemini_api_key
    if not api_key:
        print("[RAG WARNING] Отсутствует gemini_api_key, переключаюсь на LIKE-фоллбек.")
        return await _search_memory_like_fallback(ctx, query)
        
    try:
        query_vector = await get_embedding(query, api_key)
    except Exception as e:
        print(f"[RAG WARNING] Ошибка получения эмбеддинга запроса ({e}), переключаюсь на LIKE-фоллбек.")
        return await _search_memory_like_fallback(ctx, query)
        
    # Вытаскиваем все сообщения
    try:
        with db.get_connection() as conn:
            cursor = conn.execute(
                '''SELECT m.id, m.content, m.role, c.title 
                   FROM messages m 
                   JOIN chats c ON m.chat_id = c.id'''
            )
            messages = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[RAG Error] Ошибка чтения из БД: {e}")
        return f"Ошибка при обращении к базе данных: {e}"
        
    if not messages:
        return f"Ничего не найдено в памяти по запросу '{query}' (история пуста)."
        
    scored_messages = []
    for msg in messages:
        msg_id = msg["id"]
        content = msg["content"]
        # Игнорируем служебные сообщения
        if content.startswith("[Служебный системный контекст:"):
            continue
            
        emb_json = db.get_cached_embedding(msg_id)
        emb_vector = None
        if emb_json:
            try:
                emb_vector = json.loads(emb_json)
            except Exception:
                pass
                
        if not emb_vector:
            try:
                emb_vector = await get_embedding(content[:1000], api_key)
                db.save_cached_embedding(msg_id, json.dumps(emb_vector))
            except Exception as e:
                print(f"[RAG WARNING] Не удалось сгенерировать эмбеддинг для сообщения {msg_id}: {e}")
                continue
                
        similarity = cosine_similarity(query_vector, emb_vector)
        scored_messages.append((similarity, msg))
        
    # Сортируем по косинусному сходству
    scored_messages.sort(key=lambda x: x[0], reverse=True)
    
    # Отбираем топ-5 релевантных (сходство > 0.3)
    top_results = [item for item in scored_messages[:5] if item[0] > 0.3]
    if not top_results:
        return f"Семантически близких совпадений по запросу '{query}' не найдено."
        
    snippets = []
    for score, r in top_results:
        snippets.append(f"[Чат: {r['title']}] [Сходство: {score:.2f}] {r['role'].upper()}: {r['content']}")
        
    all_text = "\n---\n".join(snippets)
    
    from core.agent import agent as root_agent, LITE_MODEL
    prompt = f"Пользователь ищет информацию по запросу '{query}'. Сделай краткую выжимку из этих семантически близких сообщений:\n\n{all_text}"
    
    try:
        result = await root_agent.run(prompt, model=LITE_MODEL, deps=ctx.deps)
        return getattr(result, 'data', getattr(result, 'output', str(result)))
    except Exception as e:
        return f"Ошибка при суммаризации семантической памяти: {str(e)}"

async def export_active_chat(chat_id: str, deps) -> str:
    """Функция экспорта чата (вызывается напрямую из bridge.py, не как инструмент агента)"""
    from core import db
    from core.file_ops import atomic_write_obsidian_note
    import uuid
    
    history = db.get_chat_history(chat_id)
    if not history:
        return "Чат пуст."
        
    lines = []
    for msg in history:
        lines.append(f"**{msg['role'].upper()}**:\n{msg['content']}\n")
    full_chat = "\n".join(lines)
    
    from core.agent import agent as root_agent, HEAVY_MODEL
    prompt = (
        "Ты технический писатель. Скомпилируй из этого диалога сухую Markdown-статью. "
        "Выкинь воду, оставь решения, код и задачи.\n\n"
        f"ДИАЛОГ:\n{full_chat}"
    )
    
    result = await root_agent.run(prompt, model=HEAVY_MODEL, deps=deps)
    markdown_result = getattr(result, 'data', getattr(result, 'output', str(result)))
    
    filename = f"Export_{uuid.uuid4().hex[:8]}.md"
    obsidian_root = deps.obsidian_vault_path
    target_path = os.path.join(obsidian_root, "_Inbox", filename)
    
    await atomic_write_obsidian_note(target_path, markdown_result)
    return f"Успех! Чат экспортирован в {target_path}"

# --- ИНСТРУМЕНТЫ DEEP RESEARCH (OSINT) ---

async def fetch_url(ctx: RunContext, url: str) -> str:
    """
    Загружает веб-страницу по указанному URL, очищает её от HTML-тегов, скриптов и стилей,
    и возвращает чистый текстовый контент (лимит 12000 символов).
    """
    import httpx
    from bs4 import BeautifulSoup
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        print(f"[fetch_url] Загружаю страницу: {url}")
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
            
            # Парсинг и очистка HTML
            soup = BeautifulSoup(html, "html.parser")
            for script in soup(["script", "style", "head", "title", "meta", "[document]"]):
                script.extract()
                
            text = soup.get_text(separator="\n")
            # Нормализация пустых строк и пробелов
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            limit = 12000
            if len(clean_text) > limit:
                return clean_text[:limit] + "\n... [Контент обрезан]"
            return clean_text
    except Exception as e:
        return f"Ошибка при загрузке URL {url}: {str(e)}"

async def deep_research(ctx: RunContext, topic: str) -> str:
    """
    Выполняет итеративный поиск по теме с использованием DuckDuckGo, собирает ссылки,
    загружает контент 2-3 наиболее релевантных страниц и генерирует структурированный аналитический отчет.
    """
    from duckduckgo_search import DDGS
    
    print(f"[deep_research] Начинаю исследование: '{topic}'")
    
    # 1. Поиск ссылок через DuckDuckGo
    results = []
    try:
        with DDGS() as ddgs:
            ddg_results = list(ddgs.text(topic, max_results=8))
            for r in ddg_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
    except Exception as e:
        return f"Ошибка при обращении к поисковой системе DuckDuckGo: {str(e)}"
        
    if not results:
        return f"Поисковая система не вернула результатов по теме '{topic}'."
        
    # 2. Выбор 2-3 наиболее релевантных страниц
    urls_to_fetch = []
    for r in results:
        url = r["url"]
        if url and url not in urls_to_fetch:
            # Исключаем загрузку слишком тяжелых файлов (pdf и т.д.)
            if not url.lower().endswith(('.pdf', '.zip', '.tar.gz', '.tgz', '.exe', '.png', '.jpg', '.jpeg', '.gif')):
                urls_to_fetch.append(url)
        if len(urls_to_fetch) >= 3:
            break
            
    # 3. Скачивание содержимого страниц (fetch_url)
    fetched_contents = []
    for i, url in enumerate(urls_to_fetch):
        print(f"[deep_research] Страница {i+1}/{len(urls_to_fetch)}: {url}")
        content = await fetch_url(ctx, url)
        fetched_contents.append(f"=== ИСТОЧНИК {i+1}: {url} ===\n{content}\n")
        
    all_sources_text = "\n\n".join(fetched_contents)
    
    # 4. Анализ текста и синтез финального ответа через LLM
    from core.agent import agent as root_agent, LITE_MODEL
    prompt = (
        f"Ты — модуль OSINT Deep Research. Твоя задача — проанализировать сырые данные с веб-страниц "
        f"и составить исчерпывающий, структурированный, очищенный от воды отчет по теме: '{topic}'.\n\n"
        f"СЫРЫЕ ДАННЫЕ С РЕЛЕВАНТНЫХ САЙТОВ:\n"
        f"{all_sources_text}\n\n"
        f"ИНСТРУКЦИЯ:\n"
        f"1. Сделай подробный отчет, структурируя его по разделам.\n"
        f"2. Обязательно приводи точные ссылки на источники (URLs), которые были использованы.\n"
        f"3. Выделяй ключевые факты, даты и технические детали."
    )
    
    try:
        res = await root_agent.run(prompt, model=LITE_MODEL, deps=ctx.deps)
        report = getattr(res, 'data', getattr(res, 'output', str(res)))
        return report
    except Exception as e:
        return f"Ошибка при генерации отчета: {str(e)}\n\nСырые данные поисковой выдачи:\n" + "\n".join(f"- {r['title']}: {r['url']}" for r in results)

# --- ИНСТРУМЕНТ ЛОКАЛЬНОГО ВЫПОЛНЕНИЯ КОДА (SANDBOX) ---

async def execute_python(ctx: RunContext[OrangeDeps], code: str) -> str:
    """
    Запускает переданный Python-код в локальном процессе (subprocess) с таймаутом 10 секунд.
    Перехватывает stdout и stderr выполнения. Позволяет тестировать скрипты и производить вычисления.
    """
    if not ctx.deps.request_override:
        return "Ошибка: Выполнение Python-кода запрещено, так как callback одобрения не настроен."
        
    approved = await ctx.deps.request_override(code)
    if not approved:
        return "Ошибка: Выполнение Python-кода было отклонено пользователем."

    import sys
    import subprocess
    import tempfile
    import os
    import asyncio
    
    print(f"[execute_python] Получен запрос на запуск Python-кода (длина: {len(code)} символов)")
    
    try:
        # Записываем код во временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(code)
            temp_path = temp_file.name
            
        # Запускаем скрипт асинхронно через текущий интерпретатор python.exe
        process = await asyncio.create_subprocess_exec(
            sys.executable, temp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=10.0)
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            exit_code = process.returncode
            
            output_lines = [
                f"=== РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ (Код возврата: {exit_code}) ==="
            ]
            if stdout:
                output_lines.append(f"[STDOUT]\n{stdout}")
            if stderr:
                output_lines.append(f"[STDERR]\n{stderr}")
            if not stdout and not stderr:
                output_lines.append("[Процесс завершился без вывода]")
                
            return "\n\n".join(output_lines)
            
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return "Ошибка: Выполнение кода превысило таймаут в 10 секунд и было принудительно остановлено."
            
        finally:
            # Удаляем временный файл
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        return f"Критическая ошибка при запуске песочницы: {str(e)}"

# --- ИНСТРУМЕНТ СКАНИРОВАНИЯ ЗАМЕТОК (OBSIDIAN WIKILINKS) ---

async def list_existing_notes(ctx: RunContext) -> str:
    """
    Возвращает плоский список имен существующих заметок в хранилище Obsidian.
    Используется агентом, чтобы рекомендовать релевантные внутренние связи в формате [[Имя заметки]].
    """
    import glob
    import os
    
    try:
        # Рекурсивный поиск .md файлов
        obsidian_root = ctx.deps.obsidian_vault_path
        pattern = os.path.join(obsidian_root, "**", "*.md")
        files = glob.glob(pattern, recursive=True)
        
        notes = []
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            if name and not name.startswith("."):
                notes.append(name)
                
        if not notes:
            return "Заметки в Obsidian не обнаружены."
            
        unique_notes = sorted(list(set(notes)))
        
        # Ограничение контекстного окна
        if len(unique_notes) > 200:
            return "Существующие заметки в Obsidian (первые 200):\n" + "\n".join(unique_notes[:200]) + "\n... [Список обрезан]"
            
        return "Существующие заметки в Obsidian:\n" + "\n".join(unique_notes)
    except Exception as e:
        return f"Ошибка при получении списка заметок: {str(e)}"



