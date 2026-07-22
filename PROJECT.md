# Project: ORANGE `orangeV2`

## Current Shape

ORANGE is a local-first AI workspace around an Obsidian vault. The `orangeV2`
branch combines chat, vault search, pydantic-graph agent flow, Smart Inbox,
Memory Editor, Knowledge Graph v2, Audit Log, Morning Dashboard, and Vault
Intelligence views.

## Runtime Architecture

1. `main.py` loads settings, starts the background asyncio loop, binds the local
   HTTP API from `ORANGE_PORT`, and stores the actual bound endpoint in
   `BridgeAPI`.
2. `BridgeAPI` exposes stable `api_*` methods to `ui/main.js` and delegates
   chat, settings, attachment, agent, and vault feature work to services.
3. `AgentRunner` stores messages in SQLite, folds history, injects vault
   context, and runs the FSM in `core/graph.py`.
4. Tools in `core/tools.py` perform vault reads, approved diff-based writes,
   memory search, web research, and restricted Python execution.
5. `mcp_servers/index.ts` exposes `list_notes`, `read_note`, and `write_note`
   over stdio with resolved vault path validation.

## Implemented Product Areas

- Stable local HTTP API: `/query`, `/api/graph`, `/api/note`.
- Knowledge Graph v2: note preview, node types, orphan filtering, suggested
  wikilinks.
- Memory Editor: pin, exclude from RAG, delete.
- Smart Inbox: file classification proposals and user-confirmed apply.
- Morning Dashboard: today, overdue, Telegram, orphan notes, focus items.
- Project Pages and Weekly Review: diff preview before writing.
- Audit Log: approvals, backups, memory edits, inbox, and vault writes.
- Vault Intelligence: Time Machine, Contradiction Finder, Agent Debate,
  Dormant Radar, Operating Manual.

## Defaults

- Python runtime: `3.11`.
- HTTP port: `8080`, configurable through `ORANGE_PORT`.
- Fixture vault: `examples/test_vault`.
- Auto backup: `OFF`.
- Auto push: `OFF`.
- Dangerous writes and code execution require explicit user approval.
