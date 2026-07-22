def test_graph_endpoint_handler_shape(tmp_path):
    from core.graph_api import get_notes_graph

    (tmp_path / "daily.md").write_text("[[project]]", encoding="utf-8")
    (tmp_path / "project.md").write_text("# Project", encoding="utf-8")

    graph = get_notes_graph(str(tmp_path))
    assert "nodes" in graph
    assert "links" in graph
