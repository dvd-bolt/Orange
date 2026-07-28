from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict, List

from core.graph_api import get_notes_graph
from core.path_safety import VaultPathResolver


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[ \]\s+(?P<text>.+)$")
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
LOCAL_DATE_PATTERN = re.compile(r"\b([0-3]?\d)\.([01]?\d)\.(20\d{2})\b")


class DashboardService:
    """Builds a compact daily operational snapshot from the vault."""

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root

    def build_morning_dashboard(self) -> Dict:
        today = date.today()
        today_tasks: List[Dict] = []
        overdue_tasks: List[Dict] = []
        telegram_tasks: List[Dict] = []
        open_tasks: List[Dict] = []
        task_records: Dict[tuple[str, str], Dict] = {}

        for file_path in self._markdown_files():
            try:
                content = self._resolver.read_note_text(file_path)
                rel_path = file_path.relative_to(self.vault_path).as_posix()
            except (OSError, ValueError):
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                match = TASK_PATTERN.match(line)
                if not match:
                    continue
                text = match.group("text").strip()
                due = self._extract_date(text)
                task_key = (
                    re.sub(r"\s+", " ", text).strip().casefold(),
                    due.isoformat() if due else "",
                )
                today_context = (
                    due == today
                    or (due is None and self._looks_like_today_context(file_path, content))
                )
                telegram_context = "telegram" in rel_path.lower()
                item = {
                    "text": text,
                    "file_path": rel_path,
                    "line": line_number,
                    "due_date": due.isoformat() if due else None,
                    "_today_context": today_context,
                    "_telegram_context": telegram_context,
                }
                existing = task_records.get(task_key)
                candidate_rank = (today_context, telegram_context)
                existing_rank = (
                    existing.get("_today_context", False),
                    existing.get("_telegram_context", False),
                ) if existing else (False, False)
                if existing is None or candidate_rank > existing_rank:
                    task_records[task_key] = item

        for item in task_records.values():
            due = (
                date.fromisoformat(item["due_date"])
                if item["due_date"]
                else None
            )
            open_tasks.append(item)
            if due and due < today:
                overdue_tasks.append(item)
            elif item["_today_context"]:
                today_tasks.append(item)
            if item["_telegram_context"]:
                telegram_tasks.append(item)

        for item in open_tasks:
            item.pop("_today_context", None)
            item.pop("_telegram_context", None)

        graph = get_notes_graph(str(self.vault_path), exclude_generated=True)
        overdue_tasks.sort(key=lambda item: (item["due_date"] or "", item["file_path"], item["line"]))
        today_tasks.sort(key=lambda item: (item["file_path"], item["line"]))
        telegram_tasks.sort(key=lambda item: (item["file_path"], item["line"]))
        open_tasks.sort(key=lambda item: (item["file_path"], item["line"]))
        orphan_notes = sorted(
            (node for node in graph["nodes"] if node.get("orphan")),
            key=lambda node: node["path"].lower(),
        )[:20]

        focus_candidates = []
        focus_keys = set()
        for collection in (overdue_tasks, today_tasks, open_tasks):
            for item in collection:
                key = (item["file_path"], item["line"])
                if key in focus_keys:
                    continue
                focus_keys.add(key)
                focus_candidates.append(item)
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
        return list(self._resolver.iter_notes(exclude_generated=True))

    def _extract_date(self, text: str):
        match = ISO_DATE_PATTERN.search(text)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                pass
        local_match = LOCAL_DATE_PATTERN.search(text)
        if not local_match:
            return None
        try:
            return date(
                int(local_match.group(3)),
                int(local_match.group(2)),
                int(local_match.group(1)),
            )
        except ValueError:
            return None

    def _looks_like_today_context(self, file_path: Path, content: str) -> bool:
        name = file_path.stem.lower()
        return "today" in name or "daily" in name or "# today" in content.lower()
