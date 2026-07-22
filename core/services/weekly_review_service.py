from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from core import db
from core.graph_api import get_notes_graph
from core.services.write_preview_service import WritePreviewService


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[(?P<done>[ xX])\]\s+(?P<text>.+)$", re.MULTILINE)
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


class WeeklyReviewService:
    """Builds and exports a weekly vault review."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.writer = WritePreviewService(vault_path)

    def preview_weekly_review(self) -> Dict:
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        recent_since = datetime.now() - timedelta(days=7)
        review = self._build_review(today, recent_since)
        target_rel = f"_Orange/Reviews/Weekly Review {iso_year}-W{iso_week:02d}.md"
        plan = self.writer.build_plan(target_rel, review, action="weekly_review")
        db.add_audit_event("weekly_review", "proposed", f"Generated weekly review preview {iso_year}-W{iso_week:02d}", plan["diff"])
        return {"status": "success", "plan": plan, "week": f"{iso_year}-W{iso_week:02d}"}

    async def apply_weekly_review(self) -> Dict:
        preview = self.preview_weekly_review()
        await self.writer.apply_plan(preview["plan"])
        db.add_audit_event("weekly_review", "applied", f"Applied weekly review {preview['week']}", preview["plan"]["diff"])
        return {"status": "success", "message": f"Weekly review written: {preview['plan']['relative_path']}", "plan": preview["plan"]}

    def _build_review(self, today: date, recent_since: datetime) -> str:
        open_tasks = []
        done_tasks = []
        overdue_tasks = []
        recent_notes = []

        for file_path in self._markdown_files():
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            rel = str(file_path.relative_to(self.vault_path))
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified >= recent_since:
                recent_notes.append(rel)

            for match in TASK_PATTERN.finditer(content):
                item = {"text": match.group("text").strip(), "file_path": rel}
                if match.group("done").lower() == "x":
                    done_tasks.append(item)
                else:
                    open_tasks.append(item)
                    due = self._extract_date(item["text"])
                    if due and due < today:
                        overdue_tasks.append(item)

        graph = get_notes_graph(str(self.vault_path))
        orphan_notes = [node for node in graph["nodes"] if node.get("orphan")][:20]
        focus = overdue_tasks[:2] + open_tasks[:3]

        return (
            f"# Weekly Review {today.isoformat()}\n\n"
            "## Scoreboard\n"
            f"- Open tasks: {len(open_tasks)}\n"
            f"- Completed tasks: {len(done_tasks)}\n"
            f"- Overdue tasks: {len(overdue_tasks)}\n"
            f"- Recent notes: {len(recent_notes)}\n"
            f"- Orphan notes: {len(orphan_notes)}\n\n"
            "## Top Focus\n"
            f"{self._task_bullets(focus, 'No focus tasks found')}\n\n"
            "## Overdue\n"
            f"{self._task_bullets(overdue_tasks[:20], 'No overdue tasks')}\n\n"
            "## Completed This Vault Snapshot\n"
            f"{self._task_bullets(done_tasks[:20], 'No completed tasks found')}\n\n"
            "## Recent Notes\n"
            f"{self._bullets(recent_notes[:30], 'No recently modified notes')}\n\n"
            "## Orphan Notes To Link\n"
            f"{self._bullets([node['path'] for node in orphan_notes], 'No orphan notes found')}\n"
        )

    def _markdown_files(self) -> List[Path]:
        if not self.vault_path.exists():
            return []
        result = []
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
            for filename in files:
                if filename.endswith(".md"):
                    result.append(Path(root) / filename)
        return sorted(result)

    def _extract_date(self, text: str):
        match = DATE_PATTERN.search(text)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None

    def _task_bullets(self, items: List[Dict], empty: str) -> str:
        if not items:
            return f"- {empty}"
        return "\n".join(f"- [ ] {item['text']} (`{item['file_path']}`)" for item in items)

    def _bullets(self, items: List[str], empty: str) -> str:
        if not items:
            return f"- {empty}"
        return "\n".join(f"- `{item}`" for item in items)
