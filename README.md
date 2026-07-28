# ORANGE

Local-first AI workspace for Obsidian: chat, vault search, graph exploration,
Smart Inbox, memory controls, audit log, and local automation.

ORANGE does not silently emulate unavailable integrations. Model-backed
actions return `NOT_CONFIGURED` until their key is present, and write actions
require an explicit preview/confirmation flow.

## Requirements

- Python 3.11
- Rust toolchain for `orange_core`
- Bun for the MCP server
- Playwright browser runtime

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install
```

Build the Rust extension into the active virtualenv:

```bash
cd orange_core
maturin develop --release
cd ..
python - <<'PY'
import orange_core
assert hasattr(orange_core, "scan_vault_fast")
notes = orange_core.scan_vault_fast("../examples/test_vault")
assert isinstance(notes, list) and notes
PY
```

Create local config:

```bash
cp .env.example .env
```

Set at least one model API key in `.env`:

```env
GOOGLE_API_KEY=
ORANGE_LITE_MODEL=google:gemini-3.5-flash-lite
ORANGE_HEAVY_MODEL=google:gemini-3.6-flash
OBSIDIAN_VAULT_PATH=examples/test_vault
ORANGE_PORT=8080
MCP_SERVER_URL=
ORANGE_AGENT_TIMEOUT_SECONDS=240
```

`OPENROUTER_API_KEY` is optional unless an OpenRouter model is selected.
To run the bundled MCP server, set
`MCP_SERVER_URL=mcp_servers/index.ts`; ORANGE starts TypeScript MCP paths with
Bun and forwards only the vault path and a minimal non-secret environment.
Deep Research uses the real `ddgs` search dependency and then the configured
heavy model. With no search provider or model key it returns a structured
error instead of a generated research result.

## Run

```bash
python main.py
```

If `ORANGE_PORT` is occupied, ORANGE binds the next free local port and exposes
the actual `http_base_url` through `BridgeAPI.api_get_system_status()`.

## Checks

```bash
python3.11 -m compileall -q main.py core integrations tests
python3.11 -m pytest -q
node --check ui/main.js
node --check ui/chat.js
node --check ui/settings.js
node --check ui/feature_dialogs.js
node --check ui/graph.js
node --check ui/bridge_client.js
cd orange_core && cargo fmt --check && cargo check
cd ../mcp_servers && bun install && bunx tsc --noEmit && bun test
cd .. && .venv/bin/pip check
```

## Safety Defaults

- Auto backup: `OFF`
- Auto push: `OFF`
- Python execution: requires explicit user approval and restricted validation
- Attachments: staged under `.orange_runtime/attachments`; external paths and
  symlinks are rejected
- Vault writes: diff preview plus approval for agent tools
- Agent-initiated MCP access: read-only (`list_notes`, `read_note`)
- HTTP `/query`: bounded request/response sizes and runtime timeout
- Fixture vault: `examples/test_vault`
