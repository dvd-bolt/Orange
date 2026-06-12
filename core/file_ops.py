import os
import asyncio
from pathlib import Path
import aiofiles
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

@retry(
    retry=retry_if_exception_type((PermissionError, OSError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def atomic_write_obsidian_note(target_path: str | Path, content: str) -> None:
    """
    Безопасная атомарная запись файла с учетом блокировок iCloud/Obsidian.
    Записывает во временный файл, делает fsync, затем атомарно переименовывает.
    """
    target_path = Path(target_path)
    temp_path = target_path.with_suffix('.tmp')

    from core.file_lock import safe_write_lock
    try:
        async with safe_write_lock(target_path):
            # Асинхронно пишем во временный файл
            async with aiofiles.open(temp_path, mode='w', encoding='utf-8') as f:
                await f.write(content)
                await f.flush()
                # Принудительно сбрасываем буфер ОС на диск в отдельном потоке
                await asyncio.to_thread(os.fsync, f.fileno())

            # Атомарно заменяем целевой файл
            await asyncio.to_thread(os.replace, temp_path, target_path)

    except Exception as e:
        # Убираем временный файл при ошибках
        if temp_path.exists():
            try:
                await asyncio.to_thread(os.remove, temp_path)
            except Exception:
                pass
        raise e
