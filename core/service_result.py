from __future__ import annotations

from typing import Any, Dict


def success(
    data: Any = None,
    message: str = "",
    **compatibility_fields: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": "success",
        "data": data,
        "message": str(message or ""),
        "error_code": None,
    }
    result.update(compatibility_fields)
    return result


def error(
    error_code: str,
    message: str,
    *,
    data: Any = None,
    **compatibility_fields: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": "error",
        "data": data,
        "message": str(message or "Operation failed."),
        "error_code": str(error_code or "VALIDATION_ERROR"),
    }
    result.update(compatibility_fields)
    return result


def normalize(
    payload: Dict[str, Any],
    *,
    data: Any = None,
) -> Dict[str, Any]:
    """Backfill the shared result envelope without removing compatibility fields."""
    result = dict(payload)
    status = str(result.get("status") or "success")
    if status in {"success_local_only", "no_changes"}:
        result.setdefault("outcome", status)
        status = "success"
    result["status"] = status
    result.setdefault("data", data)
    result.setdefault("message", "")
    result.setdefault(
        "error_code",
        None if status == "success" else "VALIDATION_ERROR",
    )
    return result
