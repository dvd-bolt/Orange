PROFILES = {
    "base": (
        "You are Orange, a highly efficient local AI assistant.\n"
        "Your task is to provide clear, factual, and direct answers to any user questions. "
        "You have access to the conversation history and memory search tools (search_memory).\n"
        "RULES:\n"
        "1. Respond concisely, without unnecessary politeness or fluff.\n"
        "2. Focus strictly on facts.\n"
        "3. Respond in the language used by the user unless they explicitly request another language."
    ),
    "deep_research": (
        "You are Orange in Deep Research mode (OSINT Machine).\n"
        "Your main goal is to conduct deep information gathering and synthesis from the external web.\n"
        "RULES:\n"
        "1. Use the real web sources supplied in the request context before making claims.\n"
        "2. If a source is unavailable, say so instead of inventing its contents.\n"
        "3. Structure reports: highlight sections, list of sources with exact links, key dates, and numbers.\n"
        "4. Always verify facts and provide a balanced analytical synthesis.\n"
        "5. Respond in the language used by the user unless they explicitly request another language."
    ),
    "coder": (
        "You are Orange in Coder mode (Restricted Python Executor).\n"
        "Your goal is to write clean, reviewable code.\n"
        "RULES:\n"
        "1. Never claim that code was executed unless actual execution output is present in the prompt.\n"
        "2. Python blocks are executed only through the user's Execute button and approval dialog.\n"
        "3. Return working code with concise comments and state what remains unverified.\n"
        "4. Respond in the language used by the user unless they explicitly request another language."
    ),
    "project_manager": (
        "You are Orange in Project Manager mode.\n"
        "Your goal is to route explicit tasks into the user's real Obsidian vault.\n"
        "RULES:\n"
        "1. Use `list_existing_notes` before choosing a destination; never rely on a hardcoded project map.\n"
        "2. Choose an exact vault-relative note path only when its title or content clearly matches the task.\n"
        "3. Use `add_task` for the write. Every write must pass the user's approval gate.\n"
        "4. When no destination is a clear match, ask the user where to place the task instead of inventing a note.\n"
        "5. If approval is denied, report what was proposed and do not claim the file changed.\n"
        "6. Respond in the language used by the user unless they explicitly request another language."
    )
}

import os
from pathlib import Path
from core.path_safety import VaultPathResolver

def buildSessionContext(vault_path: str, current_note_path: str = None) -> str:
    """
    Выполняет Walk-up сканирование каталогов от текущей заметки до корня хранилища.
    Собирает контент локальных файлов SYSTEM.md и инструкций папок внутри текущего vault.
    """
    resolver = VaultPathResolver(vault_path)
    vault_path = str(resolver.root)
    
    # 1. Определение начального пути сканирования
    start_dir = vault_path
    if current_note_path:
        try:
            abs_note_path = resolver.resolve(current_note_path, must_exist=True)
            if abs_note_path.is_file():
                start_dir = str(abs_note_path.parent)
            elif abs_note_path.is_dir():
                start_dir = str(abs_note_path)
        except ValueError:
            start_dir = vault_path
            
    # 2. Поднимаемся вверх по иерархии папок до корня vault_path
    collected_systems = []
    curr_dir = os.path.abspath(start_dir)
    
    while True:
        try:
            system_file = resolver.resolve_note(Path(curr_dir) / "SYSTEM.md")
        except ValueError:
            system_file = None
        if system_file and system_file.is_file():
            try:
                with system_file.open('r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(12_000).strip()
                if content:
                    collected_systems.append(f"### Спецификация каталога {os.path.basename(curr_dir) or '/'}:\n{content}")
            except Exception as e:
                import sys
                print(f"[buildSessionContext Error] Failed to read {system_file}: {e}", file=sys.stderr)
                
        if curr_dir == vault_path:
            break
            
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir or not resolver.is_inside(parent):
            break
        curr_dir = parent

    collected_systems.reverse()
    
    # 3. Принудительно дописываем APPEND_SYSTEM.md
    try:
        append_file = resolver.resolve_note("APPEND_SYSTEM.md")
    except ValueError:
        append_file = None
    if append_file and append_file.is_file():
        try:
            with append_file.open('r', encoding='utf-8', errors='ignore') as f:
                content = f.read(12_000).strip()
            if content:
                collected_systems.append(f"### APPEND_SYSTEM (Глобальные правила защиты):\n{content}")
        except Exception as e:
            import sys
            print(f"[buildSessionContext Error] Failed to read {append_file}: {e}", file=sys.stderr)
            
    return "\n\n".join(collected_systems)


def buildIdentityContext(vault_path: str) -> str:
    """
    Загружает автономный профиль личности и памяти из папки _System/:
    - Identity.md (SOUL/системный характер)
    - USER.md (профиль пользователя, до 1375 символов)
    - MEMORY.md (активные проекты/память, до 2200 символов)
    Если папка или файлы отсутствуют, ничего не создает и возвращает пустой контекст.
    """
    resolver = VaultPathResolver(vault_path)
    vault_path = str(resolver.root)
    try:
        system_dir = resolver.resolve("_System")
    except ValueError:
        return ""
    
    if not system_dir.is_dir():
        return ""
            
    def safe_system_note(filename: str):
        try:
            path = resolver.resolve_note(system_dir / filename)
        except ValueError:
            return None
        return path if path.is_file() else None

    identity_file = safe_system_note("Identity.md")
    user_file = safe_system_note("USER.md")
    memory_file = safe_system_note("MEMORY.md")
    
    parts = []
    
    # 1. Identity
    if identity_file:
        try:
            with identity_file.open('r', encoding='utf-8', errors='ignore') as f:
                content = f.read(4_000).strip()
            if content:
                parts.append(f"=== IDENTITY (SOUL.md) ===\n{content}")
        except Exception:
            pass
            
    # 2. USER.md
    if user_file:
        try:
            with user_file.open('r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1_376).strip()
            if content:
                # Limit to 1375 chars
                user_content = content[:1375]
                parts.append(f"=== USER PROFILE (USER.md) ===\n{user_content}")
        except Exception:
            pass
            
    # 3. MEMORY.md
    if memory_file:
        try:
            with memory_file.open('r', encoding='utf-8', errors='ignore') as f:
                content = f.read(2_201).strip()
            if content:
                # Limit to 2200 chars
                memory_content = content[:2200]
                parts.append(f"=== PERSISTENT MEMORY (MEMORY.md) ===\n{memory_content}")
        except Exception:
            pass
            
    if parts:
        return "\n\n" + "\n\n".join(parts) + "\n\n"
    return ""
