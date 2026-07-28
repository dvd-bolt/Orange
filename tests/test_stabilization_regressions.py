import asyncio
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from core import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()
    return db


def test_vault_resolver_blocks_symlink_escapes_and_ambiguous_names(tmp_path):
    from core.path_safety import AmbiguousVaultPathError, VaultPathError, VaultPathResolver

    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    (vault / "one").mkdir(parents=True)
    (vault / "two").mkdir()
    outside.mkdir()
    (vault / "one" / "same.md").write_text("one", encoding="utf-8")
    (vault / "two" / "same.md").write_text("two", encoding="utf-8")
    (outside / "secret.md").write_text("secret", encoding="utf-8")
    (vault / "file-link.md").symlink_to(outside / "secret.md")
    (vault / "dir-link").symlink_to(outside, target_is_directory=True)

    resolver = VaultPathResolver(vault)
    with pytest.raises(VaultPathError):
        resolver.resolve_note("../outside/secret.md", must_exist=True)
    with pytest.raises(VaultPathError):
        resolver.resolve_note("file-link.md", must_exist=True)
    with pytest.raises(VaultPathError):
        resolver.resolve_note("dir-link/secret.md", must_exist=True)
    with pytest.raises(AmbiguousVaultPathError):
        resolver.resolve_note("same.md", must_exist=True, search_by_name=True)

    listed = [resolver.relative(path) for path in resolver.iter_notes()]
    assert listed == ["one/same.md", "two/same.md"]


def test_obsidian_cli_uses_argument_exec_and_filters_traversal(monkeypatch):
    from core import markdown_ops

    captured = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"[]", b""

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(
        markdown_ops.run_obsidian_cli(
            ["search", "query=$(touch /tmp/orange-command-injection)"]
        )
    )

    assert result == "[]"
    assert captured["args"] == (
        "obsidian",
        "search",
        "query=$(touch /tmp/orange-command-injection)",
    )
    assert "shell" not in captured["kwargs"]
    assert not markdown_ops._is_safe_note_path("../secret.md")
    assert not markdown_ops._is_safe_note_path("/tmp/secret.md")
    assert markdown_ops._is_safe_note_path("projects/roadmap.md")


def test_python_mcp_client_uses_bun_for_typescript_without_forwarding_secrets(
    tmp_path,
    monkeypatch,
):
    from core.mcp_client import ObsidianMCPClient
    import core.mcp_client as mcp_client_module

    server = tmp_path / "index.ts"
    server.write_text("export {};", encoding="utf-8")
    monkeypatch.setattr(
        mcp_client_module.shutil,
        "which",
        lambda name: "/usr/local/bin/bun" if name == "bun" else None,
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "examples/test_vault")

    params = ObsidianMCPClient(str(server))._stdio_server_parameters()

    assert params.command == "/usr/local/bin/bun"
    assert params.args == ["run", str(server.resolve())]
    assert params.env["OBSIDIAN_VAULT_PATH"] == "examples/test_vault"
    assert "GOOGLE_API_KEY" not in params.env
    assert "OPENROUTER_API_KEY" not in params.env


def test_write_preview_rejects_stale_tampered_and_reused_plans(tmp_path):
    from core.services.write_preview_service import (
        PreviewStateError,
        StalePreviewError,
        WritePreviewService,
    )

    service = WritePreviewService(str(tmp_path))
    note = tmp_path / "note.md"
    note.write_text("before\n", encoding="utf-8")

    stale = service.build_plan("note.md", "after\n")
    note.write_text("changed elsewhere\n", encoding="utf-8")
    with pytest.raises(StalePreviewError):
        asyncio.run(service.apply_plan(stale))
    assert stale["status"] == "stale"
    assert note.read_text(encoding="utf-8") == "changed elsewhere\n"

    tampered = service.build_plan("note.md", "shown\n")
    tampered["new_content"] = "not shown\n"
    with pytest.raises(PreviewStateError):
        asyncio.run(service.apply_plan(tampered))
    assert note.read_text(encoding="utf-8") == "changed elsewhere\n"

    valid = service.build_plan("note.md", "applied\n")
    asyncio.run(service.apply_plan(valid))
    with pytest.raises(PreviewStateError):
        asyncio.run(service.apply_plan(valid))
    assert note.read_text(encoding="utf-8") == "applied\n"


def test_write_tool_does_not_modify_note_without_approval(tmp_path, isolated_db):
    from core.tools import rewrite_file

    note = tmp_path / "note.md"
    note.write_text("before", encoding="utf-8")

    async def deny(_command):
        return False

    context = SimpleNamespace(
        deps=SimpleNamespace(
            obsidian_vault_path=str(tmp_path),
            request_override=deny,
        )
    )
    result = asyncio.run(rewrite_file(context, "note.md", "after"))

    assert "Отклонено" in result
    assert note.read_text(encoding="utf-8") == "before"
    assert isolated_db.list_audit_events()[0]["status"] == "denied"


def test_inbox_nested_dedup_stale_and_reprocess_after_change(tmp_path):
    from core.services.inbox_service import InboxService

    nested = tmp_path / "_Inbox" / "nested"
    nested.mkdir(parents=True)
    note = nested / "идея.md"
    note.write_text("Идея проекта с roadmap", encoding="utf-8")
    service = InboxService(str(tmp_path))

    first = service.build_proposal(str(note))
    duplicate = service.build_proposal(str(note))
    assert first["proposal_id"] == duplicate["proposal_id"]
    assert service.list_proposals()[0]["relative_path"] == "_Inbox/nested/идея.md"

    note.write_text("Идея проекта изменилась", encoding="utf-8")
    stale = asyncio.run(
        service.apply_proposal(
            str(note),
            first["category"],
            first["proposal_id"],
        )
    )
    assert stale["error_code"] == "STALE_PREVIEW"
    assert not (tmp_path / "_Inbox" / "Inbox Review.md").exists()

    current = service.build_proposal(str(note))
    applied = asyncio.run(
        service.apply_proposal(
            str(note),
            current["category"],
            current["proposal_id"],
        )
    )
    assert applied["outcome"] == "applied"
    assert service.list_proposals() == []

    note.write_text("Идея проекта изменилась снова", encoding="utf-8")
    refreshed = service.list_proposals()
    assert len(refreshed) == 1
    assert refreshed[0]["content_hash"] != current["content_hash"]


def test_watcher_debounces_and_ignores_orange_writes(tmp_path):
    from core.watcher import ObsidianWatcher
    from core.write_activity import mark_orange_write

    calls = []
    api = SimpleNamespace(
        _window=None,
        propose_inbox_review=lambda path: calls.append(path),
    )
    watcher = ObsidianWatcher(api)
    note = tmp_path / "capture.md"
    note.write_text("capture", encoding="utf-8")
    event = SimpleNamespace(is_directory=False, src_path=str(note))

    watcher.on_modified(event)
    watcher.on_modified(event)
    assert calls == [str(note.resolve())]

    own_note = tmp_path / "orange.md"
    own_note.write_text("orange", encoding="utf-8")
    mark_orange_write(own_note)
    watcher.on_modified(
        SimpleNamespace(is_directory=False, src_path=str(own_note))
    )
    assert calls == [str(note.resolve())]


def test_memory_fallback_honors_pin_exclusion_and_delete_cleanup(
    isolated_db,
):
    from core.tools import search_memory

    chat_id = isolated_db.create_chat("Memory")
    pinned_id = isolated_db.add_message(chat_id, "user", "literal 100% memory")
    excluded_id = isolated_db.add_message(chat_id, "model", "literal 100% secret")
    isolated_db.update_message_memory_flags(pinned_id, is_pinned=True)
    isolated_db.update_message_memory_flags(excluded_id, exclude_from_rag=True)
    isolated_db.save_cached_embedding(
        pinned_id,
        json.dumps([1.0, 0.0]),
        "model-a",
    )
    assert isolated_db.get_cached_embedding(pinned_id, "model-b") is None

    context = SimpleNamespace(
        deps=SimpleNamespace(
            settings=SimpleNamespace(gemini_api_key=None),
        )
    )
    result = asyncio.run(search_memory(context, "100%"))
    assert "literal 100% memory" in result
    assert "[PINNED]" in result
    assert "secret" not in result

    assert isolated_db.delete_message(pinned_id)
    assert isolated_db.get_cached_embedding(pinned_id) is None
    assert isolated_db.search_messages("memory") == []


def test_audit_log_redacts_credentials_and_caps_details(isolated_db):
    fake_google_key = "AIza" + ("A" * 32)
    fake_github_token = "ghp_" + ("a" * 36)
    isolated_db.add_audit_event(
        "security",
        "denied",
        "Authorization: Bearer very-secret-token",
        (
            f"api_key={fake_google_key} "
            f"token={fake_github_token} "
            + "x" * 5000
        ),
    )
    event = isolated_db.list_audit_events()[0]

    assert "very-secret-token" not in event["summary"]
    assert "AIza" not in event["details"]
    assert "ghp_" not in event["details"]
    assert "[REDACTED]" in event["details"]
    assert len(event["details"]) <= isolated_db.MAX_AUDIT_DETAILS_CHARS + 20


def test_dashboard_dates_paths_lines_dedup_and_focus_are_deterministic(tmp_path):
    from core.services.dashboard_service import DashboardService

    (tmp_path / "a.md").write_text(
        "# Tasks\n"
        "- [ ] Overdue 2020-01-01\n"
        "- [ ] Duplicate task\n",
        encoding="utf-8",
    )
    (tmp_path / "daily.md").write_text(
        "# Today\n"
        "- [ ] Today without date\n"
        "- [ ] Duplicate task\n",
        encoding="utf-8",
    )
    (tmp_path / "telegram.md").write_text(
        "- [ ] Telegram follow-up 2020-01-02\n",
        encoding="utf-8",
    )

    dashboard = DashboardService(str(tmp_path)).build_morning_dashboard()
    all_tasks = dashboard["overdue_tasks"] + dashboard["today_tasks"]

    assert dashboard["focus"][0] == "Overdue 2020-01-01"
    assert sum(item["text"] == "Duplicate task" for item in all_tasks) == 1
    assert any(
        item["file_path"] == "daily.md" and item["line"] == 2
        for item in dashboard["today_tasks"]
    )
    assert dashboard["telegram_tasks"][0]["file_path"] == "telegram.md"


def test_graph_supports_filename_collisions_aliases_and_reciprocal_links(tmp_path):
    from core.graph_api import get_notes_graph

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "Note.md").write_text("# A Note", encoding="utf-8")
    (tmp_path / "b" / "Note.md").write_text("# B Note", encoding="utf-8")
    (tmp_path / "a" / "Source.md").write_text("[[Note]]", encoding="utf-8")
    (tmp_path / "Alias.md").write_text(
        "---\naliases: [Road Map]\n---\n# Alias",
        encoding="utf-8",
    )
    (tmp_path / "Alias Source.md").write_text("[[Road Map]]", encoding="utf-8")
    (tmp_path / "First.md").write_text("[[Second]]", encoding="utf-8")
    (tmp_path / "Second.md").write_text("[[First]]", encoding="utf-8")
    (tmp_path / "API.md").write_text("# API", encoding="utf-8")
    (tmp_path / "Suggestion Source.md").write_text(
        "A single API mention must not create a suggestion.",
        encoding="utf-8",
    )

    graph = get_notes_graph(str(tmp_path))
    nodes = {node["id"]: node for node in graph["nodes"]}
    pairs = {
        (link["source"], link["target"])
        for link in graph["links"]
    }

    assert {"a/Note", "b/Note"} <= set(nodes)
    assert ("a/Source", "a/Note") in pairs
    assert ("Alias Source", "Alias") in pairs
    assert sum(
        {link["source"], link["target"]} == {"First", "Second"}
        for link in graph["links"]
    ) == 1
    assert "Second" not in nodes["First"]["suggested_links"]
    assert "First" not in nodes["Second"]["suggested_links"]
    assert "API" not in nodes["Suggestion Source"]["suggested_links"]


def test_git_backup_skips_empty_commit_and_never_pushes_when_disabled(tmp_path):
    from core.git_backup import _sync_git_backup

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Orange Test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "orange@example.test"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "note.md").write_text("note", encoding="utf-8")

    first = _sync_git_backup(str(tmp_path), push=False)
    second = _sync_git_backup(str(tmp_path), push=False)

    assert first["status"] == "success_local_only"
    assert second["status"] == "no_changes"
    assert (
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "1"
    )
    assert (
        subprocess.run(
            ["git", "config", "user.name"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "Orange Test"
    )


def test_daemon_manager_stops_its_background_worker(monkeypatch):
    import asyncio
    import threading
    import time
    from types import SimpleNamespace

    from core import daemon_manager as daemon_module

    monkeypatch.setattr(
        daemon_module,
        "load_runtime_settings",
        lambda: {"telegram_daemon": "OFF"},
    )
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    api = SimpleNamespace(_background_loop=loop)
    manager = daemon_module.DaemonManager(api)

    try:
        manager.start()
        deadline = time.monotonic() + 2
        while manager._stop_event is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert manager._stop_event is not None
        manager.stop()
        assert manager.running is False
        assert manager.task is None
    finally:
        manager.stop()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()


def test_telegram_without_credentials_never_creates_notes(tmp_path, monkeypatch):
    from core.daemon_manager import DaemonManager

    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    monkeypatch.delenv("TELEGRAM_PHONE", raising=False)
    loop = asyncio.new_event_loop()
    api = SimpleNamespace(
        _background_loop=loop,
        _deps=SimpleNamespace(obsidian_vault_path=str(tmp_path)),
    )
    manager = DaemonManager(api)
    asyncio.run(manager._start_telegram_daemon())
    loop.close()

    assert manager.telegram_client == "NOT_CONFIGURED"
    assert list(tmp_path.rglob("TG_Task_*.md")) == []
