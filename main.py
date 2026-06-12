import os
import threading
import asyncio
import webview
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from watchdog.observers import Observer
from dotenv import load_dotenv

# Подтягиваем ключ из .env файла ДО импорта локальных модулей
load_dotenv()

from core.dependencies import OrangeDeps
from config.settings import get_settings
from core.mcp_client import ObsidianMCPClient
from core.bridge import BridgeAPI
from core.watcher import ObsidianWatcher

# --- АСИНХРОННЫЙ ФОНОВЫЙ ЦИКЛ ---
background_loop = asyncio.new_event_loop()

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

async def safe_connect_mcp(client: ObsidianMCPClient):
    try:
        print("[MCP Client] Подключение к серверу...")
        await client.connect()
    except Exception as e:
        print(f"[MCP Client Error] Не удалось подключиться: {e}")

class ObsidianQueryHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/query':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # Support both active_note_title/user_query and note_title/query
                note_title = data.get('active_note_title', data.get('note_title', ''))
                content = data.get('content', '')
                query = data.get('user_query', data.get('query', ''))
                
                prompt = (
                    f"Obsidian Note: '{note_title}':\n"
                    f"--- CONTENT START ---\n"
                    f"{content}\n"
                    f"--- CONTENT END ---\n\n"
                    f"Question: {query}"
                )
                
                # Pass through the bridge API pipeline
                future = asyncio.run_coroutine_threadsafe(
                    self.server.api._async_run_agent("auto", prompt),
                    self.server.background_loop
                )
                
                response_text = future.result()
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/markdown; charset=utf-8')
                self.end_headers()
                self.wfile.write(response_text.encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def main():
    # Запускаем фоновый цикл событий
    threading.Thread(target=start_background_loop, args=(background_loop,), daemon=True).start()

    # Инициализация зависимостей
    settings = get_settings()
    mcp_client = ObsidianMCPClient(settings.mcp_server_url) if settings.mcp_server_url else None
    
    # Запускаем автоподключение MCP клиента в фоновом цикле событий
    if mcp_client:
        asyncio.run_coroutine_threadsafe(safe_connect_mcp(mcp_client), background_loop)
    
    # Инициализация Watchdog для папки Obsidian
    vault_root = os.path.abspath(settings.obsidian_vault_path)
    deps = OrangeDeps(settings=settings, mcp_client=mcp_client, obsidian_vault_path=vault_root)
    api = BridgeAPI(background_loop, deps)
    
    # Bind BridgeAPI request_execution_override to deps.request_override
    deps.request_override = api.request_execution_override
    
    obsidian_path = os.path.join(vault_root, "_Inbox")
    os.makedirs(obsidian_path, exist_ok=True)
    
    # Запуск HTTP сервера для Obsidian интеграции в фоновом потоке
    server = None
    bound_port = None
    class NonReusableHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = False

    for port in range(settings.orange_port, settings.orange_port + 11):
        try:
            server = NonReusableHTTPServer(('127.0.0.1', port), ObsidianQueryHandler)
            bound_port = port
            break
        except OSError as e:
            print(f"[HTTP Server] Порт {port} занят, пробуем следующий. Ошибка: {e}")
            
    if server is None:
        raise OSError(f"Не удалось запустить HTTP сервер: все порты от {settings.orange_port} до {settings.orange_port + 10} заняты.")
        
    server.deps = deps
    server.api = api
    server.background_loop = background_loop
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
        print(f"[Watchdog] ВНИМАНИЕ: Папка не найдена: {obsidian_path}")

    # Запуск нативного окна приложения со встроенным Edge/Webkit движком
    window = webview.create_window(
        title="Orange Core OS", 
        url="ui/index.html", 
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
            print(f"[MCP Client Error] Ошибка при отключении: {e}")
    
    # Останавливаем фоновый цикл событий
    background_loop.call_soon_threadsafe(background_loop.stop)

if __name__ == "__main__":
    main()
