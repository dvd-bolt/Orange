import asyncio
import json
import os
import time

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


def test_audit_log_crud_uses_temp_database(tmp_path, monkeypatch):
    from core import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()
    event_id = db.add_audit_event("test", "proposed", "summary", "details")

    events = db.list_audit_events()
    assert events[0]["id"] == event_id
    assert events[0]["event_type"] == "test"
    assert events[0]["details"] == "details"


def test_write_preview_service_builds_diff_and_applies(tmp_path):
    from core.services.write_preview_service import WritePreviewService

    service = WritePreviewService(str(tmp_path))
    (tmp_path / "note.md").write_text("old\n", encoding="utf-8")

    plan = service.build_plan("note.md", "new\n", action="test")
    assert "--- a/note.md" in plan["diff"]
    assert "+++ b/note.md" in plan["diff"]
    assert "-old" in plan["diff"]
    assert "+new" in plan["diff"]

    asyncio.run(service.apply_plan(plan))
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "new\n"


def test_project_pages_service_previews_and_applies(tmp_path, monkeypatch):
    from core import db
    from core.services.project_pages_service import ProjectPagesService

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "roadmap.md").write_text("# Roadmap\n- [ ] Ship feature\nQuestion?\n", encoding="utf-8")

    service = ProjectPagesService(str(tmp_path))
    preview = service.preview_project_pages()
    assert preview["status"] == "success"
    assert preview["count"] == 1
    assert any("Project Pages" in plan["relative_path"] for plan in preview["plans"])

    result = asyncio.run(service.apply_project_pages())
    assert result["status"] == "success"
    assert (tmp_path / "_Orange" / "Project Pages" / "Roadmap.md").exists()


def test_weekly_review_service_previews_and_applies(tmp_path, monkeypatch):
    from core import db
    from core.services.weekly_review_service import WeeklyReviewService

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()
    (tmp_path / "daily.md").write_text("- [ ] Follow up 2020-01-01\n- [x] Done task\n", encoding="utf-8")

    service = WeeklyReviewService(str(tmp_path))
    preview = service.preview_weekly_review()
    assert preview["status"] == "success"
    assert "Weekly Review" in preview["plan"]["relative_path"]
    assert "Overdue" in preview["plan"]["new_content"]

    result = asyncio.run(service.apply_weekly_review())
    assert result["status"] == "success"
    assert (tmp_path / "_Orange" / "Reviews").exists()


def test_vault_intelligence_service_reports_core_views(tmp_path, monkeypatch):
    from core import db
    from core.services.vault_intelligence_service import VaultIntelligenceService

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()

    projects = tmp_path / "projects"
    projects.mkdir()
    roadmap = projects / "roadmap.md"
    roadmap.write_text(
        "# Roadmap\n"
        "Decision: use local storage for backup\n"
        "- [ ] Ship safer write flow\n"
        "[[manual]]\n",
        encoding="utf-8",
    )
    conflict = tmp_path / "manual.md"
    conflict.write_text(
        "# Manual\n"
        "Decision: do not use local storage for backup\n"
        "- [x] Ship safer write flow\n",
        encoding="utf-8",
    )
    old_project = projects / "legacy.md"
    old_project.write_text("# Legacy Project\n- [ ] Decide archive path\n", encoding="utf-8")
    old_time = time.time() - 90 * 24 * 60 * 60
    os.utime(old_project, (old_time, old_time))

    service = VaultIntelligenceService(str(tmp_path))

    time_machine = service.build_time_machine()
    assert time_machine["status"] == "success"
    assert time_machine["total_notes"] == 3
    assert time_machine["themes"]

    contradictions = service.find_contradictions()
    assert contradictions["status"] == "success"
    assert any(item["type"] == "policy_conflict" for item in contradictions["findings"])
    assert any(item["type"] == "task_state_conflict" for item in contradictions["findings"])

    debate = service.run_agent_debate("backup storage")
    assert debate["status"] == "success"
    assert [round_item["role"] for round_item in debate["rounds"]] == ["Engineer", "Strategist", "Skeptic"]

    dormant = service.find_dormant_projects(stale_days=30)
    assert dormant["items"]
    assert dormant["items"][0]["path"].endswith("legacy.md")

    manual = service.build_operating_manual()
    assert manual["status"] == "success"
    assert manual["manual"]["principles"]


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
        "api_run_git_backup",
        "api_get_project_pages_preview",
        "api_apply_project_pages",
        "api_get_weekly_review_preview",
        "api_apply_weekly_review",
        "api_get_audit_log",
        "api_get_vault_time_machine",
        "api_find_contradictions",
        "api_run_agent_debate",
        "api_get_dormant_projects",
        "api_get_operating_manual",
    }

    missing = [name for name in expected_methods if not hasattr(BridgeAPI, name)]
    assert missing == []


def test_scenario_engine_blocks_traversal_and_unsafe_eval(tmp_path):
    from core.scenario import ScenarioEngine

    engine = ScenarioEngine(str(tmp_path))
    class AllowDeps:
        async def request_override(self, _text):
            return True

    scenario = {
        "name": "safe",
        "steps": [
            {"id": "ctx", "action": "set_context", "params": {"ready": True}},
            {"id": "route", "action": "conditional_route", "params": {"condition": "ready", "if_true": "END", "if_false": "END"}},
        ],
    }
    result = asyncio.run(engine.run_scenario(json.dumps(scenario), deps=object()))
    assert result["status"] == "success"

    bad_path = {
        "name": "bad_path",
        "steps": [{"id": "write", "action": "write_file", "params": {"path": "../secret.md", "content": "x"}}],
    }
    result = asyncio.run(engine.run_scenario(json.dumps(bad_path), deps=AllowDeps()))
    assert result["status"] == "error"

    safe_write_without_approval = {
        "name": "no_approval",
        "steps": [{"id": "write", "action": "write_file", "params": {"path": "note.md", "content": "x"}}],
    }
    result = asyncio.run(engine.run_scenario(json.dumps(safe_write_without_approval), deps=object()))
    assert result["status"] == "denied"

    bad_eval = {
        "name": "bad_eval",
        "steps": [{"id": "eval", "action": "evaluate_expression", "params": {"expression": "__import__('os').system('echo no')"}}],
    }
    result = asyncio.run(engine.run_scenario(json.dumps(bad_eval), deps=object()))
    assert result["status"] == "error"
