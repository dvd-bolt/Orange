# ORANGE

Local-first AI workspace for Obsidian: chat, vault search, graph exploration,
Smart Inbox, memory controls, audit log, and local automation.

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
PY
```

Create local config:

```bash
cp .env.example .env
```

Set at least one model API key in `.env`:

```env
GOOGLE_API_KEY=
OBSIDIAN_VAULT_PATH=examples/test_vault
ORANGE_PORT=8080
MCP_SERVER_URL=
```

## Run

```bash
python main.py
```

If `ORANGE_PORT` is occupied, ORANGE binds the next free local port and exposes
the actual `http_base_url` through `BridgeAPI.api_get_system_status()`.

## Checks

```bash
python3.11 -m compileall -q main.py core integrations tests
pytest
node --check ui/main.js
cd orange_core && cargo check
cd ../mcp_servers && bun install && bunx tsc --noEmit
```

## Safety Defaults

- Auto backup: `OFF`
- Auto push: `OFF`
- Python execution: requires explicit user approval and restricted validation
- Vault writes: diff preview plus approval for agent tools
- Fixture vault: `examples/test_vault`
