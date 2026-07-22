import json
from pathlib import Path

import pytest


def test_validate_path_rejects_traversal(tmp_path):
    pytest.importorskip("pydantic_ai")
    from core.tools import validate_path

    vault = tmp_path / "vault"
    vault.mkdir()

    assert validate_path(str(vault), "note.md") == str(vault / "note.md")
    with pytest.raises(ValueError):
        validate_path(str(vault), "../outside.md")


def test_append_task_to_markdown_preserves_existing_content():
    pytest.importorskip("mistletoe")
    from core.markdown_ops import append_task_to_markdown

    source = "# Project\n\n## Backlog\n- [ ] Existing\n\n## Done\nComplete\n"
    result = append_task_to_markdown(source, "New task")

    assert "- [ ] Existing" in result
    assert "- [ ] New task" in result
    assert "## Done" in result


def test_db_crud_uses_temp_database(tmp_path, monkeypatch):
    from core import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()

    chat_id = db.create_chat("Temp")
    db.add_message(chat_id, "user", "hello searchable memory")

    assert db.get_chat_history(chat_id)[0]["content"] == "hello searchable memory"
    assert db.search_messages("searchable")[0]["chat_id"] == chat_id
    assert db.delete_chat(chat_id) is True
    assert db.get_chat_history(chat_id) == []


def test_chat_service_delegates_to_db(tmp_path, monkeypatch):
    from core import db
    from core.services.chat_service import ChatService

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()

    service = ChatService()
    chat_id = service.create_chat("Service")
    assert service.rename_chat(chat_id, "Renamed") is True
    assert service.list_chats()[0]["title"] == "Renamed"
    assert service.delete_chat(chat_id) is True


def test_graph_api_extracts_wikilinks(tmp_path):
    from core.graph_api import get_notes_graph

    (tmp_path / "A.md").write_text("[[B]]", encoding="utf-8")
    (tmp_path / "B.md").write_text("Back", encoding="utf-8")

    graph = get_notes_graph(str(tmp_path))
    assert {node["id"] for node in graph["nodes"]} == {"A", "B"}
    assert graph["links"] == [{"source": "A", "target": "B", "value": 1}]


def test_reciprocal_rank_fusion_orders_shared_results():
    pytest.importorskip("pydantic_ai")
    from core.hybrid_search import reciprocal_rank_fusion

    result = reciprocal_rank_fusion(["a.md", "b.md"], ["b.md", "c.md"])
    assert result[0][0] == "b.md"


def test_runtime_settings_backfill_and_save(tmp_path):
    from core.runtime_settings import load_runtime_settings, save_runtime_settings

    settings_path = tmp_path / "settings.json"
    saved = save_runtime_settings({"language": "en"}, settings_path)
    loaded = load_runtime_settings(settings_path)

    assert saved["language"] == "en"
    assert loaded["auto_backup_enabled"] == "OFF"
    assert json.loads(settings_path.read_text(encoding="utf-8"))["language"] == "en"
