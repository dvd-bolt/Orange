import os
import time
from watchdog.events import FileSystemEventHandler
from core.bridge import BridgeAPI

class ObsidianWatcher(FileSystemEventHandler):
    """Слушатель событий файловой системы с механизмом debounce"""
    def __init__(self, api: BridgeAPI):
        self.api = api
        self.last_modified = {}
        self.debounce_seconds = 10.0

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith('.md'):
            return
            
        file_path = event.src_path
        filename = os.path.basename(file_path)

        # Update BM25 index
        try:
            from core.bm25 import global_bm25_indexer
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            global_bm25_indexer.add_document(file_path, content)
            print(f"[Watcher] Updated BM25 index for: {filename}")
        except Exception as e:
            print(f"[Watcher Error] Failed to update BM25 index for modified file: {e}")
            
        current_time = time.time()
        
        # Debounce (кулдаун) для предотвращения спама при автосохранении
        last_time = self.last_modified.get(file_path, 0)
        if current_time - last_time < self.debounce_seconds:
            return
            
        self.last_modified[file_path] = current_time
        safe_filename = filename.replace("'", "\\'").replace('"', '\\"')
        
        if self.api._window:
            self.api._window.evaluate_js(
                f"appendMessage('Система [Watchdog]', 'Обнаружено изменение в файле <b>{safe_filename}</b>. Запускаю фоновый анализ...', 'sys')"
            )
            
        # Запускаем агента для чтения файла в профиле project_manager (Распределение задач)
        self.api.push_background_task("project_manager", file_path)

    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith('.md'):
            return
        file_path = event.src_path
        filename = os.path.basename(file_path)
        try:
            from core.bm25 import global_bm25_indexer
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            global_bm25_indexer.add_document(file_path, content)
            print(f"[Watcher] Added new note to BM25 index: {filename}")
        except Exception as e:
            print(f"[Watcher Error] Failed to index created file: {e}")

    def on_deleted(self, event):
        if event.is_directory or not event.src_path.endswith('.md'):
            return
        file_path = event.src_path
        filename = os.path.basename(file_path)
        try:
            from core.bm25 import global_bm25_indexer
            from core import db
            global_bm25_indexer.remove_document(file_path)
            db.delete_note_embedding(file_path)
            print(f"[Watcher] Removed deleted note from BM25 and vector cache: {filename}")
        except Exception as e:
            print(f"[Watcher Error] Failed to handle note deletion index cleanup: {e}")
