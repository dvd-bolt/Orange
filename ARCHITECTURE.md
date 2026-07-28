# ORANGE Architecture

## Runtime Flow

1. `main.py` loads `.env`, creates the background asyncio loop, loads settings,
   starts the local HTTP server, and stores the actual bound endpoint in
   `BridgeAPI`.
2. `BridgeAPI` is attached to the `pywebview` window and exposes methods used by
   `ui/main.js`. It is intentionally a thin facade over services.
3. The UI sends messages through `run_agent(profile, prompt, attachments)`.
4. `AgentRunner` validates provider configuration before creating a chat,
   stores the user message, builds a bounded history that keeps pinned memory,
   injects relevant vault notes via hybrid search, and runs the pydantic graph.
5. The FSM in `core/graph.py` performs real web collection for Deep Research
   when requested, drafts the answer with a model and finalizes it. Python code
   is never executed as part of this flow.
6. Tools in `core/tools.py` give the agent vault read/write, memory search, web
   research, note export, and restricted Python execution.
7. Runtime UI settings live in `config/settings.json` and are managed through
   `core/runtime_settings.py`.

## Key Subsystems

- UI shell: `ui/index.html`, `ui/style.css`
- UI modules: `ui/bridge_client.js`, `chat.js`, `settings.js`,
  `feature_dialogs.js`, `graph.js`, with `main.js` retaining shared window
  controls and compatibility globals
- Python bridge and agent: `core/bridge.py`, `core/agent.py`, `core/graph.py`
- Services: `core/services/chat_service.py`, `settings_service.py`,
  `attachment_service.py`, `agent_runner.py`, `inbox_service.py`,
  `dashboard_service.py`, `project_pages_service.py`,
  `weekly_review_service.py`, `write_preview_service.py`
- Vault intelligence: `core/services/vault_intelligence_service.py`
- Storage: SQLite through `core/db.py`
- Vault paths: one Python `VaultPathResolver` used by reads, scans and writes
- Vault search: Obsidian CLI when available, deterministic local text search,
  plus optional Gemini embeddings combined with reciprocal-rank fusion
- HTTP API: local `ThreadingHTTPServer` bound from `ORANGE_PORT` with fallback
  to the next free port, exposing `/query`, `/api/graph`, and `/api/note`
- MCP: `mcp_servers/index.ts`
- Native acceleration: `orange_core/src/lib.rs`
- Attachments: native file selection copies documents into the private
  `.orange_runtime/attachments/` staging directory; `AgentRunner` never reads
  attachment paths outside it

## Product Services

- Memory Editor reads and updates message flags in SQLite. `exclude_from_rag`
  messages are skipped by memory search.
- Smart Inbox watches `_Inbox`, creates proposals, and writes only after the UI
  confirms an action.
- Knowledge Graph v2 enriches nodes with path, type, degree, orphan status, and
  suggested wikilinks.
- Morning Dashboard scans Markdown tasks and graph metadata for a daily view.
- Project Pages generates overview pages under `_Orange/Project Pages/`.
- Weekly Review generates one report under `_Orange/Reviews/` for the current
  ISO week.
- Write Preview builds unified diffs before applying vault writes.
- Audit Log is stored in SQLite through `core/db.py`.
- Vault Intelligence is a local analysis layer for Time Machine,
  Contradiction Finder, Dormant Project Radar, and Personal Operating Manual.
  Agent Debate is intentionally `NOT_CONFIGURED` until a real independent
  multi-call runner exists; static debate output was removed.

## Defaults

- HTTP port: `8080`
- Vault path: `examples/test_vault`
- Auto backup: off
- Auto push: off
