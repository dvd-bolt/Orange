# ORANGE Architecture

## Runtime Flow

1. `main.py` loads `.env`, creates the background asyncio loop, loads settings,
   indexes the Obsidian vault, and starts the local HTTP server.
2. `BridgeAPI` is attached to the `pywebview` window and exposes methods used by
   `ui/main.js`. It is intentionally a thin facade over services.
3. The UI sends messages through `run_agent(profile, prompt, attachments)`.
4. `AgentRunner` stores the user message in SQLite, folds long history, injects
   relevant vault notes via hybrid search, and runs the pydantic graph.
5. The FSM in `core/graph.py` drafts an answer, verifies Python code blocks when
   present, and finalizes the response.
6. Tools in `core/tools.py` give the agent vault read/write, memory search, web
   research, note export, and restricted Python execution.
7. Runtime UI settings live in `config/settings.json` and are managed through
   `core/runtime_settings.py`.

## Key Subsystems

- UI: `ui/index.html`, `ui/main.js`, `ui/style.css`
- Python bridge and agent: `core/bridge.py`, `core/agent.py`, `core/graph.py`
- Services: `core/services/chat_service.py`, `settings_service.py`,
  `attachment_service.py`, `agent_runner.py`, `inbox_service.py`,
  `dashboard_service.py`, `project_pages_service.py`,
  `weekly_review_service.py`, `write_preview_service.py`
- Vault intelligence: `core/services/vault_intelligence_service.py`
- Storage: SQLite through `core/db.py`
- Vault search: BM25 plus optional Gemini embeddings
- HTTP API: local `ThreadingHTTPServer` bound from `ORANGE_PORT`, exposing
  `/query`, `/api/graph`, and `/api/note`
- MCP: `mcp_servers/index.ts`
- Native acceleration: `orange_core/src/lib.rs`

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
- Vault Intelligence is a local analysis layer that builds Time Machine,
  Contradiction Finder, Agent Debate, Dormant Project Radar, and Personal
  Operating Manual views without requiring an LLM call.

## Defaults

- HTTP port: `8080`
- Vault path: `examples/test_vault`
- Auto backup: off
- Auto push: off
