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
