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

# --- Фича: BM25/Ключевой поиск по Obsidian Vault ---
import os
import re
import math
from typing import List, Dict, Tuple

def tokenize(text: str) -> List[str]:
    """Simple lowercase word tokenizer"""
    return re.findall(r'\w+', text.lower())

def search_relevant_files(vault_path: str, query: str, limit: int = 5) -> List[str]:
    """
    Performs BM25 keyword search over all markdown files in vault_path.
    Returns absolute paths of the most relevant markdown files.
    """
    if not vault_path or not os.path.exists(vault_path):
        return []

    # 1. Collect all markdown files, skipping hidden directories
    md_files = []
    for root, dirs, files in os.walk(vault_path):
        # Ignore dot folders (e.g. .obsidian, .orange)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.lower().endswith('.md'):
                md_files.append(os.path.join(root, f))

    if not md_files:
        return []

    # 2. Build frequency statistics
    doc_words: Dict[str, List[str]] = {}
    doc_lengths: Dict[str, int] = {}
    doc_term_freqs: Dict[str, Dict[str, int]] = {}
    term_doc_count: Dict[str, int] = {}  # How many docs contain the term
    
    total_len = 0
    for filepath in md_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            words = tokenize(text)
            doc_words[filepath] = words
            doc_lengths[filepath] = len(words)
            total_len += len(words)
            
            # Term frequencies
            tf: Dict[str, int] = {}
            for w in words:
                tf[w] = tf.get(w, 0) + 1
            doc_term_freqs[filepath] = tf
            
            # Document frequency
            for w in tf:
                term_doc_count[w] = term_doc_count.get(w, 0) + 1
        except Exception as e:
            print(f"[Indexer] Error reading file {filepath} for index: {e}")

    N = len(doc_words)
    if N == 0:
        return []
        
    avg_doc_len = total_len / N
    query_terms = tokenize(query)
    
    # BM25 Parameters
    k1 = 1.5
    b = 0.75
    
    scores: Dict[str, float] = {}
    for filepath in md_files:
        if filepath not in doc_term_freqs:
            continue
            
        score = 0.0
        doc_len = doc_lengths[filepath]
        tf = doc_term_freqs[filepath]
        
        for term in query_terms:
            if term not in tf:
                continue
                
            # Compute IDF
            n_doc = term_doc_count.get(term, 0)
            idf = math.log((N - n_doc + 0.5) / (n_doc + 0.5) + 1.0)
            
            # Compute BM25 term score
            term_tf = tf[term]
            num = term_tf * (k1 + 1.0)
            den = term_tf + k1 * (1.0 - b + b * (doc_len / (avg_doc_len or 1.0)))
            score += idf * (num / den)
            
        if score > 0.0:
            scores[filepath] = score

    # Sort files by relevance score descending
    sorted_files = sorted(scores.keys(), key=lambda x: scores[x], desc=True)
    return sorted_files[:limit]
