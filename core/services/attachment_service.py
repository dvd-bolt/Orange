from __future__ import annotations

import json
import os
import uuid
from typing import Dict


class AttachmentService:
    """Native file staging and PDF text extraction for BridgeAPI."""

    allowed_extensions = {".txt", ".csv", ".md", ".pdf"}

    def stage_file(self, window) -> Dict:
        if not window:
            return {"status": "error", "message": "Application window is not initialized"}

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

            file_path = result[0]
            filename = os.path.basename(file_path)
            _, ext = os.path.splitext(filename)
            if ext.lower() not in self.allowed_extensions:
                return {
                    "status": "error",
                    "message": "Only .txt, .csv, .md, and .pdf formats are supported",
                }

            if ext.lower() == ".pdf":
                import pypdf

                reader = pypdf.PdfReader(file_path)
                return {
                    "status": "pdf_config_needed",
                    "file_path": file_path,
                    "filename": filename,
                    "page_count": len(reader.pages),
                }

            print(f"[AttachmentService] File staged: {filename} -> {file_path}")
            return {"status": "success", "filename": filename, "file_path": file_path}
        except Exception as e:
            print(f"[AttachmentService Error] Error staging file: {e}")
            return {"status": "error", "message": str(e)}

    def stage_pdf_with_range(self, file_path: str, start_page: int, end_page: int) -> Dict:
        try:
            import pypdf

            filename = os.path.basename(file_path)
            reader = pypdf.PdfReader(file_path)
            total = len(reader.pages)
            start = max(0, start_page - 1)
            end = min(total, end_page)
            pages_text = [reader.pages[index].extract_text() or "" for index in range(start, end)]
            content = "\n".join(pages_text)

            scratch_dir = "scratch"
            os.makedirs(scratch_dir, exist_ok=True)
            temp_filename = f"pdf_extract_{uuid.uuid4().hex}.txt"
            temp_file_path = os.path.abspath(os.path.join(scratch_dir, temp_filename))
            with open(temp_file_path, "w", encoding="utf-8") as file:
                file.write(content)

            print(f"[AttachmentService] PDF {filename} pages {start_page}-{end_page} extracted to {temp_file_path}")
            return {"status": "success", "filename": filename, "file_path": temp_file_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def to_json(self, payload: Dict) -> str:
        return json.dumps(payload)
