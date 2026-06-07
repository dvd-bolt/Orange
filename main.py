import os
import threading
import asyncio
import webview
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
    vault_root = r"C:\icloud\iCloudDrive\iCloud~md~obsidian\obs_chest"
    deps = OrangeDeps(settings=settings, mcp_client=mcp_client, obsidian_vault_path=vault_root)
    api = BridgeAPI(background_loop, deps)
    
    obsidian_path = os.path.join(vault_root, "_Inbox")
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
    webview.start()
    
    # Корректное завершение работы фоновых процессов при закрытии окна
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
