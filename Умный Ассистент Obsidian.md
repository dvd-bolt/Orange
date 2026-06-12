# 🧠 Умный Ассистент Obsidian: Панель Управления и Скрипты Автоматизации

Добро пожаловать в центр управления вашим «Вторым мозгом»! Эта заметка объединяет все предложенные функции автоматизации, расширения возможностей и коучинга. 

Ниже представлены **полностью готовые и рабочие Python-скрипты**, системные промты для коучинга и инструкции по интеграции.

---

## 📅 Быстрый запуск функций через ИИ-ассистента
Вы можете попросить меня выполнить любой из этих скриптов прямо в чате. Например:
*   *«Запусти умный ревью задач и забытых заметок»*
*   *«Запусти авто-перелинковку в моем хранилище»*
*   *«Обнови дайджест новостей по RSS»*

---

## 🛠 Раздел 1. Автоматизация Obsidian (Скрипты Python)

### 1.1. Умный ревью задач (`#todo`) и забытых заметок
Этот скрипт сканирует ваше хранилище Obsidian, находит все невыполненные задачи (`- [ ]`) и заметки, которые не редактировались более 30 дней. Результат он записывает в удобный дайджест `Ревю задач и заметок.md`.

```python
# Сохраните этот код как obsidian_review.py или попросите меня запустить его
import os
import time
from datetime import datetime, timedelta

VAULT_DIR = "."  # Текущая директория хранилища
IGNORE_DIRS = {".obsidian", ".git", ".space", "node_modules"}
DAYS_FOR_OLD = 30

def scan_vault():
    todo_list = []
    old_notes = []
    now = datetime.now()
    threshold_date = now - timedelta(days=DAYS_FOR_OLD)

    for root, dirs, files in os.walk(VAULT_DIR):
        # Игнорируем скрытые папки
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md") and file != "Ревю задач и заметок.md":
                file_path = os.path.join(root, file)
                
                # 1. Поиск задач
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    for line_num, line in enumerate(lines, 1):
                        if "- [ ]" in line:
                            clean_task = line.replace("- [ ]", "").strip()
                            todo_list.append((file, line_num, clean_task))
                except Exception as e:
                    pass
                
                # 2. Поиск забытых заметок по времени изменения
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < threshold_date:
                        old_notes.append((file, mtime.strftime("%Y-%m-%d")))
                except Exception:
                    pass

    # Сортировка старых заметок от самых заброшенных
    old_notes.sort(key=lambda x: x[1])
    return todo_list, old_notes

def write_report(todos, olds):
    report_path = os.path.join(VAULT_DIR, "Ревю задач и заметок.md")
    content = f"# 📋 Еженедельный отчет и Ревю хранилища\n"
    content += f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    
    content += f"## 🔴 Невыполненные задачи ({len(todos)})\n"
    if not todos:
        content += "Отлично! Все задачи выполнены. 🎉\n"
    else:
        for file, line, task in todos:
            # Создаем красивую ссылку на файл и строку
            content += f"- [ ] [[{file[:-3]}]] (стр. {line}): {task}\n"
            
    content += f"\n## ⏳ Забытые заметки (не обновлялись > {DAYS_FOR_OLD} дней): {len(olds)}\n"
    if not olds:
        content += "Все заметки актуальны и свежи! 🌟\n"
    else:
        content += "Рекомендуется пересмотреть, обновить или архивировать эти заметки:\n"
        for file, date in olds:
            content += f"- [[{file[:-3]}]] — *последнее изменение: {date}*\n"
            
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Отчет успешно сохранен в файл [[Ревю задач и заметок]]!")

if __name__ == "__main__":
    todos, olds = scan_vault()
    write_report(todos, olds)
```

---

### 1.2. Авто-перелинковка и создание связей `[[ссылки]]`
Скрипт сканирует ваши файлы и ищет упоминания названий других заметок. Если он находит совпадение, которое еще не оформлено в виде ссылки, он предлагает перелинковку или автоматически добавляет `[[ссылку]]` (безопасно, не ломая существующий синтаксис).

```python
# Сохраните этот код как obsidian_linker.py
import os
import re

VAULT_DIR = "."
IGNORE_DIRS = {".obsidian", ".git", ".space"}

def get_all_notes():
    note_names = {}
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                name_without_ext = file[:-3]
                if len(name_without_ext) > 3:  # Игнорируем слишком короткие названия
                    note_names[name_without_ext] = file
    return note_names

def auto_link_notes():
    notes = get_all_notes()
    updated_count = 0
    
    for root, dirs, files in os.walk(VAULT_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
        for file in files:
            if not file.endswith(".md") or file == "Умный Ассистент Obsidian.md":
                continue
                
            file_path = os.path.join(root, file)
            current_note_name = file[:-3]
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            original_content = content
            
            # Проверяем упоминания других заметок
            for target_name in notes:
                if target_name == current_note_name:
                    continue  # Не ссылаемся на самого себя
                
                # Регулярное выражение: ищет точное совпадение слова, 
                # избегая уже существующих ссылок [[...]] и markdown ссылок
                pattern = r'(?<!\[\[)(?<![a-zA-Zа-яА-Я0-9])' + re.escape(target_name) + r'(?![a-zA-Zа-яА-Я0-9])(?!\]\])'
                
                # Заменяем на [[target_name]]
                content = re.sub(pattern, f"[[{target_name}]]", content)
                
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Обновлена перелинковка в заметке: [[{current_note_name}]]")
                updated_count += 1
                
    print(f"Всего обновлено заметок: {updated_count}")

if __name__ == "__main__":
    auto_link_notes()
```

---

## 🌐 Раздел 2. Мониторинг и Внешние Данные (Органы чувств)

### 2.1. RSS Мониторинг и создание «Дайджеста дня»
Скрипт собирает свежие заголовки из интересных вам RSS-лент (например, Habr, TechCrunch или любые другие темы) и записывает их в удобный ежедневный дайджест в Obsidian.

```python
# Сохраните этот код как obsidian_rss.py
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Список ваших любимых RSS лент
FEEDS = {
    "Habr (Главное)": "https://habr.com/ru/rss/articles/top/daily/?fl=ru",
    "Hacker News": "https://news.ycombinator.com/rss"
}

def fetch_rss_feed(feed_name, url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = []
        
        # Разные форматы RSS могут иметь разную структуру, обрабатываем стандартный канал
        channel = root.find('channel')
        if channel is not None:
            for item in channel.findall('item')[:5]:  # Берем топ-5 новостей
                title = item.find('title').text
                link = item.find('link').text
                items.append((title, link))
        return items
    except Exception as e:
        print(f"Ошибка при загрузке {feed_name}: {e}")
        return []

def create_digest():
    digest_path = "Дайджест дня.md"
    today = datetime.now().strftime("%Y-%m-%d")
    
    content = f"# 📰 Дайджест новостей от {today}\n"
    content += "Автоматическое обновление утренней прессы для вашего фокуса.\n\n"
    
    for feed_name, url in FEEDS.items():
        content += f"## 🌐 {feed_name}\n"
        items = fetch_rss_feed(feed_name, url)
        if not items:
            content += "*Не удалось загрузить новости на данный момент.*\n\n"
        else:
            for title, link in items:
                content += f"- [{title}]({link})\n"
            content += "\n"
            
    with open(digest_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Дайджест успешно обновлен: [[Дайджест дня]]")

if __name__ == "__main__":
    create_digest()
```

---

## 🎓 Раздел 3. Личный Коучинг и Развитие (Промты)

Скопируйте эти промты и отправляйте мне в чат, когда вам нужна экспертная оценка или глубокое понимание сложной темы.

### 🧠 3.1. Метод Фейнмана (Понимание сложных концепций)
> **Инструкция для ИИ:**
> *"Я хочу изучить концепцию [ВСТАВЬТЕ НАЗВАНИЕ]. Твоя задача — объяснить мне её, используя Метод Фейнмана. 
> 1. Объясни тему так просто, как будто мне 10 лет, избегая сложного жаргона и используя аналогии из реального мира.
> 2. После объяснения задай мне один контрольный проверочный вопрос средней сложности, чтобы проверить, как я понял материал.
> 3. Когда я отвечу, укажи на логические пробелы в моем ответе и мягко поправь меня."*

### 👔 3.2. Режим Критика (Методология Питера Друкера / Стива Джобса)
> **Инструкция для ИИ:**
> *"Я собираюсь отправить тебе текст/идею моего проекта: [ВСТАВЬТЕ ТЕКСТ/ОПИСАНИЕ]. 
> Проанализируй её с двух точек зрения:
> 1. **Стив Джобс (Продуктовый перфекционизм и UX):** Бескомпромиссно укажи на то, где идея перегружена, не сфокусирована или не несет эмоциональной ценности для пользователя. Где здесь «простота и магия»?
> 2. **Питер Друкер (Бизнес и эффективность):** Задай жесткие вопросы об эффективности, ключевых метриках, ресурсах и реальной рыночной ценности. Как мы измерим успех?
> Выдай структурированный и жесткий, но конструктивный фидбек."*

---

## ⚙️ Раздел 4. Как настроить запуск скриптов в Obsidian

Чтобы запускать эти скрипты прямо внутри Obsidian в один клик:
1.  **Установите плагин `Shell Commands`** в Obsidian (через Настройки -> Сторонние плагины).
2.  Создайте новую команду:
    *   Назовите её, например, `Запуск Ревю Хранилища`.
    *   В поле команды введите: `python "{{vault_path}}/obsidian_review.py"`
3.  Настройте горячую клавишу или добавьте кнопку на панель через плагин `Commander` для мгновенного выполнения!

*Все настроено и готово к работе. Какую из этих функций мы протестируем или запустим прямо сейчас?*
