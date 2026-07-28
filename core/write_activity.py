from __future__ import annotations

import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_recent_writes: dict[str, float] = {}


def mark_orange_write(path: str | Path) -> None:
    """Record an ORANGE-owned write so the watcher can ignore its echo event."""
    normalized = os.path.realpath(os.fspath(path))
    now = time.monotonic()
    with _lock:
        _recent_writes[normalized] = now
        _prune(now)


def was_recent_orange_write(path: str | Path, *, window_seconds: float = 4.0) -> bool:
    normalized = os.path.realpath(os.fspath(path))
    now = time.monotonic()
    with _lock:
        _prune(now, max_age=max(window_seconds * 3, 12.0))
        timestamp = _recent_writes.get(normalized)
    return timestamp is not None and now - timestamp <= window_seconds


def _prune(now: float, *, max_age: float = 30.0) -> None:
    expired = [
        path
        for path, timestamp in _recent_writes.items()
        if now - timestamp > max_age
    ]
    for path in expired:
        _recent_writes.pop(path, None)
