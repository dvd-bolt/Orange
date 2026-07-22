# ORANGE

ORANGE is a local desktop AI assistant for Obsidian. It combines a `pywebview`
UI, a Python agent core, SQLite memory, local vault search, a small HTTP API,
an optional MCP server, and a Rust/PyO3 acceleration module.

## Requirements

- Python 3.11
- Rust toolchain for `orange_core`
- Bun for the optional MCP server
- Google Gemini API key for LLM features

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install

cd orange_core
maturin develop --release
cd ..

cp .env.example .env
```

Edit `.env` and set at least `GOOGLE_API_KEY`. `ORANGE_PORT` defaults to `8080`.
If the port is busy, ORANGE will bind the next available port and expose the
actual URL through the UI bridge.

## Run

```bash
python main.py
```

The local HTTP API exposes:

- `POST /query` for Obsidian note-context questions
- `GET /api/graph` for the knowledge graph data
- `GET /api/note?path=...` for a safe in-vault note preview

## Optional MCP Server

```bash
cd mcp_servers
bun install
OBSIDIAN_VAULT_PATH=../examples/test_vault bun run index.ts
```

The MCP server provides `list_notes`, `read_note`, and `write_note`.

## Validation

```bash
python -m compileall main.py check_models.py core integrations tests
pytest
node --check ui/main.js
cd orange_core && cargo check
cd ../mcp_servers && bun install && bunx tsc --noEmit
```

If `orange_core` is not built, Python fallback paths keep basic vault tools
working more slowly and report the build command in tool output.

## Implemented Product Surfaces

- Command Palette: `Cmd+K` / `Ctrl+K`
- Memory Editor: pin messages, delete messages, and exclude messages from RAG
- Smart Inbox: classifies `_Inbox` notes and applies changes only after confirmation
- Knowledge Graph v2: filters, clickable nodes, note previews, wikilink suggestions
- Morning Dashboard: today tasks, overdue tasks, Telegram tasks, orphan notes, focus list
- Diff Preview: vault writes show a unified diff before agent/tool changes are applied
- Project Pages: generated `_Orange/Project Pages/` summaries for project notes
- Weekly Review: generated `_Orange/Reviews/` weekly vault report
- Audit Log: local action history for proposals, approvals, writes, backups, and memory edits
- Vault Time Machine: filesystem-based activity timeline, themes, quiet notes, bursts
- Contradiction Finder: possible conflicting decisions and task-state conflicts
- Agent Debate: local Engineer / Strategist / Skeptic debate from vault context
- Dormant Project Radar: stale project notes with open loops and revive actions
- Personal Operating Manual: generated working rules for using ORANGE and the vault
