import os
import threading
import asyncio
import webview
import json
import socket
from concurrent.futures import TimeoutError as FutureTimeoutError
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from watchdog.observers import Observer
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Подтягиваем ключ из .env файла ДО импорта локальных модулей
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from core.dependencies import OrangeDeps
from config.settings import get_settings
from core.mcp_client import ObsidianMCPClient
from core.bridge import BridgeAPI
from core.watcher import ObsidianWatcher
from core.path_safety import VaultPathResolver

# Импорт PyQt6 модулей для конфигурации (если доступны)
QT_AVAILABLE = False
try:
    import qtpy.QtWebEngineWidgets
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
    QT_AVAILABLE = True
except ImportError:
    pass

# Принудительное включение сглаживания на уровне операционной системы
import os
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"


# --- АСИНХРОННЫЙ ФОНОВЫЙ ЦИКЛ ---
background_loop = asyncio.new_event_loop()
MAX_HTTP_QUERY_BYTES = 1024 * 1024
HTTP_QUERY_TIMEOUT_SECONDS = 180
HTTP_READ_TIMEOUT_SECONDS = 15
MAX_HTTP_RESPONSE_BYTES = 1024 * 1024

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

async def safe_connect_mcp(client: ObsidianMCPClient):
    try:
        print("[MCP Client] Подключение к серверу...")
        await client.connect()
    except Exception as e:
        print(f"[MCP Client Error] Не удалось подключиться: {type(e).__name__}")

def build_note_payload(vault_path: str, note_path: str) -> dict:
    """Builds the `/api/note` response while keeping the path inside the vault."""
    resolver = VaultPathResolver(vault_path)
    candidate = resolver.resolve(note_path, must_exist=True, allowed_extensions={".md"})

    with candidate.open('r', encoding='utf-8', errors='ignore') as file:
        content = file.read(8001)

    from core.graph_api import get_notes_graph
    relative_path = resolver.relative(candidate)
    graph = get_notes_graph(str(resolver.root))
    node = next((item for item in graph.get("nodes", []) if item.get("path") == relative_path), {})
    return {
        "path": relative_path,
        "title": candidate.stem,
        "content": content[:8000],
        "suggested_links": node.get("suggested_links", []),
        "degree": node.get("degree", 0),
        "orphan": node.get("orphan", False),
        "type": node.get("type", "note"),
    }

class ObsidianQueryHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(HTTP_READ_TIMEOUT_SECONDS)

    def _send_json(self, status: int, payload: dict, *, cors: bool = False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cors:
            origin = self.headers.get("Origin", "")
            parsed_origin = urlparse(origin)
            allowed_loopback = (
                parsed_origin.scheme in {"http", "https"}
                and parsed_origin.hostname in {"127.0.0.1", "localhost", "::1"}
            )
            if origin == "null" or allowed_loopback:
                self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(body)

    def _send_query_error(self, status: int, error_code: str, message: str):
        payload = {"status": "error", "error_code": error_code, "message": message}
        self._send_json(status, payload)

    def _is_local_browser_request(self) -> bool:
        host = urlparse(f"//{self.headers.get('Host', '')}").hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return False

        origin = self.headers.get("Origin", "")
        if not origin or origin == "null":
            return True
        parsed_origin = urlparse(origin)
        return (
            parsed_origin.scheme in {"http", "https"}
            and parsed_origin.hostname in {"127.0.0.1", "localhost", "::1"}
        )

    def _reject_non_local_request(self) -> bool:
        if self._is_local_browser_request():
            return False
        self._send_json(
            403,
            {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Only local application requests are accepted.",
            },
        )
        return True

    def do_GET(self):
        if self._reject_non_local_request():
            return
        parsed = urlparse(self.path)
        if parsed.path == '/api/graph':
            try:
                from core.graph_api import get_notes_graph
                vault_path = self.server.deps.obsidian_vault_path
                graph_data = get_notes_graph(vault_path)
                
                self._send_json(200, graph_data, cors=True)
            except Exception as e:
                self._send_json(
                    500,
                    {"status": "error", "error_code": "PROVIDER_ERROR", "message": type(e).__name__},
                    cors=True,
                )
        elif parsed.path == '/api/note':
            try:
                query = parse_qs(parsed.query)
                note_path = query.get('path', [''])[0]
                payload = build_note_payload(self.server.deps.obsidian_vault_path, note_path)

                self._send_json(200, payload, cors=True)
            except Exception as e:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "error_code": "VALIDATION_ERROR",
                        "message": "Note path is invalid or the note is unavailable.",
                    },
                    cors=True,
                )
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self._reject_non_local_request():
            return
        if urlparse(self.path).path == '/query':
            future = None
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length <= 0:
                    self._send_query_error(400, "VALIDATION_ERROR", "Request body is empty.")
                    return
                if content_length > MAX_HTTP_QUERY_BYTES:
                    self._send_query_error(413, "VALIDATION_ERROR", "Request body exceeds 1 MB.")
                    return
                try:
                    post_data = self.rfile.read(content_length)
                except socket.timeout:
                    self._send_query_error(
                        408,
                        "TIMEOUT",
                        f"Request body was not received within {HTTP_READ_TIMEOUT_SECONDS} seconds.",
                    )
                    return
                data = json.loads(post_data.decode('utf-8'))
                if not isinstance(data, dict):
                    self._send_query_error(400, "VALIDATION_ERROR", "JSON body must be an object.")
                    return
                
                # Support both active_note_title/user_query and note_title/query
                note_title = data.get('active_note_title', data.get('note_title', ''))
                content = data.get('content', '')
                query = data.get('user_query', data.get('query', ''))
                if not isinstance(content, str) or not isinstance(query, str) or not isinstance(note_title, str):
                    self._send_query_error(400, "VALIDATION_ERROR", "Query fields must be strings.")
                    return
                if not query.strip():
                    self._send_query_error(400, "VALIDATION_ERROR", "Query is empty.")
                    return
                if len(query) > 20_000 or len(content) > 250_000 or len(note_title) > 500:
                    self._send_query_error(
                        413,
                        "VALIDATION_ERROR",
                        "One or more query fields exceed their allowed size.",
                    )
                    return
                
                prompt = (
                    f"Obsidian Note: '{note_title}':\n"
                    f"--- CONTENT START ---\n"
                    f"{content}\n"
                    f"--- CONTENT END ---\n\n"
                    f"Question: {query}"
                )
                
                # Pass through the bridge API pipeline
                future = asyncio.run_coroutine_threadsafe(
                    self.server.api._async_run_http_query("auto", prompt, query),
                    self.server.background_loop
                )
                
                response_text = future.result(timeout=HTTP_QUERY_TIMEOUT_SECONDS)
                marker_errors = {
                    "[NOT_CONFIGURED]": (503, "NOT_CONFIGURED"),
                    "[VALIDATION_ERROR]": (400, "VALIDATION_ERROR"),
                    "[PROVIDER_ERROR]": (502, "PROVIDER_ERROR"),
                    "[TIMEOUT]": (504, "TIMEOUT"),
                }
                for marker, (status_code, error_code) in marker_errors.items():
                    if response_text.startswith(marker):
                        self._send_query_error(
                            status_code,
                            error_code,
                            response_text[len(marker):].strip(),
                        )
                        return
                if len(response_text.encode("utf-8")) > MAX_HTTP_RESPONSE_BYTES:
                    self._send_query_error(
                        502,
                        "PROVIDER_ERROR",
                        "Agent response exceeded the 1 MB HTTP response limit.",
                    )
                    return
                
                accept_header = self.headers.get('Accept', '')
                if 'application/json' in accept_header:
                    self._send_json(200, {"status": "success", "answer": response_text})
                else:
                    body = response_text.encode("utf-8")
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/markdown; charset=utf-8')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                
            except (FutureTimeoutError, socket.timeout) as exc:
                future_completed = future is not None and future.done()
                if future is not None and not future_completed:
                    future.cancel()
                message = str(exc).strip()
                busy_timeout = future_completed and "busy" in message.lower()
                self._send_query_error(
                    503 if busy_timeout else 504,
                    "TIMEOUT",
                    "Agent is busy. Try again shortly."
                    if busy_timeout
                    else f"Agent request exceeded {HTTP_QUERY_TIMEOUT_SECONDS} seconds.",
                )
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                self._send_query_error(400, "VALIDATION_ERROR", str(e))
            except Exception as e:
                from core.services.agent_runner import AgentNotConfiguredError

                if isinstance(e, AgentNotConfiguredError):
                    self._send_query_error(503, "NOT_CONFIGURED", str(e))
                    return
                print(f"[HTTP Query Error] {type(e).__name__}")
                self._send_query_error(502, "PROVIDER_ERROR", f"Agent request failed: {type(e).__name__}")
        else:
            self.send_response(404)
            self.end_headers()

def main():
    import sys
    sys.stdout = sys.stderr

    # Инициализация QApplication для настройки системного сглаживания (если доступен PyQt6)
    if "QApplication" in globals():
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        font = QFont("IBM Plex Mono")
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        app.setFont(font)

    # Запускаем фоновый цикл событий
    threading.Thread(target=start_background_loop, args=(background_loop,), daemon=True).start()

    # Инициализация зависимостей
    settings = get_settings()
    mcp_client = ObsidianMCPClient(settings.mcp_server_url) if settings.mcp_server_url else None
    
    # Запускаем автоподключение MCP клиента в фоновом цикле событий
    if mcp_client:
        asyncio.run_coroutine_threadsafe(safe_connect_mcp(mcp_client), background_loop)
    
    # Инициализация Watchdog для папки Obsidian
    configured_vault = os.path.expanduser(settings.obsidian_vault_path)
    vault_root = (
        os.path.realpath(configured_vault)
        if os.path.isabs(configured_vault)
        else os.path.realpath(os.path.join(PROJECT_ROOT, configured_vault))
    )
    
    # Инициализация поискового индекса BM25 (Deprecated)
    # from core.bm25 import global_bm25_indexer
    # global_bm25_indexer.index_vault(vault_root)
    
    deps = OrangeDeps(settings=settings, mcp_client=mcp_client, obsidian_vault_path=vault_root)
    api = BridgeAPI(background_loop, deps)
    
    # Bind BridgeAPI request_execution_override to deps.request_override
    deps.request_override = api.request_execution_override
    
    obsidian_path = os.path.join(vault_root, "_Inbox")
    
    # Запуск HTTP сервера для Obsidian интеграции в фоновом потоке
    server = None
    bound_port = None
    class NonReusableHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = False
        daemon_threads = True

    start_port = settings.orange_port
    for port in range(start_port, start_port + 11):
        try:
            server = NonReusableHTTPServer(('127.0.0.1', port), ObsidianQueryHandler)
            bound_port = port
            break
        except OSError as e:
            print(f"[HTTP Server] Порт {port} занят, пробуем следующий. Ошибка: {e}")
            
    if server is None:
        raise OSError(f"Не удалось запустить HTTP сервер: все порты от {start_port} до {start_port + 10} заняты.")
        
    server.deps = deps
    server.api = api
    server.background_loop = background_loop
    api.set_http_endpoint("127.0.0.1", bound_port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[HTTP Server] Запуск HTTP сервера на http://127.0.0.1:{bound_port}")
    
    observer = None
    if os.path.exists(obsidian_path):
        observer = Observer()
        event_handler = ObsidianWatcher(api)
        observer.schedule(event_handler, path=obsidian_path, recursive=True)
        observer.start()
        print(f"[Watchdog] Отслеживание папки: {obsidian_path}")
    else:
        print(f"[Watchdog] NOT_CONFIGURED: Папка не найдена: {obsidian_path}")

    # Запуск нативного окна приложения со встроенным Edge/Webkit движком
    window = webview.create_window(
        title="Orange Core OS", 
        url=os.path.join(PROJECT_ROOT, "ui", "index.html"),
        js_api=api, 
        width=1200, 
        height=800,
        resizable=True
    )
    api._window = window
    
    # Инициализация и запуск фонового демона Telegram
    from core.daemon_manager import DaemonManager
    daemon_manager = DaemonManager(api)
    daemon_manager.start()
    
    try:
        if QT_AVAILABLE:
            webview.start(gui='qt')
        else:
            webview.start()
    except Exception:
        webview.start()
    
    # Корректное завершение работы фоновых процессов при закрытии окна
    daemon_manager.stop()
    
    print("[HTTP Server] Остановка HTTP сервера...")
    server.shutdown()
    server.server_close()
    print("[HTTP Server] HTTP сервер остановлен.")
    
    if observer:
        observer.stop()
        observer.join()
        
    # Закрываем соединение с MCP клиентом перед выходом
    if mcp_client:
        future = asyncio.run_coroutine_threadsafe(mcp_client.disconnect(), background_loop)
        try:
            # Дадим ему до 3 секунд завершить соединение
            future.result(timeout=3.0)
        except Exception as e:
            print(
                f"[MCP Client Error] Ошибка при отключении: "
                f"{type(e).__name__}"
            )

    shutdown_future = asyncio.run_coroutine_threadsafe(
        api.shutdown(),
        background_loop,
    )
    try:
        shutdown_future.result(timeout=3.0)
    except Exception as e:
        print(f"[Shutdown Warning] Background service cleanup failed: {type(e).__name__}")
    
    # Останавливаем фоновый цикл событий
    background_loop.call_soon_threadsafe(background_loop.stop)

if __name__ == "__main__":
    main()
