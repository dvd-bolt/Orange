from pathlib import Path

import pytest


def test_graph_endpoint_handler_shape(tmp_path):
    from core.graph_api import get_notes_graph

    (tmp_path / "daily.md").write_text("[[project]]", encoding="utf-8")
    (tmp_path / "project.md").write_text("# Project", encoding="utf-8")

    graph = get_notes_graph(str(tmp_path))
    assert "nodes" in graph
    assert "links" in graph


def test_note_payload_blocks_traversal_and_returns_preview(tmp_path):
    pytest.importorskip("webview")
    from main import build_note_payload

    (tmp_path / "daily.md").write_text("[[project]]\nMention orphan", encoding="utf-8")
    (tmp_path / "project.md").write_text("# Project", encoding="utf-8")
    payload = build_note_payload(str(tmp_path), "daily.md")

    assert payload["title"] == "daily"
    assert payload["path"] == "daily.md"
    assert "[[project]]" in payload["content"]
    assert "suggested_links" in payload

    with pytest.raises(ValueError):
        build_note_payload(str(tmp_path), "../secret.md")


def test_mcp_server_uses_resolved_vault_paths():
    source = Path("mcp_servers/index.ts").read_text(encoding="utf-8")

    assert "function resolveVaultPath" in source
    assert "relative(VAULT_ROOT, fullPath)" in source
    assert "startsWith(VAULT_PATH)" not in source
