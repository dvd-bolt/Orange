# Project: ORANGE OS Obsidian & Telegram integration

## Architecture
ORANGE is a PyWebView-based desktop AI assistant with a Python backend and HTML/JS frontend.
The architecture is structured as follows:
- **UI layer**: `ui/index.html`, `ui/main.js`, `ui/style.css` communicating with Python via `pywebview`'s JS API Bridge.
- **Bridge layer**: `core/bridge.py` routing frontend API calls to Python core functions and async event loop.
- **Agent Core**: `core/agent.py`, `core/tools.py` executing Gemini LLM prompts with local database memory (`core/db.py`) and Obsidian tools.
- **Obsidian Integration**: Web server running in background on port 8000 handling external queries, mapping note-context to agent queries.
- **Telegram Daemon**: Background client thread filtering incoming alerts, logging to the Telemetry panel, and updating tasks.

## Code Layout
- `main.py`: Application startup, background loop orchestration, WebView instantiation, and observer cleanup.
- `config/settings.json`: JSON configuration settings containing authorization tokens, telemetry preferences, and daemon status.
- `core/bridge.py`: Class `BridgeAPI` exposing methods to JS, triggering modals, handling overrides and panics.
- `core/daemon_manager.py` (New): Controls background worker thread lifecycles (Telegram daemon).
- `integrations/obsidian/` (New): Script/bridge plugin to interface Obsidian app workspace with ORANGE backend.
- `scratch/` (New): Directory for validation tests (`test_bugfixes.py`, `test_advanced.py`).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Obsidian Integration | HTTP server on port 8000; `/query` endpoint; `integrations/obsidian/` script; vault root adjustment | None | PLANNED |
| 2 | M2: Telegram Daemon | `core/daemon_manager.py`; thread lifecycle; settings toggles; telemetry/inbox routing | M1 | PLANNED |
| 3 | M3: UI Overlay Audit | Cleanup duplicates; error interception for panic; async Future command override | M2 | PLANNED |
| 4 | M4: Final E2E & Adversarial | PASS all E2E validation tests in `scratch/`; coverage hardening | M3 | PLANNED |

## Interface Contracts
### Obsidian API Endpoint (`/query`)
- **Method**: `POST`
- **Path**: `/query`
- **Request Body**: `{"note_title": "...", "content": "...", "query": "..."}`
- **Response**: `{"answer": "..."}`
- **Port**: `8000`

### Settings Configuration
- File: `config/settings.json`
- Key: `"telegram_daemon"` ("ON" / "OFF")

### JS Bridge / System Panics
- **Method**: `window.pywebview.api.trigger_panic(msg)` or evaluate JS: `triggerSystemPanic(msg)`
- **Z-Index**: `999999` for `#system-panic-modal`

### JS Bridge / Command Execution Override
- **Method**: `await request_execution_override(cmd)`
- **JS Call**: `showExecutionOverride(cmd)`
- **Approval Callback**: `api_handle_override_response(approved: bool)` resolving async Future.
