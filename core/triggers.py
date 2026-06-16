import os
import time
import logging
import threading
from typing import Dict, Any, Callable
from http.server import HTTPServer, BaseHTTPRequestHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("triggers")

class TriggerRegistry:
    """
    TriggerRegistry manages registration, starting, and stopping of
    CronTriggers, FileWatchTriggers, and WebhookTriggers.
    """
    def __init__(self):
        self.triggers: Dict[str, Any] = {}
        self.active_runners: Dict[str, Any] = {}

    def register_trigger(self, trigger_id: str, trigger_type: str, config: dict, callback: Callable):
        """Registers a trigger with its configuration and callback."""
        if trigger_id in self.triggers:
            self.unregister_trigger(trigger_id)
            
        self.triggers[trigger_id] = {
            "type": trigger_type,
            "config": config,
            "callback": callback
        }
        logger.info(f"Registered trigger {trigger_id} of type {trigger_type}")

    def unregister_trigger(self, trigger_id: str):
        """Stops and unregisters a trigger."""
        self.stop_trigger(trigger_id)
        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            logger.info(f"Unregistered trigger {trigger_id}")

    def start_trigger(self, trigger_id: str):
        """Starts the trigger execution."""
        if trigger_id not in self.triggers:
            raise ValueError(f"Trigger {trigger_id} is not registered")
            
        if trigger_id in self.active_runners:
            return
            
        trigger_info = self.triggers[trigger_id]
        trigger_type = trigger_info["type"]
        config = trigger_info["config"]
        callback = trigger_info["callback"]
        
        runner = None
        if trigger_type == "CronTrigger":
            runner = CronTriggerRunner(trigger_id, config, callback)
        elif trigger_type == "FileWatchTrigger":
            runner = FileWatchTriggerRunner(trigger_id, config, callback)
        elif trigger_type == "WebhookTrigger":
            runner = WebhookTriggerRunner(trigger_id, config, callback)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
            
        runner.start()
        self.active_runners[trigger_id] = runner
        logger.info(f"Started trigger {trigger_id}")

    def stop_trigger(self, trigger_id: str):
        """Stops a running trigger."""
        if trigger_id in self.active_runners:
            runner = self.active_runners[trigger_id]
            runner.stop()
            del self.active_runners[trigger_id]
            logger.info(f"Stopped trigger {trigger_id}")

    def start_all(self):
        """Starts all registered triggers."""
        for tid in list(self.triggers.keys()):
            self.start_trigger(tid)

    def stop_all(self):
        """Stops all running triggers."""
        for tid in list(self.active_runners.keys()):
            self.stop_trigger(tid)


class CronTriggerRunner:
    """Simulates a cron scheduler using a background thread and periodic intervals."""
    def __init__(self, trigger_id: str, config: dict, callback: Callable):
        self.trigger_id = trigger_id
        self.interval = config.get("interval", 60) # default interval in seconds
        self.cron_expr = config.get("cron", "* * * * *")
        self.callback = callback
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        # Extremely basic scheduler: wait interval seconds and call callback
        while self.running:
            time.sleep(self.interval)
            if self.running:
                try:
                    self.callback({"trigger_id": self.trigger_id, "type": "cron", "timestamp": time.time()})
                except Exception as e:
                    logger.error(f"Error in cron callback: {e}")


class FileWatchTriggerRunner(FileSystemEventHandler):
    """Watches file system modifications using watchdog."""
    def __init__(self, trigger_id: str, config: dict, callback: Callable):
        super().__init__()
        self.trigger_id = trigger_id
        self.path = os.path.abspath(config.get("path", "."))
        self.recursive = config.get("recursive", False)
        self.callback = callback
        self.observer = None

    def start(self):
        self.observer = Observer()
        os.makedirs(self.path, exist_ok=True)
        self.observer.schedule(self, path=self.path, recursive=self.recursive)
        self.observer.start()

    def stop(self):
        if self.observer:
            self.observer.stop()

    def on_modified(self, event):
        if event.is_directory:
            return
        try:
            self.callback({
                "trigger_id": self.trigger_id,
                "type": "file_watch",
                "event_type": "modified",
                "src_path": event.src_path,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Error in file watch callback: {e}")


class WebhookTriggerRunner:
    """Listens to incoming webhook requests on a local port."""
    def __init__(self, trigger_id: str, config: dict, callback: Callable):
        self.trigger_id = trigger_id
        self.port = config.get("port", 9000)
        self.path = config.get("path", "/webhook")
        self.callback = callback
        self.server = None
        self.thread = None

    def start(self):
        handler_class = self._make_handler_class(self.path, self.callback, self.trigger_id)
        
        # Try port fallback if occupied
        for p in range(self.port, self.port + 10):
            try:
                self.server = HTTPServer(('127.0.0.1', p), handler_class)
                self.port = p
                break
            except OSError:
                continue
                
        if not self.server:
            raise RuntimeError(f"Could not bind WebhookTrigger to ports {self.port} to {self.port+9}")
            
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"WebhookTrigger serving on http://127.0.0.1:{self.port}{self.path}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)

    @staticmethod
    def _make_handler_class(path: str, callback: Callable, trigger_id: str):
        class WebhookHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # suppress logging standard request output to stderr
                
            def do_POST(self):
                if self.path == path:
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length).decode('utf-8')
                    
                    import json
                    payload = {}
                    try:
                        payload = json.loads(post_data)
                    except Exception:
                        payload = {"raw_data": post_data}
                        
                    try:
                        callback({
                            "trigger_id": trigger_id,
                            "type": "webhook",
                            "payload": payload,
                            "timestamp": time.time()
                        })
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"status":"received"}')
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()
        return WebhookHandler
