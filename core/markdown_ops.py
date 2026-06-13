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

async def search_notes_cli(query: str) -> List[str]:
    """
    Search notes using Obsidian CLI: obsidian search query="{query}" format=json
    Returns a list of note paths.
    """
    try:
        output = await run_obsidian_cli(["search", f"query={query}", "format=json"])
        cleaned = output.strip()
        if not cleaned:
            return []
        
        # Try parsing as JSON list first
        try:
            paths = json.loads(cleaned)
            if isinstance(paths, list):
                return paths
        except json.JSONDecodeError:
            pass
            
        # Fallback: parse as line-by-line relative path listings
        paths = [line.strip() for line in cleaned.splitlines() if line.strip()]
        return paths
    except Exception as e:
        print(f"[Obsidian CLI Search Error] {e}")
        return []

async def read_note_cli(path: str) -> str:
    """
    Read note using Obsidian CLI: obsidian read path="{path}"
    """
    try:
        output = await run_obsidian_cli(["read", f"path={path}"])
        return output
    except Exception as e:
        return f"Error reading note via Obsidian CLI: {str(e)}"
