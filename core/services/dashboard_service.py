from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, List

from core.graph_api import get_notes_graph


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[ \]\s+(?P<text>.+)$", re.MULTILINE)
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


class DashboardService:
    """Builds a compact daily operational snapshot from the vault."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)

    def build_morning_dashboard(self) -> Dict:
        today = date.today()
        today_tasks: List[Dict] = []
        overdue_tasks: List[Dict] = []
        telegram_tasks: List[Dict] = []

        for file_path in self._markdown_files():
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(file_path.relative_to(self.vault_path))
            for match in TASK_PATTERN.finditer(content):
                text = match.group("text").strip()
                item = {"text": text, "file_path": rel_path}
                due = self._extract_date(text)
                if due and due < today:
                    overdue_tasks.append(item)
                elif due == today or self._looks_like_today_context(file_path, content):
                    today_tasks.append(item)
                if "telegram" in rel_path.lower():
                    telegram_tasks.append(item)

        graph = get_notes_graph(str(self.vault_path))
        orphan_notes = [node for node in graph["nodes"] if node.get("orphan")][:20]
        focus_candidates = overdue_tasks[:2] + today_tasks[:2]
        focus = [item["text"] for item in focus_candidates[:3]]
        if len(focus) < 3:
            focus.extend([f"Link orphan note: {note['id']}" for note in orphan_notes[: 3 - len(focus)]])

        return {
            "date": today.isoformat(),
            "today_tasks": today_tasks[:20],
            "overdue_tasks": overdue_tasks[:20],
            "telegram_tasks": telegram_tasks[:20],
            "orphan_notes": orphan_notes,
            "focus": focus[:3],
        }

    def _markdown_files(self) -> List[Path]:
        if not self.vault_path.exists():
            return []
        files = []
        for root, dirs, filenames in os.walk(self.vault_path):
            dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
            for filename in filenames:
                if filename.endswith(".md"):
                    files.append(Path(root) / filename)
        return files

    def _extract_date(self, text: str):
        match = DATE_PATTERN.search(text)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None

    def _looks_like_today_context(self, file_path: Path, content: str) -> bool:
        name = file_path.stem.lower()
        return "today" in name or "daily" in name or "# today" in content.lower()
