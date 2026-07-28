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
import re
import shutil
from pathlib import PurePosixPath
from typing import List

_obsidian_cli_lock = None

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
    """Runs Obsidian CLI without invoking a shell."""
    global _obsidian_cli_lock
    if _obsidian_cli_lock is None:
        _obsidian_cli_lock = asyncio.Lock()
    async with _obsidian_cli_lock:
        cmd = ["obsidian", *[str(arg).replace("\\", "/") for arg in args]]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            except asyncio.CancelledError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                raise
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise RuntimeError("Obsidian CLI execution timed out after 15 seconds")
            
            # Anti-Wedge Delay: 60ms
            await asyncio.sleep(0.06)
            
            if proc.returncode != 0:
                err_msg = decode_bytes(stderr).strip()
                raise RuntimeError(f"Obsidian CLI failed: {err_msg}")
                
            decoded = decode_bytes(stdout)
            if len(decoded) > 1_000_000:
                return decoded[:1_000_000] + "\n...[CLI output truncated]"
            return decoded
        except FileNotFoundError as exc:
            raise RuntimeError("Obsidian CLI is not installed or is not available in PATH.") from exc
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to run Obsidian CLI: {exc}") from exc

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
    normalized = path_clean.replace("\\", "/")
    path_parts = PurePosixPath(normalized).parts
    if (
        "\0" in normalized
        or normalized.startswith(("/", "~"))
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in path_parts
    ):
        return False

    # Rule 1 – extension whitelist
    path_lower = normalized.lower()
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


async def search_notes_cli(query: str, vault_path: str | None = None) -> List[str]:
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
    cli_failed = False

    async def _execute_search(q: str) -> List[str]:
        nonlocal cli_failed
        try:
            output = await run_obsidian_cli(["search", f"query={q}", "format=json"])
            cleaned = output.strip()
            if not cleaned:
                return []

            # --- Parse raw output ------------------------------------------------
            raw_paths: list[str] = []

            # Try parsing as JSON list first
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            raw_paths.append(item)
                        elif isinstance(item, dict):
                            value = item.get("path") or item.get("file") or item.get("name")
                            if value:
                                raw_paths.append(str(value))
                elif isinstance(parsed, dict):
                    for item in parsed.get("results", []):
                        if isinstance(item, str):
                            raw_paths.append(item)
                        elif isinstance(item, dict):
                            value = item.get("path") or item.get("file") or item.get("name")
                            if value:
                                raw_paths.append(str(value))
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
            if vault_path:
                from core.path_safety import VaultPathResolver

                resolver = VaultPathResolver(vault_path)
                validated = []
                for path in safe_paths:
                    try:
                        validated.append(resolver.relative(resolver.resolve_note(path, must_exist=True)))
                    except ValueError:
                        continue
                return validated
            return safe_paths
        except Exception as e:
            cli_failed = True
            print(f"[Obsidian CLI Search Error] {type(e).__name__}")
            return []

    if shutil.which("obsidian") is None:
        cli_failed = True

    # 1. First attempt: standard text search
    results = [] if cli_failed else await _execute_search(query)

    # 2. Fallback attempt: filename search if no results found
    if not results and not cli_failed:
        results = await _execute_search(f"file:{query}")

    if not results and vault_path:
        from core.hybrid_search import local_search_vault

        return local_search_vault(query, vault_path)

    if not results:
        print("[ERROR] Заметка не найдена в индексах хранилища")
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

    if vault_path:
        from core.path_safety import VaultPathResolver

        try:
            resolver = VaultPathResolver(vault_path)
            resolved = resolver.resolve_note(sanitized, must_exist=True)
            return await asyncio.to_thread(
                resolver.read_note_text,
                resolved,
                max_chars=100_000,
            )
        except ValueError as exc:
            return f"[ERROR] {exc}"

    try:
        output = await run_obsidian_cli(["read", f"path={sanitized}"])
        return output
    except Exception as e:
        return f"[PROVIDER_ERROR] Obsidian CLI read failed: {type(e).__name__}"
