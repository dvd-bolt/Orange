from __future__ import annotations

import os
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class InboxService:
    """Creates review proposals for files in `_Inbox` and applies them only after user confirmation."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.inbox_path = self.vault_path / "_Inbox"

    def _resolve_inside_vault(self, file_path: str) -> Path:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = self.vault_path / candidate
        resolved = candidate.resolve()
        if self.vault_path not in resolved.parents and resolved != self.vault_path:
            raise ValueError(f"Path is outside vault: {file_path}")
        return resolved

    def classify_text(self, text: str) -> Dict:
        lowered = text.lower()
        urls = re.findall(r"https?://\S+", text)
        category = "idea"
        confidence = 0.55

        if re.search(r"(^|\n)\s*[-*]\s*\[[ x]\]|\b(todo|task|надо|сделать|дедлайн)\b", lowered):
            category = "task"
            confidence = 0.82
        elif urls:
            category = "link"
            confidence = 0.78
        elif re.search(r"\b(meeting|митинг|созвон|встреча|agenda|повестка)\b", lowered):
            category = "meeting"
            confidence = 0.76
        elif re.search(r"\b(project|проект|roadmap|milestone|релиз)\b", lowered):
            category = "project"
            confidence = 0.72

        first_line = next((line.strip("# -*\t ") for line in text.splitlines() if line.strip()), "")
        summary = first_line[:180] or "Empty inbox note"
        return {
            "category": category,
            "confidence": confidence,
            "summary": summary,
            "links": urls[:5],
            "action_label": self._action_label(category),
        }

    def _action_label(self, category: str) -> str:
        labels = {
            "task": "Add to inbox review tasks",
            "idea": "Save as idea for review",
            "link": "Save link for expansion",
            "project": "Mark as project material",
            "meeting": "Mark as meeting note",
        }
        return labels.get(category, "Save for review")

    def build_proposal(self, file_path: str) -> Dict:
        resolved = self._resolve_inside_vault(file_path)
        content = resolved.read_text(encoding="utf-8", errors="ignore")
        classification = self.classify_text(content)
        return {
            "status": "success",
            "file_path": str(resolved),
            "relative_path": str(resolved.relative_to(self.vault_path)),
            "filename": resolved.name,
            **classification,
        }

    def list_proposals(self, limit: int = 50) -> List[Dict]:
        if not self.inbox_path.exists():
            return []
        proposals = []
        for file_path in sorted(self.inbox_path.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True):
            if file_path.name == "Inbox Review.md":
                continue
            try:
                proposals.append(self.build_proposal(str(file_path)))
            except Exception as e:
                proposals.append({
                    "status": "error",
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "message": str(e),
                })
            if len(proposals) >= limit:
                break
        return proposals

    async def apply_proposal(self, file_path: str, category: str = "") -> Dict:
        proposal = self.build_proposal(file_path)
        category = category or proposal["category"]
        target_path = self.inbox_path / "Inbox Review.md"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        existing = target_path.read_text(encoding="utf-8", errors="ignore") if target_path.exists() else "# Inbox Review\n\n"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        block = (
            f"\n## {timestamp} - {proposal['filename']}\n"
            f"- Category: {category}\n"
            f"- Source: [[{Path(proposal['relative_path']).stem}]]\n"
            f"- Summary: {proposal['summary']}\n"
            f"- Action: {proposal['action_label']}\n"
        )
        await self._write_review_note(target_path, existing.rstrip() + "\n" + block)
        return {"status": "success", "message": f"Inbox proposal applied to {target_path}", "proposal": proposal}

    async def _write_review_note(self, target_path: Path, content: str):
        try:
            from core.file_ops import atomic_write_obsidian_note

            await atomic_write_obsidian_note(str(target_path), content)
            return
        except ModuleNotFoundError:
            pass

        temp_path = target_path.with_suffix(".tmp")
        await asyncio.to_thread(temp_path.write_text, content, encoding="utf-8")
        await asyncio.to_thread(os.replace, temp_path, target_path)
