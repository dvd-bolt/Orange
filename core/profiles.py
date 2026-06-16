PROFILES = {
    "base": (
        "You are Orange, a highly efficient local AI assistant.\n"
        "Your task is to provide clear, factual, and direct answers to any user questions. "
        "You have access to the conversation history and memory search tools (search_memory).\n"
        "RULES:\n"
        "1. Respond concisely, without unnecessary politeness or fluff.\n"
        "2. Focus strictly on facts.\n"
        "3. Always respond in English unless the user explicitly requests another language."
    ),
    "deep_research": (
        "You are Orange in Deep Research mode (OSINT Machine).\n"
        "Your main goal is to conduct deep information gathering and synthesis from the external web.\n"
        "RULES:\n"
        "1. Actively use the `deep_research` tool to search and analyze information based on user query.\n"
        "2. If you need to load a specific page, use `fetch_url`.\n"
        "3. Structure reports: highlight sections, list of sources with exact links, key dates, and numbers.\n"
        "4. Always verify facts and provide a balanced analytical synthesis.\n"
        "5. Always respond in English unless the user explicitly requests another language."
    ),
    "coder": (
        "You are Orange in Coder mode (Local Python Sandbox).\n"
        "Your goal is to write clean code and run it in a local sandbox environment.\n"
        "RULES:\n"
        "1. For complex calculations, algorithm verification, or data analysis, write Python scripts and ALWAYS run them using the `execute_python` tool.\n"
        "2. Run the code yourself first, inspect the output (stdout/stderr), fix errors, and only then present the final solution to the user.\n"
        "3. Return working code with comments and an explanation of its execution results.\n"
        "4. Always respond in English unless the user explicitly requests another language."
    ),
    "project_manager": (
        "YOU ARE AN AUTOMATED ROUTING ROBOT WITH NO VOICE.\n"
        "Your ONLY goal is to invoke the `add_task` tool.\n"
        "FORBIDDEN: writing text responses, lists, reasoning, apologies, or questions.\n"
        "FORBIDDEN: complaining about missing files.\n"
        "MANDATORY MAP (use strictly as listed):\n"
        "- VPN -> 2026/VPN.md\n"
        "- DS Digital (scripts, agency) -> 2026/DS Digital.md\n"
        "- Chess -> 2026/Chess.md\n"
        "- Term papers (statistics, studies) -> 2026/Term_papers.md\n\n"
        "ALGORITHM:\n"
        "1. Read the text.\n"
        "2. SILENTLY invoke `add_task` for each identified task with paths from the map.\n"
        "Any text response without a tool call is a critical system failure."
    )
}

import os

def buildSessionContext(vault_path: str, current_note_path: str = None) -> str:
    """
    Выполняет Walk-up сканирование каталогов от текущей заметки до корня хранилища.
    Собирает контент локальных файлов SYSTEM.md и инструкций папок.
    В самом конце принудительно дописывает глобальный файл защиты test_vault/APPEND_SYSTEM.md.
    """
    vault_path = os.path.abspath(vault_path)
    
    # 1. Определение начального пути сканирования
    start_dir = vault_path
    if current_note_path:
        if not os.path.isabs(current_note_path):
            abs_note_path = os.path.abspath(os.path.join(vault_path, current_note_path))
        else:
            abs_note_path = os.path.abspath(current_note_path)
            
        if os.path.isfile(abs_note_path):
            start_dir = os.path.dirname(abs_note_path)
        elif os.path.isdir(abs_note_path):
            start_dir = abs_note_path
            
    # 2. Поднимаемся вверх по иерархии папок до корня vault_path
    collected_systems = []
    curr_dir = os.path.abspath(start_dir)
    
    while True:
        system_file = os.path.join(curr_dir, "SYSTEM.md")
        if os.path.isfile(system_file):
            try:
                with open(system_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                if content:
                    collected_systems.append(f"### Спецификация каталога {os.path.basename(curr_dir) or '/'}:\n{content}")
            except Exception as e:
                import sys
                print(f"[buildSessionContext Error] Failed to read {system_file}: {e}", file=sys.stderr)
                
        if curr_dir == vault_path:
            break
            
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent

    collected_systems.reverse()
    
    # 3. Принудительно дописываем APPEND_SYSTEM.md
    append_file = os.path.join(vault_path, "APPEND_SYSTEM.md")
    if os.path.isfile(append_file):
        try:
            with open(append_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
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
    Если папка или файлы отсутствуют, создает шаблоны по умолчанию.
    """
    vault_path = os.path.abspath(vault_path)
    system_dir = os.path.join(vault_path, "_System")
    
    # Автосоздание папки и дефолтных шаблонов, если их нет
    if not os.path.exists(system_dir):
        try:
            os.makedirs(system_dir, exist_ok=True)
            
            # Дефолтный Identity.md
            with open(os.path.join(system_dir, "Identity.md"), "w", encoding="utf-8") as f:
                f.write(
                    "# Личность и характер ассистента Orange\n\n"
                    "Вы — высокоэффективный локальный ИИ-ассистент Orange. Вы общаетесь кратко, по делу, "
                    "без лишней вежливости и \"воды\". Ваша цель — экономить время пользователя и решать задачи точно.\n"
                )
            # Дефолтный USER.md
            with open(os.path.join(system_dir, "USER.md"), "w", encoding="utf-8") as f:
                f.write(
                    "# Профиль пользователя\n\n"
                    "Имя: Пользователь\n"
                    "Стек технологий: Python, JavaScript, PyQt, SQLite, HTML\n"
                    "Предпочтения: Краткие ответы, готовый рабочий код с комментариями, оформление в стиле Markdown.\n"
                )
            # Дефолтный MEMORY.md
            with open(os.path.join(system_dir, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(
                    "# Активная память и проекты\n\n"
                    "Текущий проект: Обновление Orange OS до версии «Джарвис».\n"
                    "Направления работы: Внедрение FTS5 поиска по сообщениям, кристаллизация навыков (Skill Crystallization) и точечный патчинг файлов.\n"
                )
            print(f"[Identity] Создана папка _System с шаблонами по умолчанию: {system_dir}")
        except Exception as e:
            print(f"[Identity Error] Не удалось создать шаблоны по умолчанию: {e}")
            return ""
            
    identity_file = os.path.join(system_dir, "Identity.md")
    user_file = os.path.join(system_dir, "USER.md")
    memory_file = os.path.join(system_dir, "MEMORY.md")
    
    parts = []
    
    # 1. Identity
    if os.path.isfile(identity_file):
        try:
            with open(identity_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            if content:
                parts.append(f"=== IDENTITY (SOUL.md) ===\n{content}")
        except Exception:
            pass
            
    # 2. USER.md
    if os.path.isfile(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            if content:
                # Limit to 1375 chars
                user_content = content[:1375]
                parts.append(f"=== USER PROFILE (USER.md) ===\n{user_content}")
        except Exception:
            pass
            
    # 3. MEMORY.md
    if os.path.isfile(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            if content:
                # Limit to 2200 chars
                memory_content = content[:2200]
                parts.append(f"=== PERSISTENT MEMORY (MEMORY.md) ===\n{memory_content}")
        except Exception:
            pass
            
    if parts:
        return "\n\n" + "\n\n".join(parts) + "\n\n"
    return ""


