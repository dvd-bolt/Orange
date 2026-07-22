# ORANGE Security Notes

## Vault Path Safety

Python vault tools normalize paths and use `os.path.commonpath` to keep reads
and writes inside the configured Obsidian vault.

The MCP server resolves every requested note path against the vault root and
rejects `../` traversal before reading or writing.

## Restricted Python Executor

`execute_python` now runs only after explicit user approval. Before execution it:

- parses the code with AST
- allows only calculation-oriented imports
- blocks filesystem, process, network, and introspection APIs
- runs code in `.orange_runtime/sandbox/`
- uses Python isolated mode
- limits execution to 10 seconds
- truncates stdout/stderr to 50 KB

This is a restricted subprocess, not a VM boundary. Treat it as a safer local
developer tool, not as a secure multi-tenant sandbox.

## Markdown Rendering

Agent Markdown is sanitized in the UI with DOMPurify before insertion into the
DOM. System messages are escaped.

## Git Backup

Automatic vault backup is off by default. Auto-push is also off by default.
Manual local backup can be triggered from Settings. Remote push only happens
when `auto_push_enabled` is explicitly set to `ON`.

## Smart Inbox

The watcher no longer runs background vault modifications after each inbox file
change. It sends a proposal to the UI, and `InboxService.apply_proposal` writes
only after user confirmation.

## Diff Preview Before Writes

Agent tools that rewrite notes, add tasks, export chats, expand note links, or
patch note content build a unified diff first and request explicit UI approval
before applying the write. Generated Project Pages and Weekly Reviews are also
shown as diff previews in the UI before writing to `_Orange/`.

## Audit Log

`audit_log` in SQLite records proposals, approvals, denials, applied writes,
manual backups, memory edits, Smart Inbox actions, Project Pages, and Weekly
Review exports. It is available from the Audit Log UI.

## Memory Controls

Memory Editor can mark messages as `exclude_from_rag`. Those messages remain in
the local chat history until deleted, but `search_memory` skips them.
