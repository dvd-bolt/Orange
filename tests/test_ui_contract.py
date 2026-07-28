import re
from pathlib import Path


def test_ui_bridge_calls_exist_on_bridge_api():
    from core.bridge import BridgeAPI

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("ui/main.js"),
            Path("ui/chat.js"),
            Path("ui/settings.js"),
            Path("ui/feature_dialogs.js"),
            Path("ui/graph.js"),
            Path("ui/bridge_client.js"),
        )
    )
    api_names = set(
        re.findall(r"(?:window\.)?pywebview\.api\.(api_[A-Za-z0-9_]+)", sources)
    )
    bridge_client_names = set(
        re.findall(
            r"orangeBridge\.(?:call|json)\(\s*['\"]([A-Za-z0-9_]+)['\"]",
            sources,
        )
    )
    missing = sorted(
        name
        for name in api_names | bridge_client_names
        if not hasattr(BridgeAPI, name)
    )
    assert missing == []


def test_ui_has_no_automatic_python_execution_or_static_code_mock():
    html = Path("ui/index.html").read_text(encoding="utf-8")
    script = Path("ui/main.js").read_text(encoding="utf-8")

    assert "initialize_protocol" not in html
    assert "executeCodeFromModal" not in html
    assert "executeCodeWithApproval(codeText)" in script
    assert "api_execute_python(code)" in script
    assert "language-python" in script


def test_markdown_requires_sanitizer_and_scripts_load_in_dependency_order():
    html = Path("ui/index.html").read_text(encoding="utf-8")
    script = Path("ui/main.js").read_text(encoding="utf-8")

    assert "window.marked || !window.DOMPurify" in script
    assert "window.DOMPurify.sanitize" in script
    script_order = [
        'src="bridge_client.js"',
        'src="chat.js"',
        'src="settings.js"',
        'src="feature_dialogs.js"',
        'src="graph.js"',
        'src="main.js"',
    ]
    positions = [html.index(source) for source in script_order]
    assert positions == sorted(positions)


def test_ui_feature_functions_have_single_owners():
    module_paths = [
        Path("ui/main.js"),
        Path("ui/chat.js"),
        Path("ui/settings.js"),
        Path("ui/feature_dialogs.js"),
        Path("ui/graph.js"),
    ]
    owners = {}
    for path in module_paths:
        source = path.read_text(encoding="utf-8")
        for name in re.findall(
            r"^(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(",
            source,
            flags=re.MULTILINE,
        ):
            owners.setdefault(name, []).append(path.name)

    duplicates = {
        name: paths
        for name, paths in owners.items()
        if len(paths) > 1
    }
    assert duplicates == {}
    assert owners["sendToAgent"] == ["chat.js"]
    assert owners["openSettings"] == ["settings.js"]
    assert owners["openMemoryEditor"] == ["feature_dialogs.js"]
    assert owners["toggleKnowledgeGraph"] == ["graph.js"]
