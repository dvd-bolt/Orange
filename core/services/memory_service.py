from __future__ import annotations

from typing import Optional

from core import db
from core.service_result import error, success


class MemoryService:
    """Owns Memory Editor reads, flag updates, and deletion semantics."""

    def list_items(self, limit: int = 200) -> dict:
        try:
            safe_limit = max(1, min(int(limit), 500))
            items = db.list_memory_messages(safe_limit)
            return success(items, items=items)
        except Exception as exc:
            return error(
                "VALIDATION_ERROR",
                f"Memory could not be loaded: {type(exc).__name__}",
                data=[],
                items=[],
            )

    def update_item(
        self,
        message_id: int,
        is_pinned: Optional[bool] = None,
        exclude_from_rag: Optional[bool] = None,
    ) -> dict:
        try:
            normalized_id = int(message_id)
            ok = db.update_message_memory_flags(
                normalized_id,
                self._coerce_optional_bool(is_pinned),
                self._coerce_optional_bool(exclude_from_rag),
            )
            if not ok:
                return error("VALIDATION_ERROR", "Memory message was not found.")
            db.add_audit_event("memory", "applied", f"Updated memory item {normalized_id}")
            return success(
                {"message_id": normalized_id},
                "Memory item updated.",
                message_id=normalized_id,
            )
        except (TypeError, ValueError) as exc:
            return error("VALIDATION_ERROR", str(exc))
        except Exception as exc:
            return error(
                "VALIDATION_ERROR",
                f"Memory update failed: {type(exc).__name__}",
            )

    def delete_item(self, message_id: int) -> dict:
        try:
            normalized_id = int(message_id)
            ok = db.delete_message(normalized_id)
            if not ok:
                return error("VALIDATION_ERROR", "Memory message was not found.")
            db.add_audit_event("memory", "applied", f"Deleted memory item {normalized_id}")
            return success(
                {"message_id": normalized_id},
                "Memory item deleted.",
                message_id=normalized_id,
            )
        except (TypeError, ValueError) as exc:
            return error("VALIDATION_ERROR", str(exc))
        except Exception as exc:
            return error(
                "VALIDATION_ERROR",
                f"Memory deletion failed: {type(exc).__name__}",
            )

    @staticmethod
    def _coerce_optional_bool(value) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        raise ValueError("Memory flags must be boolean values.")
