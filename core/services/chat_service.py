from typing import Any, Dict, List

from core import db


class ChatService:
    """Chat persistence facade around SQLite CRUD helpers."""

    def list_chats(self) -> List[Dict[str, Any]]:
        return db.get_all_chats()

    def create_chat(self, title: str) -> str:
        return db.create_chat(title)

    def load_chat(self, chat_id: str) -> List[Dict[str, Any]]:
        return db.get_chat_history(chat_id)

    def toggle_pin(self, chat_id: str) -> bool:
        return db.toggle_pin(chat_id)

    def delete_chat(self, chat_id: str) -> bool:
        return db.delete_chat(chat_id)

    def rename_chat(self, chat_id: str, new_title: str) -> bool:
        cleaned = new_title.strip()
        if not cleaned:
            return False
        db.update_chat_title(chat_id, cleaned[:50])
        return True

    def search_chats(self, query: str) -> List[Dict[str, Any]]:
        cleaned = query.strip()
        if not cleaned:
            return []
        return db.search_messages(cleaned)
