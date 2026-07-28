import os
import uuid
import asyncio
from pathlib import Path
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

def sync_atomic_write(target_path: str | Path, content: str) -> None:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.parent / f".{target_path.name}.{uuid.uuid4().hex}.tmp"
    
    try:
        from core.write_activity import mark_orange_write

        mark_orange_write(target_path)
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
        mark_orange_write(target_path)
        try:
            directory_fd = os.open(str(target_path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception as e:
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e

@retry(
    retry=retry_if_exception_type((PermissionError, OSError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def atomic_write_obsidian_note(target_path: str | Path, content: str) -> None:
    """
    Безопасная атомарная запись через временный файл рядом с целевым.
    """
    await asyncio.to_thread(sync_atomic_write, target_path, content)
