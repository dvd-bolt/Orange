import mistletoe
from mistletoe.block_token import Heading, List

def append_task_to_markdown(markdown_text: str, task_text: str) -> str:
    """
    Безопасное добавление задачи в markdown-файл.
    Использует AST (mistletoe) для поиска логических блоков, но реконструирует
    результат на основе оригинальных строк, чтобы гарантировать 100% сохранность
    специфичного синтаксиса Obsidian (YAML frontmatter, WikiLinks, Callouts).
    """
    # 1. Программный парсинг текста в AST-дерево
    doc = mistletoe.Document(markdown_text)
    
    target_heading_line = -1
    list_start_line = -1
    next_block_line = -1
    
    in_target_section = False
    lines = markdown_text.split('\n')
    
    # 2-3. Поиск раздела "Backlog" / "Задачи" и списка внутри него
    for child in doc.children:
        current_line = getattr(child, 'line_number', -1)
        if current_line == -1:
            continue
            
        if isinstance(child, Heading):
            # Проверяем заголовок по исходной строке, чтобы избежать багов с UTF-8 в AST
            header_text = lines[current_line - 1].lower()
            if "backlog" in header_text or "задачи" in header_text:
                in_target_section = True
                target_heading_line = current_line
                continue
            elif in_target_section:
                # Начался следующий заголовок — секция закрыта
                next_block_line = current_line
                break
                
        if in_target_section and isinstance(child, List):
            list_start_line = current_line
            
        elif in_target_section and list_start_line != -1 and current_line > list_start_line:
            # Первый блок после списка внутри целевой секции
            next_block_line = current_line
            break

    # 4. Добавление задачи (Рендеринг результата)
    if list_start_line != -1:
        # Вставляем в конец существующего списка
        insert_line = next_block_line - 1 if next_block_line != -1 else len(lines)
        
        # Отступаем от пустых строк в конце файла/блока
        while insert_line > list_start_line and not lines[insert_line - 1].strip():
            insert_line -= 1
            
        lines.insert(insert_line, f"- [ ] {task_text}")
        
    elif target_heading_line != -1:
        # Заголовок есть, но списка нет — создаем список сразу под ним
        lines.insert(target_heading_line, f"- [ ] {task_text}")
        
    else:
        # 5. Заголовка нет — безопасно добавляем в конец документа
        # Убедимся, что перед новым заголовком есть пустая строка
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append("## Задачи")
        lines.append(f"- [ ] {task_text}")
        
    return "\n".join(lines)

import asyncio
import subprocess
import json
from typing import List

_obsidian_cli_lock = asyncio.Lock()

def decode_bytes(data: bytes) -> str:
    """Safely decodes bytes to string trying utf-8, cp1251, cp866."""
    if not data:
        return ""
    for enc in ['utf-8', 'cp1251', 'cp866']:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')

async def run_obsidian_cli(args: List[str]) -> str:
    """Runs obsidian CLI command with Anti-Wedge Delay protection."""
    async with _obsidian_cli_lock:
        try:
            cmd = ["obsidian"] + args
            cmd = [arg.replace("\\", "/") for arg in cmd]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            # Anti-Wedge Delay: 60ms
            await asyncio.sleep(0.06)
            
            if proc.returncode != 0:
                err_msg = decode_bytes(stderr).strip()
                raise RuntimeError(f"Obsidian CLI failed: {err_msg}")
                
            return decode_bytes(stdout)
        except Exception as e:
            try:
                cmd_args = [arg.replace("\\", "/") for arg in (["obsidian"] + args)]
                cmd_str = " ".join([f'"{arg}"' for arg in cmd_args])
                proc = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                await asyncio.sleep(0.06)
                if proc.returncode != 0:
                    err_msg = decode_bytes(stderr).strip()
                    raise RuntimeError(f"Obsidian CLI failed: {err_msg}")
                return decode_bytes(stdout)
            except Exception as ex:
                raise RuntimeError(f"Failed to run obsidian CLI: {ex}")

# ---------------------------------------------------------------------------
# Path Sanitization Constants
# ---------------------------------------------------------------------------
# Only these file extensions are allowed through from Obsidian CLI results.
ALLOWED_EXTENSIONS = ('.md', '.canvas')

# Any path containing one of these substrings is unconditionally blocked.
# This prevents Electron internals, caches, binaries and system artefacts
# from leaking into the cognitive layer and causing infinite FSM loops.
BLOCKED_SUBSTRINGS = (
    '.asar',
    'node_modules',
    '.git',
    'AppData',
    'Local/Temp',
    'Local\\Temp',
    'download',
    '.dll',
    '.exe',
    '.log',
    '__pycache__',
    '.electron',
    'Cache',
    'GPUCache',
    'Code Cache',
)


def _is_safe_note_path(path: str) -> bool:
    """
    Returns True only if *path* looks like a legitimate Obsidian note.

    Rules applied (in order):
      1. Must end with one of ALLOWED_EXTENSIONS (.md / .canvas).
      2. Must NOT contain any of the BLOCKED_SUBSTRINGS.
    """
    if not path or not isinstance(path, str):
        return False

    path_clean = path.strip()
    if not path_clean:
        return False

    # Rule 1 – extension whitelist
    path_lower = path_clean.lower()
    if not path_lower.endswith(ALLOWED_EXTENSIONS):
        return False

    # Rule 2 – blocked-substring blacklist (case-insensitive)
    for blocked in BLOCKED_SUBSTRINGS:
        if blocked.lower() in path_lower:
            return False

    return True


def _sanitize_path_for_cli(raw_path: str) -> str:
    """
    Normalise a path before passing it to ``obsidian read``.

    * Strips leading/trailing whitespace.
    * Converts back-slashes → forward-slashes (Obsidian CLI expects POSIX
      separators even on Windows).
    * Removes a leading ``./`` if present.
    """
    p = raw_path.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p


async def search_notes_cli(query: str) -> List[str]:
    """
    Search notes using Obsidian CLI: obsidian search query="{query}" format=json

    Returns a **filtered** list of note paths.  Every returned path is
    guaranteed to:
      • end with .md or .canvas,
      • contain none of the blocked substrings (Electron binaries, caches …).

    If no valid paths survive filtering, returns an empty list and prints
    a structured "[ERROR] Заметка не найдена в индексах хранилища" message
    so that callers receive a clean signal instead of garbage.
    """
    async def _execute_search(q: str) -> List[str]:
        try:
            output = await run_obsidian_cli(["search", f"query={q}", "format=json"])
            cleaned = output.strip()
            if not cleaned:
                return []

            # --- Parse raw output ------------------------------------------------
            raw_paths: list = []

            # Try parsing as JSON list first
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    raw_paths = [str(p) for p in parsed]
                elif isinstance(parsed, dict):
                    # Some CLI versions return {"results": [...]}
                    raw_paths = [str(p) for p in parsed.get("results", [])]
            except json.JSONDecodeError:
                pass

            # Fallback: parse as line-by-line relative path listings
            if not raw_paths:
                raw_paths = [line.strip() for line in cleaned.splitlines() if line.strip()]

            # --- Sanitize --------------------------------------------------------
            safe_paths = [
                _sanitize_path_for_cli(p)
                for p in raw_paths
                if _is_safe_note_path(p)
            ]
            return safe_paths
        except Exception as e:
            print(f"[Obsidian CLI Search Error] {e}")
            return []

    # 1. First attempt: standard text search
    results = await _execute_search(query)

    # 2. Fallback attempt: filename search if no results found
    if not results:
        results = await _execute_search(f"file:{query}")

    if not results:
        print("[ERROR] Заметка не найдена в индексах хранилища")
        return []

    return results


async def read_note_cli(path: str, vault_path: str | None = None) -> str:
    """
    Read note using Obsidian CLI: obsidian read path="{path}"

    Safety guarantees:
      • The path is validated through ``_is_safe_note_path`` before the
        subprocess is spawned.
      • If *vault_path* is provided the physical existence of the file is
        verified on disk beforehand, avoiding pointless (and potentially
        dangerous) CLI invocations for non-existent files.
    """
    sanitized = _sanitize_path_for_cli(path)

    # Validate the path is a legitimate note
    if not _is_safe_note_path(sanitized):
        return (
            f"[ERROR] Путь отклонён фильтром безопасности: {sanitized!r}. "
            "Разрешены только файлы .md / .canvas без запрещённых подстрок."
        )

    # Physical existence check (when vault root is known)
    if vault_path:
        import os
        abs_path = os.path.join(vault_path, sanitized)
        abs_path = os.path.normpath(abs_path)
        if not os.path.isfile(abs_path):
            return f"[ERROR] Файл не найден на диске: {sanitized}"

    try:
        output = await run_obsidian_cli(["read", f"path={sanitized}"])
        return output
    except Exception as e:
        return f"Error reading note via Obsidian CLI: {str(e)}"
