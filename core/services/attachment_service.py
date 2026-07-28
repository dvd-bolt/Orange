from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional


class AttachmentService:
    """Native file staging and PDF text extraction for BridgeAPI."""

    allowed_extensions = {".txt", ".csv", ".md", ".pdf"}
    max_file_bytes = 10 * 1024 * 1024
    max_pdf_bytes = 50 * 1024 * 1024
    max_extracted_bytes = 2 * 1024 * 1024
    staged_file_ttl_seconds = 60 * 60
    pdf_authorization_ttl_seconds = 10 * 60

    def __init__(
        self,
        vault_path: str = "",
        runtime_dir: Optional[Path] = None,
    ):
        self.vault_path = vault_path
        self.runtime_dir = (
            Path(runtime_dir)
            if runtime_dir is not None
            else Path(__file__).resolve().parents[2]
            / ".orange_runtime"
            / "attachments"
        )
        self._authorized_pdfs: Dict[str, Dict] = {}
        self._authorization_lock = threading.Lock()

    def _prepare_runtime_dir(self) -> None:
        if self.runtime_dir.parent.is_symlink() or self.runtime_dir.is_symlink():
            raise ValueError("Attachment runtime directory cannot be a symlink")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.runtime_dir.chmod(0o700)
        except OSError:
            pass

        cutoff = time.time() - self.staged_file_ttl_seconds
        for child in self.runtime_dir.iterdir():
            try:
                metadata = child.lstat()
                if metadata.st_mtime < cutoff and (
                    child.is_symlink() or child.is_file()
                ):
                    child.unlink(missing_ok=True)
            except OSError:
                continue

        now = time.monotonic()
        with self._authorization_lock:
            self._authorized_pdfs = {
                path: metadata
                for path, metadata in self._authorized_pdfs.items()
                if metadata["expires_at"] > now and Path(path).is_file()
            }

    def _stage_source(self, source: Path, prefix: str, max_bytes: int) -> Path:
        self._prepare_runtime_dir()
        destination = self.runtime_dir / f"{prefix}_{uuid.uuid4().hex}{source.suffix.lower()}"
        try:
            with source.open("rb") as source_file, destination.open("xb") as destination_file:
                copied = 0
                while chunk := source_file.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > max_bytes:
                        raise ValueError("Selected file grew beyond the size limit")
                    destination_file.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        try:
            destination.chmod(0o600)
        except OSError:
            pass
        return destination.resolve(strict=True)

    def _authorize_pdf(self, staged_path: Path, filename: str) -> None:
        stat = staged_path.stat()
        with self._authorization_lock:
            self._authorized_pdfs[str(staged_path)] = {
                "filename": filename,
                "expires_at": time.monotonic() + self.pdf_authorization_ttl_seconds,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }

    def _get_authorized_pdf(self, file_path: str) -> tuple[Path, Dict]:
        self._prepare_runtime_dir()
        candidate = Path(file_path).expanduser()
        if candidate.is_symlink():
            raise ValueError("Staged PDF symlinks are not allowed")
        source = candidate.resolve(strict=True)
        try:
            source.relative_to(self.runtime_dir.resolve(strict=True))
        except ValueError as exc:
            raise ValueError("PDF is not a staged attachment") from exc

        with self._authorization_lock:
            metadata = self._authorized_pdfs.get(str(source))
        if not metadata or metadata["expires_at"] <= time.monotonic():
            raise ValueError("PDF staging authorization is missing or expired")

        stat = source.stat()
        if stat.st_size != metadata["size"] or stat.st_mtime_ns != metadata["mtime_ns"]:
            raise ValueError("Staged PDF changed after selection")
        return source, metadata

    def discard_staged_file(self, file_path: str) -> Dict:
        try:
            self._prepare_runtime_dir()
            candidate = Path(file_path).expanduser()
            runtime_root = self.runtime_dir.resolve(strict=False)
            if candidate.is_symlink():
                candidate.parent.resolve(strict=True).relative_to(runtime_root)
                candidate.unlink(missing_ok=True)
                return {"status": "success"}
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(runtime_root)
            with self._authorization_lock:
                self._authorized_pdfs.pop(str(resolved), None)
            resolved.unlink(missing_ok=True)
            return {"status": "success"}
        except (OSError, ValueError):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Attachment is not a valid staged file",
            }

    def stage_file(self, window) -> Dict:
        if not window:
            return {
                "status": "error",
                "error_code": "NOT_CONFIGURED",
                "message": "Application window is not initialized",
            }

        try:
            import webview

            file_types = ("Text and PDF files (*.txt;*.csv;*.md;*.pdf)", "All files (*.*)")
            result = window.create_file_dialog(
                dialog_type=webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=file_types,
            )
            if not result:
                return {"status": "cancelled"}

            source = Path(result[0]).expanduser().resolve(strict=True)
            if not source.is_file():
                raise ValueError("Selected path is not a regular file")
            filename = source.name
            _, ext = os.path.splitext(filename)
            if ext.lower() not in self.allowed_extensions:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "message": "Only .txt, .csv, .md, and .pdf formats are supported",
                }

            file_size = source.stat().st_size
            size_limit = self.max_pdf_bytes if ext.lower() == ".pdf" else self.max_file_bytes
            if file_size > size_limit:
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "message": f"File is too large. Limit: {size_limit // 1024 // 1024} MB",
                }

            if ext.lower() == ".pdf":
                import pypdf

                staged_path = self._stage_source(
                    source,
                    "pdf_source",
                    self.max_pdf_bytes,
                )
                try:
                    reader = pypdf.PdfReader(str(staged_path))
                    page_count = len(reader.pages)
                    if page_count == 0:
                        raise ValueError("PDF has no pages")
                except Exception:
                    staged_path.unlink(missing_ok=True)
                    raise
                self._authorize_pdf(staged_path, filename)
                return {
                    "status": "pdf_config_needed",
                    "file_path": str(staged_path),
                    "filename": filename,
                    "page_count": page_count,
                }

            staged_path = self._stage_source(source, "document", self.max_file_bytes)
            print(f"[AttachmentService] File staged: {filename}")
            return {
                "status": "success",
                "filename": filename,
                "file_path": str(staged_path),
            }
        except Exception as e:
            print(f"[AttachmentService Error] Error staging file: {type(e).__name__}")
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"File could not be staged: {type(e).__name__}",
            }

    def stage_pdf_with_range(self, file_path: str, start_page: int, end_page: int) -> Dict:
        try:
            import pypdf

            start_page = int(start_page)
            end_page = int(end_page)
            source, authorization = self._get_authorized_pdf(file_path)
            if source.suffix.lower() != ".pdf":
                return {"status": "error", "error_code": "VALIDATION_ERROR", "message": "Expected a PDF file"}
            if source.stat().st_size > self.max_pdf_bytes:
                return {"status": "error", "error_code": "VALIDATION_ERROR", "message": "PDF exceeds 50 MB"}

            filename = authorization["filename"]
            reader = pypdf.PdfReader(str(source))
            total = len(reader.pages)
            if (
                total == 0
                or start_page < 1
                or end_page < start_page
                or start_page > total
                or end_page > total
            ):
                return {
                    "status": "error",
                    "error_code": "VALIDATION_ERROR",
                    "message": f"Invalid PDF page range {start_page}-{end_page}; document has {total} pages",
                }
            start = max(0, start_page - 1)
            end = end_page
            pages_text = [reader.pages[index].extract_text() or "" for index in range(start, end)]
            content = "\n".join(pages_text)
            encoded = content.encode("utf-8")
            if len(encoded) > self.max_extracted_bytes:
                content = encoded[:self.max_extracted_bytes].decode("utf-8", errors="ignore")

            self._prepare_runtime_dir()
            temp_filename = f"pdf_extract_{uuid.uuid4().hex}.txt"
            temp_file_path = self.runtime_dir / temp_filename
            with temp_file_path.open("x", encoding="utf-8") as file:
                file.write(content)
            try:
                temp_file_path.chmod(0o600)
            except OSError:
                pass
            with self._authorization_lock:
                self._authorized_pdfs.pop(str(source), None)
            source.unlink(missing_ok=True)

            print(
                f"[AttachmentService] PDF {filename} pages "
                f"{start_page}-{end_page} extracted."
            )
            return {"status": "success", "filename": filename, "file_path": str(temp_file_path.resolve())}
        except Exception as e:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"PDF could not be processed: {type(e).__name__}",
            }

    def to_json(self, payload: Dict) -> str:
        return json.dumps(payload, ensure_ascii=False)
