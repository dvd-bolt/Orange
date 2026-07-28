import os
import time
import json
from types import SimpleNamespace
from watchdog.events import FileSystemEventHandler
from core.bridge import BridgeAPI

class ObsidianWatcher(FileSystemEventHandler):
    """Слушатель событий файловой системы с механизмом debounce"""
    def __init__(self, api: BridgeAPI):
        self.api = api
        self.last_modified = {}
        self.debounce_seconds = 1.5

    def on_modified(self, event):
        if event.is_directory or not event.src_path.lower().endswith('.md'):
            return
            
        file_path = os.path.realpath(event.src_path)
        filename = os.path.basename(file_path)
        if filename == "Inbox Review.md" or filename.startswith("."):
            return
        from core.write_activity import was_recent_orange_write

        if was_recent_orange_write(file_path):
            return
            
        current_time = time.monotonic()
        
        # Debounce (кулдаун) для предотвращения спама при автосохранении
        last_time = self.last_modified.get(file_path, 0)
        if current_time - last_time < self.debounce_seconds:
            return
            
        self.last_modified[file_path] = current_time
        if len(self.last_modified) > 500:
            cutoff = current_time - max(self.debounce_seconds * 4, 10)
            self.last_modified = {
                path: timestamp
                for path, timestamp in self.last_modified.items()
                if timestamp >= cutoff
            }
        if self.api._window:
            try:
                self.api._window.evaluate_js(
                    f"appendMessage('Smart Inbox', {json.dumps(f'Обнаружено изменение: {filename}. Создаю предложение.')}, 'sys')"
                )
            except Exception:
                pass
            
        # Smart Inbox must propose actions first; file writes happen only after UI confirmation.
        if hasattr(self.api, "propose_inbox_review"):
            self.api.propose_inbox_review(file_path)

    def on_created(self, event):
        self.on_modified(event)

    def on_moved(self, event):
        if getattr(event, "dest_path", ""):
            self.on_modified(
                SimpleNamespace(
                    is_directory=event.is_directory,
                    src_path=event.dest_path,
                )
            )

    def on_deleted(self, event):
        pass
