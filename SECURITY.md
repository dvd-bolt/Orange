# ORANGE Security Notes

## Vault Path Safety

Python vault operations use `core/path_safety.py::VaultPathResolver`. It
resolves physical paths, rejects `../` and symlink escapes, supports duplicate
filenames without guessing, and bounds note reads.

The MCP server uses the equivalent TypeScript resolver and rejects absolute
paths, traversal and symlink components before reading or writing. The
in-process agent MCP proxy exposes only `list_notes` and `read_note`; automatic
MCP writes are denied and audited.

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
DOM. If the sanitizer is unavailable, Markdown falls back to escaped plain
text. System messages and vault-derived fields are escaped.

## Attachments

Native file selection copies supported documents into
`.orange_runtime/attachments/` with random names and private permissions.
Agent runs reject external paths and symlinks. PDF range extraction accepts
only a short-lived staged PDF selected through the native dialog. Submitted,
discarded, and stale staged files are removed automatically.

## Git Backup

Automatic vault backup is off by default. Auto-push is also off by default.
Manual local backup can be triggered from Settings. Empty commits are skipped,
Git identity is never rewritten, and remote push only happens
when `auto_push_enabled` is explicitly set to `ON`.

## Smart Inbox

The watcher debounces duplicate events, ignores ORANGE-owned writes and sends a
proposal to the UI. A proposal is bound to the source path and content hash;
changed notes become `STALE_PREVIEW` and must be reviewed again.

## Diff Preview Before Writes

Agent tools that rewrite notes, add tasks, export chats, expand note links, or
patch note content build a unified diff first and request explicit UI approval
before applying the write. Generated Project Pages and Weekly Reviews are also
shown as diff previews in the UI before writing to `_Orange/`. Previews carry a
unique ID and before/after hashes; Apply writes the shown content and refuses a
stale or reused preview.

## Local HTTP API

The server binds only to `127.0.0.1`. `/query` enforces body and field limits,
a read timeout, an agent deadline and a 1 MB response limit. Public failures use
stable error codes and never return tracebacks. Requests with a non-loopback
`Host` or browser `Origin` are rejected to reduce DNS-rebinding and local API
cross-origin abuse.

## Audit Log

`audit_log` in SQLite records proposals, approvals, denials, applied writes,
manual backups, memory edits, Smart Inbox actions, Project Pages, and Weekly
Review exports. It is available from the Audit Log UI.

## Memory Controls

Memory Editor can mark messages as `exclude_from_rag`. Those messages remain in
the local chat history until deleted, but `search_memory` skips them.
