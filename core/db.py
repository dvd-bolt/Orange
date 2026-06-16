import sqlite3
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "orange_memory.db"
_lock = threading.Lock()

def get_connection():
    # Используем check_same_thread=False, т.к. будем обращаться из разных потоков (asyncio/pywebview)
    # Используем threading.Lock для безопасности записи
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создает таблицы, если они не существуют"""
    with _lock:
        with get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    is_pinned BOOLEAN DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS message_embeddings (
                    message_id INTEGER PRIMARY KEY,
                    embedding TEXT,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS note_embeddings (
                    file_path TEXT PRIMARY KEY,
                    embedding TEXT,
                    last_modified REAL
                )
            ''')
            # Инициализация FTS5 таблицы для поиска по сообщениям
            try:
                conn.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                        content,
                        tokenize="unicode61"
                    )
                ''')
                # Перенос старых сообщений в FTS5 (ретроактивное индексирование)
                conn.execute('''
                    INSERT INTO messages_fts(rowid, content)
                    SELECT id, content FROM messages
                    WHERE id NOT IN (SELECT rowid FROM messages_fts)
                ''')
            except sqlite3.OperationalError as e:
                print(f"[DB Warning] Не удалось инициализировать FTS5: {e}")
            conn.commit()

# --- CRUD для чатов ---

def create_chat(title: str = "Новый диалог") -> str:
    """Создает новый чат и возвращает его ID"""
    chat_id = str(uuid.uuid4())
    with _lock:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO chats (id, title, is_pinned, updated_at) VALUES (?, ?, 0, CURRENT_TIMESTAMP)",
                (chat_id, title)
            )
            conn.commit()
            print(f"[DB DEBUG] Создан новый чат: {chat_id} | Title: {title}")
    return chat_id

def get_all_chats() -> List[Dict[str, Any]]:
    """Возвращает список всех чатов, сначала закрепленные, затем по дате обновления"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM chats ORDER BY is_pinned DESC, updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

def toggle_pin(chat_id: str) -> bool:
    """Переключает статус закрепления чата. Возвращает новый статус."""
    with _lock:
        with get_connection() as conn:
            cursor = conn.execute("SELECT is_pinned FROM chats WHERE id = ?", (chat_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            new_status = not bool(row["is_pinned"])
            conn.execute(
                "UPDATE chats SET is_pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if new_status else 0, chat_id)
            )
            conn.commit()
            return new_status

def update_chat_title(chat_id: str, title: str):
    """Обновляет заголовок чата"""
    with _lock:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, chat_id)
            )
            conn.commit()

def delete_chat(chat_id: str) -> bool:
    """Удаляет чат и все его сообщения (CASCADE через ON DELETE CASCADE)"""
    with _lock:
        with get_connection() as conn:
            # Сначала удаляем сообщения чата из FTS5 индекса
            conn.execute(
                "DELETE FROM messages_fts WHERE rowid IN (SELECT id FROM messages WHERE chat_id = ?)",
                (chat_id,)
            )
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
    return True

# --- CRUD для сообщений ---

def add_message(chat_id: str, role: str, content: str):
    """Добавляет сообщение в чат и обновляет время чата"""
    with _lock:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content)
            )
            msg_id = cursor.lastrowid
            
            # Синхронизация с FTS5 индексом
            try:
                conn.execute(
                    "INSERT INTO messages_fts(rowid, content) VALUES (?, ?)",
                    (msg_id, content)
                )
            except sqlite3.OperationalError as e:
                print(f"[DB Warning] Не удалось записать в FTS5: {e}")
                
            conn.execute(
                "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chat_id,)
            )
            conn.commit()

def get_chat_history(chat_id: str) -> List[Dict[str, Any]]:
    """Возвращает историю сообщений конкретного чата"""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
            (chat_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

def search_messages(query: str) -> List[Dict[str, Any]]:
    """Быстрый полнотекстовый поиск по сообщениям во всех чатах через FTS5 с фоллбеком на LIKE"""
    clean_query = query.replace("'", " ").replace('"', ' ').strip()
    if not clean_query:
        return []
    
    words = [f"{w}*" for w in clean_query.split() if w]
    match_expression = " AND ".join(words)
    
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                '''SELECT m.*, c.title 
                   FROM messages m 
                   JOIN chats c ON m.chat_id = c.id 
                   WHERE m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?) 
                   ORDER BY m.timestamp DESC LIMIT 50''',
                (match_expression,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            # Фоллбек при синтаксической ошибке запроса FTS5
            print(f"[DB Warning] Ошибка FTS5 поиска ({e}), переход на LIKE...")
            search_term = f"%{query}%"
            cursor = conn.execute(
                '''SELECT m.*, c.title 
                   FROM messages m 
                   JOIN chats c ON m.chat_id = c.id 
                   WHERE m.content LIKE ? 
                   ORDER BY m.timestamp DESC LIMIT 50''',
                (search_term,)
            )
            return [dict(row) for row in cursor.fetchall()]

# Инициализируем БД при импорте модуля
init_db()

# --- CRUD для кэширования эмбеддингов ---

def get_cached_embedding(message_id: int) -> Optional[str]:
    """Возвращает кэшированный эмбеддинг для сообщения в виде JSON-строки"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT embedding FROM message_embeddings WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        return row["embedding"] if row else None

def save_cached_embedding(message_id: int, embedding_json: str):
    """Сохраняет эмбеддинг для сообщения в кэш"""
    with _lock:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO message_embeddings (message_id, embedding) VALUES (?, ?)",
                (message_id, embedding_json)
            )
            conn.commit()

def get_note_embedding(file_path: str) -> Optional[Dict[str, Any]]:
    """Возвращает кэшированный эмбеддинг заметки и время её модификации"""
    with get_connection() as conn:
        cursor = conn.execute("SELECT embedding, last_modified FROM note_embeddings WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            import json
            return {"embedding": json.loads(row["embedding"]), "last_modified": row["last_modified"]}
        return None

def save_note_embedding(file_path: str, embedding_json: str, last_modified: float):
    """Сохраняет эмбеддинг заметки и её время модификации"""
    with _lock:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO note_embeddings (file_path, embedding, last_modified) VALUES (?, ?, ?)",
                (file_path, embedding_json, last_modified)
            )
            conn.commit()

def delete_note_embedding(file_path: str):
    """Удаляет эмбеддинг заметки из кэша"""
    with _lock:
        with get_connection() as conn:
            conn.execute("DELETE FROM note_embeddings WHERE file_path = ?", (file_path,))
            conn.commit()
