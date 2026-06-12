# Original User Request

## Initial Request — 2026-06-08T02:12:00+03:00

Implement three stages of features for the local AI agent "ORANGE" to support Obsidian integration, a background Telegram worker daemon, and a robust system audit.

Working directory: c:\orange
Integrity mode: development

## Requirements

### R1. Obsidian Integration
- Implement a bridge plugin/script in `integrations/obsidian/` (e.g., Python script or Obsidian-compatible JS automation) that reads the active note and communicates with the ORANGE server.
- Add an HTTP API endpoint (FastAPI or lightweight HTTP server) in the ORANGE python backend (`main.py` or a dedicated module) running on port 8000.
- Ensure the agent (via `core/markdown_ops.py` or MCP client) has direct, real-time read/write access to the local obsidian vault directory `test_vault/`.

### R2. Telegram Automation Daemon
- Create `core/daemon_manager.py` to control background workers.
- Implement a Telegram userbot daemon (using `Telethon` or a custom script) running asynchronously in a separate thread.
- The daemon must filter incoming messages, forward alerts into the UI `SYSTEM_TELEMETRY` pane via the bridge, and output markdown tasks directly to `test_vault/` inbox.
- Expose toggle switches in the Settings modal (`ui/index.html`) and persist settings to `config/settings.json` to enable/disable the Telegram worker.

### R3. UI Overlay Audit and Verification
- Audit and clean `core/bridge.py`, `ui/main.js`, and `ui/index.html` to remove any duplicates.
- Ensure `SYSTEM_PANIC` catches all Python core errors, displays the traceback, and blocks the UI.
- Ensure `EXECUTION_OVERRIDE` uses an async `Future` to prompt and await permission (`[ PERMIT ]` / `[ DENY ]`) without freezing the GUI.
- Run validation tests in `scratch/test_bugfixes.py` and `scratch/test_advanced.py` to verify system health.

## Acceptance Criteria

### Obsidian Integration
- [ ] An HTTP server runs on port 8000 when starting `main.py`.
- [ ] HTTP endpoint `/query` accepts JSON `{"note_title": "...", "content": "...", "query": "..."}` and returns the agent's answer.
- [ ] An automation script exists in `integrations/obsidian/` that queries the `/query` endpoint.

### Daemon Worker
- [ ] `core/daemon_manager.py` manages Telegram client connection lifecycles.
- [ ] settings in `config/settings.json` contain `"telegram_daemon": "ON"/"OFF"`.
- [ ] When enabled, background task listens to incoming events and appends them to the telemetry UI and `test_vault/`.

### UI Modal Checks
- [ ] Uncaught python exceptions evaluate `triggerSystemPanic` in JS with z-index `999999`.
- [ ] Command execution override pops up modal without GUI freezing and waits for user's approval.
