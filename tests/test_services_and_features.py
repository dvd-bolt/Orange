import asyncio

import pytest


def test_db_memory_flags_exclude_and_delete(tmp_path, monkeypatch):
    from core import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()

    chat_id = db.create_chat("Memory")
    message_id = db.add_message(chat_id, "model", "remember this fact")

    assert db.update_message_memory_flags(message_id, is_pinned=True, exclude_from_rag=True)
    item = db.list_memory_messages()[0]
    assert item["is_pinned"] == 1
    assert item["exclude_from_rag"] == 1

    assert db.delete_message(message_id)
    assert db.list_memory_messages() == []


def test_graph_api_adds_v2_metadata(tmp_path):
    from core.graph_api import get_notes_graph

    projects = tmp_path / "projects"
    projects.mkdir()
    (tmp_path / "_Inbox").mkdir()
    (tmp_path / "daily.md").write_text("[[roadmap]]\nMention orphan", encoding="utf-8")
    (projects / "roadmap.md").write_text("# Roadmap", encoding="utf-8")
    (tmp_path / "orphan.md").write_text("# Orphan", encoding="utf-8")
    (tmp_path / "_Inbox" / "capture.md").write_text("# Inbox", encoding="utf-8")

    graph = get_notes_graph(str(tmp_path))
    nodes = {node["id"]: node for node in graph["nodes"]}

    assert nodes["roadmap"]["type"] == "project"
    assert nodes["capture"]["type"] == "inbox"
    assert nodes["orphan"]["orphan"] is True
    assert nodes["daily"]["degree"] == 1


def test_inbox_service_classifies_and_applies_after_confirmation(tmp_path):
    from core.services.inbox_service import InboxService

    inbox = tmp_path / "_Inbox"
    inbox.mkdir()
    note = inbox / "capture.md"
    note.write_text("- [ ] сделать ревью проекта", encoding="utf-8")

    service = InboxService(str(tmp_path))
    proposal = service.build_proposal(str(note))
    assert proposal["category"] == "task"

    result = asyncio.run(service.apply_proposal(str(note), proposal["category"]))
    assert result["status"] == "success"
    assert "capture" in (inbox / "Inbox Review.md").read_text(encoding="utf-8")


def test_dashboard_service_builds_daily_snapshot(tmp_path):
    from core.services.dashboard_service import DashboardService

    (tmp_path / "daily.md").write_text("- [ ] Today task\n", encoding="utf-8")
    (tmp_path / "telegram_tasks.md").write_text("- [ ] Telegram follow-up 2020-01-01\n", encoding="utf-8")
    (tmp_path / "orphan.md").write_text("# Orphan", encoding="utf-8")

    dashboard = DashboardService(str(tmp_path)).build_morning_dashboard()

    assert dashboard["today_tasks"]
    assert dashboard["overdue_tasks"]
    assert dashboard["telegram_tasks"]
    assert dashboard["focus"]


def test_bridge_public_api_contract_includes_new_methods():
    pytest.importorskip("pydantic_ai")
    from core.bridge import BridgeAPI

    expected_methods = {
        "api_get_settings",
        "api_save_settings",
        "api_stage_file",
        "api_stage_pdf_with_range",
        "api_get_memory_items",
        "api_update_memory_item",
        "api_delete_memory_item",
        "api_get_inbox_proposals",
        "api_apply_inbox_proposal",
        "api_get_morning_dashboard",
        "api_get_http_base_url",
    }

    missing = [name for name in expected_methods if not hasattr(BridgeAPI, name)]
    assert missing == []
