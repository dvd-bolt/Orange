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
            
        current_time = time.time()
        file_path = event.src_path
        
        # Debounce (кулдаун) для предотвращения спама при автосохранении
        last_time = self.last_modified.get(file_path, 0)
        if current_time - last_time < self.debounce_seconds:
            return
            
        self.last_modified[file_path] = current_time
        filename = os.path.basename(file_path)
        safe_filename = filename.replace("'", "\\'").replace('"', '\\"')
        
        if self.api._window:
            self.api._window.evaluate_js(
                f"appendMessage('Система [Watchdog]', 'Обнаружено изменение в файле <b>{safe_filename}</b>. Запускаю фоновый анализ...', 'sys')"
            )
            
        # Запускаем агента для чтения файла в профиле project_manager (Распределение задач)
        self.api.push_background_task("project_manager", file_path)
