import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def make_runner(tmp_path, *, api_key=None):
    from core.services.agent_runner import AgentRunner

    loop = asyncio.new_event_loop()
    deps = SimpleNamespace(
        settings=SimpleNamespace(gemini_api_key=api_key),
        obsidian_vault_path=str(tmp_path),
        mcp_client=None,
        request_override=None,
    )
    runner = AgentRunner(loop, deps, lambda: None, lambda: None, lambda _value: None)
    return runner, loop, deps


def test_auto_router_is_local_and_prioritizes_research_over_code():
    from core.services.agent_runner import classify_profile_locally

    assert classify_profile_locally("Привет, помоги сформулировать мысль") == "base"
    assert classify_profile_locally("Исправь traceback в Python функции") == "coder"
    assert (
        classify_profile_locally("Найди в интернете свежие источники и Python примеры")
        == "deep_research"
    )


def test_missing_model_key_fails_before_chat_or_message_creation(
    tmp_path,
    monkeypatch,
):
    from core import agent as agent_module
    from core import db
    from core.services.agent_runner import AgentNotConfiguredError

    monkeypatch.setattr(agent_module, "LITE_MODEL", "google:test-lite")
    monkeypatch.setattr(agent_module, "HEAVY_MODEL", "google:test-heavy")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ORANGE_CODER_MODELS", raising=False)
    monkeypatch.setattr(
        db,
        "create_chat",
        lambda *_args, **_kwargs: pytest.fail("chat was created before config validation"),
    )

    runner, loop, _deps = make_runner(tmp_path)
    try:
        with pytest.raises(AgentNotConfiguredError):
            asyncio.run(runner.run_agent("base", "hello"))
    finally:
        loop.close()


def test_each_agent_run_keeps_its_own_profile_prompt_and_state(
    tmp_path,
    monkeypatch,
):
    from core import graph

    states = []

    class FakeGraph:
        async def run(self, *, state, deps):
            states.append(state)
            await asyncio.sleep(0)
            return f"answer:{state.profile_name}:{state.user_prompt}"

    monkeypatch.setattr(graph, "orange_fsm_graph", FakeGraph())
    monkeypatch.setattr(graph, "delete_graph_state", AsyncMock())
    runner, loop, _deps = make_runner(tmp_path, api_key="configured-for-mock")
    monkeypatch.setattr(runner, "_build_rag_context", AsyncMock(return_value=""))

    async def run_all():
        return await asyncio.gather(
            runner.run_agent("base", "base prompt", persist_chat=False),
            runner.run_agent("coder", "coder prompt", persist_chat=False),
            runner.run_agent(
                "auto",
                "Найди в интернете свежие источники",
                persist_chat=False,
            ),
        )

    try:
        results = asyncio.run(run_all())
    finally:
        loop.close()

    assert results == [
        "answer:base:base prompt",
        "answer:coder:coder prompt",
        "answer:deep_research:Найди в интернете свежие источники",
    ]
    assert [state.profile_name for state in states] == [
        "base",
        "coder",
        "deep_research",
    ]
    assert len({id(state) for state in states}) == 3


def test_graph_selects_model_and_system_prompt_per_run(tmp_path, monkeypatch):
    from core import agent as agent_module
    from core import graph
    from core.profiles import PROFILES

    calls = []

    class FakeResult:
        def __init__(self, output):
            self.output = output

    class FakeAgent:
        async def run(self, payload, **kwargs):
            calls.append((payload, kwargs))
            await asyncio.sleep(0)
            return FakeResult(f"draft:{payload[0]}")

    monkeypatch.setattr(agent_module, "agent", FakeAgent())
    monkeypatch.setattr(graph, "save_graph_state", AsyncMock())
    deps = SimpleNamespace(
        obsidian_vault_path=str(tmp_path),
        settings=SimpleNamespace(gemini_api_key=None),
    )
    base_state = graph.OrangeGraphState(
        user_prompt="base request",
        profile_name="base",
        session_id="base",
    )
    coder_state = graph.OrangeGraphState(
        user_prompt="coder request",
        profile_name="coder",
        session_id="coder",
    )

    async def run_nodes():
        await asyncio.gather(
            graph.DraftNode().run(
                SimpleNamespace(state=base_state, deps=deps)
            ),
            graph.DraftNode().run(
                SimpleNamespace(state=coder_state, deps=deps)
            ),
        )

    asyncio.run(run_nodes())
    by_prompt = {payload[0]: kwargs for payload, kwargs in calls}
    assert by_prompt["base request"]["model"] == agent_module.LITE_MODEL
    assert by_prompt["coder request"]["model"] == agent_module.HEAVY_MODEL
    assert PROFILES["base"] in by_prompt["base request"]["instructions"]
    assert PROFILES["coder"] in by_prompt["coder request"]["instructions"]
    assert base_state.draft_response == "draft:base request"
    assert coder_state.draft_response == "draft:coder request"


@pytest.mark.parametrize("profile_name", ["base", "coder", "deep_research"])
def test_installed_pydantic_ai_accepts_orange_run_contract(
    profile_name,
    tmp_path,
    monkeypatch,
):
    from pydantic_ai.models.test import TestModel

    from core.agent import agent
    from core.profiles import PROFILES

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ORANGE_CODER_MODELS", raising=False)
    deps = SimpleNamespace(
        settings=SimpleNamespace(gemini_api_key="test"),
        obsidian_vault_path=str(tmp_path),
        mcp_client=None,
        request_override=None,
    )
    model = TestModel(
        call_tools=[],
        custom_output_text=f"contract:{profile_name}",
    )

    result = asyncio.run(
        agent.run(
            ["hello"],
            model=model,
            deps=deps,
            instructions=PROFILES[profile_name],
            model_settings={"timeout": 5.0},
            metadata={"orange_profile": profile_name},
        )
    )

    assert result.output == f"contract:{profile_name}"


def test_history_omits_current_and_excluded_messages_but_keeps_pinned(tmp_path):
    runner, loop, _deps = make_runner(tmp_path, api_key="configured")
    history = [
        {
            "id": 0,
            "role": "model",
            "content": "opening context",
            "is_pinned": 0,
            "exclude_from_rag": 0,
        },
        {
            "id": 1,
            "role": "user",
            "content": "important pinned fact",
            "is_pinned": 1,
            "exclude_from_rag": 0,
        },
        {
            "id": 2,
            "role": "model",
            "content": "excluded secret",
            "is_pinned": 0,
            "exclude_from_rag": 1,
        },
        {
            "id": 3,
            "role": "model",
            "content": "recent answer",
            "is_pinned": 0,
            "exclude_from_rag": 0,
        },
        {
            "id": 4,
            "role": "user",
            "content": "current request",
            "is_pinned": 0,
            "exclude_from_rag": 0,
        },
    ]
    try:
        context = asyncio.run(runner._build_history_context(history))
    finally:
        loop.close()

    assert context.index("opening context") < context.index("important pinned fact")
    assert context.index("important pinned fact") < context.index("recent answer")
    assert "USER [PINNED]" in context
    assert "important pinned fact" in context
    assert "recent answer" in context
    assert "excluded secret" not in context
    assert "current request" not in context


def test_rag_uses_local_vault_search_and_includes_verifiable_source_path(
    tmp_path,
    monkeypatch,
):
    from core import markdown_ops
    from core.hybrid_search import hybrid_search

    (tmp_path / "projects").mkdir()
    (tmp_path / "_Orange").mkdir()
    (tmp_path / "projects" / "roadmap.md").write_text(
        "# Roadmap\nImportant stabilization target",
        encoding="utf-8",
    )
    (tmp_path / "_Orange" / "generated.md").write_text(
        "Important stabilization target",
        encoding="utf-8",
    )
    monkeypatch.setattr(markdown_ops.shutil, "which", lambda _name: None)

    paths = asyncio.run(
        hybrid_search(
            "stabilization target",
            str(tmp_path),
            api_key=None,
            limit=3,
        )
    )
    assert paths == ["projects/roadmap.md"]

    runner, loop, _deps = make_runner(tmp_path, api_key=None)
    try:
        context = asyncio.run(
            runner._build_rag_context(None, "stabilization target")
        )
    finally:
        loop.close()
    assert "Source path: projects/roadmap.md" in context
    assert "Important stabilization target" in context
    assert "_Orange/generated.md" not in context


def test_embedding_cache_key_is_scoped_to_vault_root_and_model(tmp_path):
    from core.hybrid_search import _note_embedding_cache_key

    first = _note_embedding_cache_key(
        tmp_path / "one",
        "note.md",
        "embedding-model-a",
    )
    second = _note_embedding_cache_key(
        tmp_path / "two",
        "note.md",
        "embedding-model-a",
    )
    other_model = _note_embedding_cache_key(
        tmp_path / "one",
        "note.md",
        "embedding-model-b",
    )
    assert first != second
    assert first != other_model
    assert first.endswith(":note.md")


def test_runtime_attachment_is_cleaned_even_when_validation_skips_it(tmp_path):
    runner, loop, _deps = make_runner(tmp_path, api_key="configured")
    runtime_root = (
        Path(__file__).resolve().parents[1]
        / ".orange_runtime"
        / "attachments"
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    staged = runtime_root / "unsupported.test"
    staged.write_text("temporary", encoding="utf-8")

    try:
        parts, cleanup_paths, warnings = runner._load_attachments(
            json.dumps([str(staged)])
        )
        assert parts == []
        assert str(staged.resolve()) in cleanup_paths
        assert warnings
        runner._cleanup_runtime_attachments(cleanup_paths)
        assert not staged.exists()
    finally:
        staged.unlink(missing_ok=True)
        loop.close()


def test_agent_runner_shutdown_cancels_background_tasks(tmp_path):
    from core.services.agent_runner import AgentRunner

    async def exercise():
        loop = asyncio.get_running_loop()
        deps = SimpleNamespace(
            settings=SimpleNamespace(gemini_api_key=None),
            obsidian_vault_path=str(tmp_path),
            mcp_client=None,
            request_override=None,
        )
        runner = AgentRunner(
            loop,
            deps,
            lambda: None,
            lambda: None,
            lambda _value: None,
        )
        runner._spawn_background_task(asyncio.sleep(60))
        assert len(runner._background_tasks) == 1
        await runner.shutdown()
        assert runner._background_tasks == set()

    asyncio.run(exercise())


def test_agent_does_not_register_automatic_python_execution():
    from core.agent import agent

    tool_names = set(agent._function_toolset.tools)
    assert "execute_python" not in tool_names
    assert "execute_python_restricted" not in tool_names
    assert "deep_research" not in tool_names
    assert {"rewrite_file", "patch_file", "add_task"} <= tool_names


def test_agent_mcp_proxy_rejects_write_without_calling_server(
    tmp_path,
    monkeypatch,
):
    from core import agent as agent_module
    from core import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "orange_memory.db"))
    db.init_db()

    class FakeMcp:
        _session = object()

        async def call_tool(self, *_args, **_kwargs):
            pytest.fail("blocked MCP write reached the server")

    context = SimpleNamespace(
        deps=SimpleNamespace(mcp_client=FakeMcp())
    )
    result = asyncio.run(
        agent_module.call_obsidian_tool(
            context,
            "write_note",
            {"path": "note.md", "content": "x"},
        )
    )

    assert result.startswith("[APPROVAL_DENIED]")
    assert db.list_audit_events()[0]["status"] == "denied"


def test_restricted_executor_runs_only_after_approval_and_caps_output():
    from core.tools import execute_python_restricted

    async def approve(_command):
        return True

    async def deny(_command):
        return False

    denied = asyncio.run(execute_python_restricted("print(4)", deny))
    allowed = asyncio.run(execute_python_restricted("print(2 + 2)", approve))
    oversized = asyncio.run(
        execute_python_restricted("print('x' * 60000)", approve)
    )

    assert denied.startswith("[APPROVAL_DENIED]")
    assert "[STDOUT]\n4" in allowed
    assert "50 KB output limit" in oversized
