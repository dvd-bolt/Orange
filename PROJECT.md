# Project: ORANGE OS Obsidian & Telegram integration

## Architecture
ORANGE is a PyWebView-based desktop AI assistant with a Python backend and HTML/JS frontend.
The architecture is structured as follows:
- **UI layer**: `ui/index.html`, `ui/main.js`, `ui/style.css` communicating with Python via `pywebview`'s JS API Bridge.
- **Bridge layer**: `core/bridge.py` as a thin JS facade over services in `core/services/`.
- **Agent Core**: `core/agent.py`, `core/tools.py` executing Gemini LLM prompts with local database memory (`core/db.py`) and Obsidian tools.
- **Obsidian Integration**: Web server running in background from `ORANGE_PORT` (default `8080`) handling external queries, mapping note-context to agent queries.
- **Telegram Daemon**: Background client thread filtering incoming alerts, logging to the Telemetry panel, and updating tasks.

## Code Layout
- `main.py`: Application startup, background loop orchestration, WebView instantiation, and observer cleanup.
- `config/settings.json`: JSON configuration settings containing authorization tokens, telemetry preferences, and daemon status.
- `core/bridge.py`: Class `BridgeAPI` exposing stable methods to JS, triggering modals, handling overrides and panics.
- `core/services/`: Chat, settings, attachments, agent runner, Smart Inbox, and dashboard services.
- `core/daemon_manager.py` (New): Controls background worker thread lifecycles (Telegram daemon).
- `integrations/obsidian/` (New): Script/bridge plugin to interface Obsidian app workspace with ORANGE backend.
- `scratch/` (New): Directory for validation tests (`test_bugfixes.py`, `test_advanced.py`).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Obsidian Integration | HTTP server from `ORANGE_PORT`; `/query` endpoint; `integrations/obsidian/` script; vault root adjustment | None | IMPLEMENTED |
| 2 | M2: Telegram Daemon | `core/daemon_manager.py`; thread lifecycle; settings toggles; telemetry/inbox routing | M1 | IMPLEMENTED |
| 3 | M3: UI Overlay Audit | Panic overlay, async Future command override, sanitized Markdown rendering | M2 | IMPLEMENTED |
| 4 | M4: Validation | Unit tests, CI, restricted executor checks | M3 | IN PROGRESS |
| 5 | M5: Product Controls | Memory Editor, Smart Inbox, Knowledge Graph v2, Morning Dashboard | M4 | IMPLEMENTED |
| 6 | M6: Trust Layer | Diff preview, Project Pages, Weekly Review, Audit Log | M5 | IMPLEMENTED |
| 7 | M7: Vault Intelligence | Time Machine, Contradiction Finder, Agent Debate, Dormant Radar, Operating Manual | M6 | IMPLEMENTED |

## Interface Contracts
### Obsidian API Endpoint (`/query`)
- **Method**: `POST`
- **Path**: `/query`
- **Request Body**: `{"note_title": "...", "content": "...", "query": "..."}`
- **Response**: `{"answer": "..."}`
- **Port**: `ORANGE_PORT`, default `8080`

### Settings Configuration
- File: `config/settings.json`
- Key: `"telegram_daemon"` ("ON" / "OFF")

### Memory Editor
- `api_get_memory_items(limit)`
- `api_update_memory_item(message_id, is_pinned, exclude_from_rag)`
- `api_delete_memory_item(message_id)`

### Smart Inbox
- `api_get_inbox_proposals()`
- `api_apply_inbox_proposal(file_path, category)`
- Watcher callback: `addSmartInboxProposal(proposal)`

### Morning Dashboard
- `api_get_morning_dashboard()`

### Trust Layer
- `api_get_project_pages_preview()`
- `api_apply_project_pages()`
- `api_get_weekly_review_preview()`
- `api_apply_weekly_review()`
- `api_get_audit_log(limit)`

### Vault Intelligence
- `api_get_vault_time_machine(days)`
- `api_find_contradictions()`
- `api_run_agent_debate(topic)`
- `api_get_dormant_projects(stale_days)`
- `api_get_operating_manual()`

### JS Bridge / System Panics
- **Method**: `window.pywebview.api.trigger_panic(msg)` or evaluate JS: `triggerSystemPanic(msg)`
- **Z-Index**: `999999` for `#system-panic-modal`

### JS Bridge / Command Execution Override
- **Method**: `await request_execution_override(cmd)`
- **JS Call**: `showExecutionOverride(cmd)`
- **Approval Callback**: `api_handle_override_response(approved: bool)` resolving async Future.
