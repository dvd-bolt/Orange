import os
import re
import asyncio
from core import db
from core.markdown_ops import read_note_cli
from core.path_safety import VaultPathResolver
from core.services.write_preview_service import WritePreviewService, confirm_and_apply_plan

async def crystallize_skill(chat_id: str, deps, api_key: str):
    """
    Анализирует историю диалога после его завершения.
    Если найден полезный переиспользуемый алгоритм, сохраняет его как навык в _System/Skills/.
    """
    try:
        # Разрешаем vault_path и deps для тестирования и живого выполнения
        if isinstance(deps, str):
            vault_path = deps
            from core.dependencies import OrangeDeps
            from config.settings import Settings
            deps = OrangeDeps(
                obsidian_vault_path=vault_path,
                settings=Settings(),
                request_override=None,
                mcp_client=None
            )
            deps.settings.gemini_api_key = api_key
        else:
            vault_path = deps.obsidian_vault_path

        history = db.get_chat_history(chat_id)
        if not history or len(history) < 4:
            # Слишком короткий диалог для вычленения навыка
            return
            
        # Форматируем диалог
        lines = []
        for msg in history:
            lines.append(f"{msg['role'].upper()}: {msg['content']}")
        full_chat = "\n---\n".join(lines)
        if len(full_chat) > 40_000:
            full_chat = (
                "[Earlier chat context omitted because the skill context exceeded 40 KB.]\n\n"
                + full_chat[-40_000:]
            )
        
        # Вызываем Gemini для рефлексии и кристаллизации
        from core.agent import agent as root_agent, LITE_MODEL
        prompt = (
            "Ты — аналитический модуль рефлексии ассистента Orange OS.\n"
            "Проанализируй этот диалог. Если в нем есть полезный, повторяемый алгоритм, навык или инструкция "
            "(например, как парсить конкретный тип сайта, писать SQL-запрос для нашей структуры, "
            "настраивать какой-то инструмент, патчить определенный вид багов), кристаллизуй его в переиспользуемый навык (Skill).\n\n"
            "Правила оформления навыка:\n"
            "1. Верни Markdown-документ с заголовком первого уровня `# Навык: [Короткое понятное название]`.\n"
            "2. Добавь разделы: 'Описание', 'Когда применять', 'Пошаговый алгоритм (шаблоны, код)', 'Типичные ошибки'.\n"
            "3. Пиши кратко, емко, на русском языке.\n"
            "4. Если в диалоге нет переиспользуемого паттерна (простой вопрос-ответ, флуд, обсуждение личных тем), верни ТОЛЬКО одно слово: NONE.\n\n"
            f"ДИАЛОГ:\n{full_chat}"
        )
        
        res = await asyncio.wait_for(
            root_agent.run(
                prompt,
                model=LITE_MODEL,
                deps=deps,
                model_settings={"timeout": 60.0},
            ),
            timeout=70.0,
        )
        skill_md = getattr(res, 'data', getattr(res, 'output', str(res))).strip()
        
        if skill_md.upper() == "NONE" or "NONE" in skill_md[:10]:
            print("[Skills] Рефлексия завершена: повторяемый навык не обнаружен.")
            return
            
        # Извлекаем заголовок для имени файла
        title_match = re.search(r"^#\s*Навык:\s*(.*?)$", skill_md, re.MULTILINE)
        if title_match:
            raw_title = title_match.group(1).strip()
            # Санируем имя файла
            filename = "".join(c for c in raw_title if c.isalnum() or c in " _-").strip()
            filename = filename.replace(" ", "_") + ".md"
        else:
            filename = f"Skill_{chat_id[:8]}.md"
            
        filepath = os.path.join(vault_path, "_System", "Skills", filename)
        preview = WritePreviewService(vault_path)
        plan = preview.build_plan(filepath, skill_md, action="crystallize_skill")
        approved = await confirm_and_apply_plan(
            deps,
            plan,
            "skill_crystallization",
            f"Crystallize skill {plan['relative_path']}",
        )
        if not approved:
            print("[Skills] Кристаллизация навыка отклонена или недоступна без approval callback.")
            return
        print(f"[Skills] Успешно кристаллизован новый навык: {filepath}")
        
    except Exception as e:
        print(f"[Skills Error] Skill crystallization failed: {type(e).__name__}")

async def load_relevant_skills(deps, user_prompt: str, api_key: str) -> str:
    """
    Сканирует доступные навыки в _System/Skills/ и загружает наиболее релевантные в контекст.
    """
    try:
        if isinstance(deps, str):
            vault_path = deps
            from core.dependencies import OrangeDeps
            from config.settings import Settings
            deps = OrangeDeps(
                obsidian_vault_path=vault_path,
                settings=Settings(),
                request_override=None,
                mcp_client=None
            )
            deps.settings.gemini_api_key = api_key
        else:
            vault_path = deps.obsidian_vault_path

        resolver = VaultPathResolver(vault_path)
        try:
            skills_dir = resolver.resolve("_System/Skills")
        except ValueError:
            return ""
        if not skills_dir.is_dir():
            return ""
            
        skill_files = [
            path
            for path in resolver.iter_notes()
            if path.parent == skills_dir
        ][:100]
        if not skill_files:
            return ""
            
        # Составляем список доступных навыков
        skills_info = []
        for filepath in skill_files:
            filename = filepath.name
            # Читаем первую строку (заголовок)
            try:
                with filepath.open("r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                title = first_line.replace("# Навык:", "").replace("#", "").strip()
                skills_info.append({"file": filename, "title": title})
            except Exception:
                pass
                
        if not skills_info:
            return ""
            
        # Спрашиваем модель, какие навыки подходят
        skills_list_str = "\n".join([f"- {s['file']}: {s['title']}" for s in skills_info])
        
        from core.agent import agent as root_agent, LITE_MODEL
        prompt = (
            "У нас есть библиотека доступных навыков (skills) для решения задач:\n"
            f"{skills_list_str}\n\n"
            f"Запрос пользователя: '{user_prompt}'\n\n"
            "Какие из этих файлов навыков непосредственно применимы для выполнения этого запроса?\n"
            "Верни список имен файлов через запятую (например: Git_Backup.md, Web_Scrape.md), либо слово 'none' если ничего не подходит.\n"
            "Не пиши никаких объяснений и вводных слов."
        )
        
        res = await asyncio.wait_for(
            root_agent.run(
                prompt,
                model=LITE_MODEL,
                deps=deps,
                model_settings={"timeout": 30.0},
            ),
            timeout=40.0,
        )
        answer = getattr(res, 'data', getattr(res, 'output', str(res))).strip().lower()
        
        if "none" in answer:
            return ""
            
        selected_files = [f.strip() for f in answer.split(",") if f.strip()][:3]
        
        injected_skills = []
        for sel_file in selected_files:
            # Убеждаемся, что файл существует
            matching_file = None
            for s in skills_info:
                if s["file"].lower() == sel_file.lower() or s["file"].lower().replace(".md", "") == sel_file.lower().replace(".md", ""):
                    matching_file = s["file"]
                    break
                    
            if matching_file:
                full_path = resolver.resolve_note(skills_dir / matching_file, must_exist=True)
                try:
                    content = await read_note_cli(
                        resolver.relative(full_path),
                        vault_path=vault_path,
                    )
                    injected_skills.append(
                        f"=== RELEVANT SKILL ({matching_file}) ===\n{content[:12_000]}"
                    )
                    print(f"[Skills] Динамически загружен навык: {matching_file}")
                except Exception as ex:
                    print(f"[Skills Error] Не удалось прочитать файл навыка {matching_file}: {ex}")
                    
        if injected_skills:
            return "\n\nРЕКОМЕНДОВАННЫЕ НАВЫКИ ДЛЯ ВЫПОЛНЕНИЯ ЗАДАЧИ:\n" + "\n\n".join(injected_skills) + "\n\n"
        return ""
        
    except Exception as e:
        print(f"[Skills Error] Relevant skill loading failed: {type(e).__name__}")
        return ""
