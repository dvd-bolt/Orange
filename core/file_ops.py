import os
import uuid
import asyncio
from pathlib import Path
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

def sync_atomic_write(target_path: str | Path, content: str) -> None:
    target_path = Path(target_path)
    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    temp_dir = os.environ.get('TEMP') or os.environ.get('TMP') or '/tmp'
    temp_path = Path(temp_dir) / f"{uuid.uuid4().hex}.tmp"
    
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
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
    Безопасная атомарная запись файла с использованием двухэтапного коммита во временную директорию TEMP.
    """
    await asyncio.to_thread(sync_atomic_write, target_path, content)
