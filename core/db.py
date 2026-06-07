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

# --- CRUD для сообщений ---

def add_message(chat_id: str, role: str, content: str):
    """Добавляет сообщение в чат и обновляет время чата"""
    with _lock:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content)
            )
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
    """Поиск по сообщениям во всех чатах"""
    search_term = f"%{query}%"
    with get_connection() as conn:
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
