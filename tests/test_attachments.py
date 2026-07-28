import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


class FakeWindow:
    def __init__(self, selected_path: Path):
        self.selected_path = selected_path

    def create_file_dialog(self, **_kwargs):
        return [str(self.selected_path)]


def install_fake_webview(monkeypatch):
    fake_webview = SimpleNamespace(
        FileDialog=SimpleNamespace(OPEN="open"),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)


def test_selected_text_file_is_copied_into_runtime(tmp_path, monkeypatch):
    from core.services.attachment_service import AttachmentService

    install_fake_webview(monkeypatch)
    source = tmp_path / "source.md"
    source.write_text("# Original", encoding="utf-8")
    runtime_dir = tmp_path / "runtime"
    service = AttachmentService(runtime_dir=runtime_dir)

    result = service.stage_file(FakeWindow(source))

    staged = Path(result["file_path"])
    assert result["status"] == "success"
    assert result["filename"] == "source.md"
    assert staged.parent == runtime_dir.resolve()
    assert staged != source
    assert staged.read_text(encoding="utf-8") == "# Original"
    source.write_text("# Changed later", encoding="utf-8")
    assert staged.read_text(encoding="utf-8") == "# Original"


def test_pdf_range_requires_native_selection_and_consumes_staged_source(
    tmp_path,
    monkeypatch,
):
    import pypdf

    from core.services.attachment_service import AttachmentService

    install_fake_webview(monkeypatch)
    source = tmp_path / "document.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as file:
        writer.write(file)

    service = AttachmentService(runtime_dir=tmp_path / "runtime")
    denied = service.stage_pdf_with_range(str(source), 1, 1)
    selected = service.stage_file(FakeWindow(source))
    staged_source = Path(selected["file_path"])
    extracted = service.stage_pdf_with_range(str(staged_source), 1, 1)

    assert denied["status"] == "error"
    assert denied["error_code"] == "VALIDATION_ERROR"
    assert selected["status"] == "pdf_config_needed"
    assert staged_source.parent == service.runtime_dir.resolve()
    assert extracted["status"] == "success"
    assert Path(extracted["file_path"]).is_file()
    assert not staged_source.exists()


def test_discard_refuses_files_outside_runtime(tmp_path):
    from core.services.attachment_service import AttachmentService

    outside = tmp_path / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")
    service = AttachmentService(runtime_dir=tmp_path / "runtime")

    result = service.discard_staged_file(str(outside))

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert outside.read_text(encoding="utf-8") == "keep me"


def test_attachment_service_rejects_symlinked_runtime_directory(
    tmp_path,
    monkeypatch,
):
    from core.services.attachment_service import AttachmentService

    install_fake_webview(monkeypatch)
    source = tmp_path / "source.txt"
    source.write_text("do not copy", encoding="utf-8")
    outside_runtime = tmp_path / "outside-runtime"
    outside_runtime.mkdir()
    runtime_link = tmp_path / "runtime-link"
    runtime_link.symlink_to(outside_runtime, target_is_directory=True)
    service = AttachmentService(runtime_dir=runtime_link)

    result = service.stage_file(FakeWindow(source))

    assert result["status"] == "error"
    assert result["error_code"] == "VALIDATION_ERROR"
    assert list(outside_runtime.iterdir()) == []


def test_agent_runner_rejects_unstaged_and_symlinked_attachments(
    tmp_path,
):
    from core.services.agent_runner import AgentRunner

    loop = asyncio.new_event_loop()
    deps = SimpleNamespace(
        settings=SimpleNamespace(gemini_api_key="configured"),
        obsidian_vault_path=str(tmp_path),
        mcp_client=None,
        request_override=None,
    )
    runner = AgentRunner(loop, deps, lambda: None, lambda: None, lambda _value: None)
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    runtime_root = (
        Path(__file__).resolve().parents[1]
        / ".orange_runtime"
        / "attachments"
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    symlink = runtime_root / "outside-link.txt"
    symlink.unlink(missing_ok=True)
    symlink.symlink_to(outside)

    try:
        parts, cleanup_paths, warnings = runner._load_attachments(
            json.dumps([str(outside), str(symlink)])
        )
        assert parts == []
        assert cleanup_paths == []
        assert len(warnings) == 2
        assert any("outside" in warning.lower() for warning in warnings)
        assert any("symlink" in warning.lower() for warning in warnings)
    finally:
        symlink.unlink(missing_ok=True)
        loop.close()
