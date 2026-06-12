import os
import time
import asyncio
from contextlib import AbstractContextManager

class safe_write_lock(AbstractContextManager):
    """
    Context manager that ensures a file is not locked before writing to it.
    Supports both synchronous ('with safe_write_lock(...)') and 
    asynchronous ('async with safe_write_lock(...)') context management.
    """
    def __init__(self, filepath: str, timeout: float = 10.0, retry_delay: float = 0.5):
        self.filepath = filepath
        self.timeout = timeout
        self.retry_delay = retry_delay

    def _check_access(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, 'a') as f:
                pass
        else:
            parent_dir = os.path.dirname(self.filepath)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(self.filepath, 'w') as f:
                pass

    def __enter__(self):
        elapsed = 0.0
        while elapsed < self.timeout:
            try:
                self._check_access()
                break
            except (PermissionError, OSError) as e:
                print(f"[File Lock Sync] File '{self.filepath}' is busy, retrying in {self.retry_delay}s... ({e})")
                time.sleep(self.retry_delay)
                elapsed += self.retry_delay
        else:
            raise PermissionError(f"Timeout waiting for write lock on file '{self.filepath}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        elapsed = 0.0
        while elapsed < self.timeout:
            try:
                # Run self._check_access in executor to avoid blocking the loop
                await asyncio.to_thread(self._check_access)
                break
            except (PermissionError, OSError) as e:
                print(f"[File Lock Async] File '{self.filepath}' is busy, retrying in {self.retry_delay}s... ({e})")
                await asyncio.sleep(self.retry_delay)
                elapsed += self.retry_delay
        else:
            raise PermissionError(f"Timeout waiting for write lock on file '{self.filepath}'")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
