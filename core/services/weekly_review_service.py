from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from core import db
from core.graph_api import get_notes_graph
from core.path_safety import VaultPathResolver
from core.services.write_preview_service import WritePreviewService
from core.services.write_preview_service import PreviewStateError, StalePreviewError


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[(?P<done>[ xX])\]\s+(?P<text>.+)$", re.MULTILINE)
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
LOCAL_DATE_PATTERN = re.compile(r"\b([0-3]?\d)\.([01]?\d)\.(20\d{2})\b")


class WeeklyReviewService:
    """Builds and exports a weekly vault review."""

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root
        self.writer = WritePreviewService(vault_path)
        self._previews: Dict[str, Dict] = {}
        self._latest_preview_id = ""

    def preview_weekly_review(self) -> Dict:
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        recent_since = datetime.now() - timedelta(days=7)
        review, source_snapshot = self._build_review(today, recent_since)
        target_rel = f"_Orange/Reviews/Weekly Review {iso_year}-W{iso_week:02d}.md"
        plan = self.writer.build_plan(target_rel, review, action="weekly_review")
        preview_id = uuid.uuid4().hex
        self._previews[preview_id] = {
            "plan": plan,
            "week": f"{iso_year}-W{iso_week:02d}",
            "source_snapshot": source_snapshot,
        }
        self._latest_preview_id = preview_id
        db.add_audit_event(
            "weekly_review",
            "proposed",
            f"Generated weekly review preview {iso_year}-W{iso_week:02d}",
            self.writer.audit_details(plan),
        )
        return {
            "status": "success",
            "preview_id": preview_id,
            "plan": plan,
            "week": f"{iso_year}-W{iso_week:02d}",
        }

    async def apply_weekly_review(self, preview_id: str = "") -> Dict:
        selected_id = preview_id or self._latest_preview_id
        preview = self._previews.get(selected_id)
        if not preview:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Weekly Review preview is missing or expired. Build a new preview.",
            }
        try:
            if self._source_snapshot() != preview["source_snapshot"]:
                raise StalePreviewError(
                    "Vault source notes changed after the Weekly Review preview was built."
                )
            await self.writer.apply_plan(preview["plan"])
        except (StalePreviewError, PreviewStateError) as exc:
            error_code = (
                "STALE_PREVIEW"
                if isinstance(exc, StalePreviewError)
                else "VALIDATION_ERROR"
            )
            db.add_audit_event("weekly_review", "stale" if error_code == "STALE_PREVIEW" else "error", str(exc))
            return {
                "status": "error",
                "error_code": error_code,
                "message": str(exc),
                "preview_id": selected_id,
            }
        except Exception as exc:
            self._previews.pop(selected_id, None)
            if self._latest_preview_id == selected_id:
                self._latest_preview_id = ""
            db.add_audit_event(
                "weekly_review",
                "failed",
                f"Weekly Review write failed: {type(exc).__name__}",
                self.writer.audit_details(preview["plan"]),
            )
            return {
                "status": "error",
                "error_code": "PROVIDER_ERROR",
                "message": "Weekly Review could not be written. Build a new preview before retrying.",
                "preview_id": selected_id,
            }

        self._previews.pop(selected_id, None)
        if self._latest_preview_id == selected_id:
            self._latest_preview_id = ""
        db.add_audit_event(
            "weekly_review",
            "applied",
            f"Applied weekly review {preview['week']}",
            self.writer.audit_details(preview["plan"]),
        )
        return {
            "status": "success",
            "message": f"Weekly review written: {preview['plan']['relative_path']}",
            "preview_id": selected_id,
            "plan": preview["plan"],
        }

    def reject_weekly_review(self, preview_id: str = "") -> Dict:
        selected_id = preview_id or self._latest_preview_id
        preview = self._previews.pop(selected_id, None)
        if not preview:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Pending Weekly Review preview was not found.",
            }
        preview["plan"]["status"] = "rejected"
        if self._latest_preview_id == selected_id:
            self._latest_preview_id = ""
        db.add_audit_event(
            "weekly_review",
            "rejected",
            f"Rejected weekly review {preview['week']}",
        )
        return {
            "status": "success",
            "message": "Weekly Review preview rejected.",
            "preview_id": selected_id,
        }

    def _build_review(
        self,
        today: date,
        recent_since: datetime,
    ) -> tuple[str, Dict[str, str]]:
        open_tasks = []
        done_tasks = []
        overdue_tasks = []
        recent_notes = []
        seen_tasks = set()
        source_snapshot = {}

        for file_path in self._markdown_files():
            content = self._resolver.read_note_text(file_path)
            rel = file_path.relative_to(self.vault_path).as_posix()
            source_snapshot[rel] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified >= recent_since:
                recent_notes.append(rel)

            for match in TASK_PATTERN.finditer(content):
                item = {"text": match.group("text").strip(), "file_path": rel}
                identity = (
                    re.sub(r"\s+", " ", item["text"]).strip().casefold(),
                    match.group("done").lower() == "x",
                )
                if identity in seen_tasks:
                    continue
                seen_tasks.add(identity)
                if match.group("done").lower() == "x":
                    done_tasks.append(item)
                else:
                    open_tasks.append(item)
                    due = self._extract_date(item["text"])
                    if due and due < today:
                        overdue_tasks.append(item)

        graph = get_notes_graph(str(self.vault_path), exclude_generated=True)
        orphan_notes = [node for node in graph["nodes"] if node.get("orphan")][:20]
        overdue_tasks.sort(key=lambda item: (self._extract_date(item["text"]) or date.max, item["file_path"]))
        open_tasks.sort(key=lambda item: (item["file_path"], item["text"].casefold()))
        done_tasks.sort(key=lambda item: (item["file_path"], item["text"].casefold()))
        recent_notes.sort(key=str.casefold)
        focus = []
        focus_keys = set()
        for item in [*overdue_tasks, *open_tasks]:
            identity = item["text"].casefold()
            if identity in focus_keys:
                continue
            focus_keys.add(identity)
            focus.append(item)
            if len(focus) >= 3:
                break

        review = (
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
        return review, source_snapshot

    def _source_snapshot(self) -> Dict[str, str]:
        snapshot = {}
        for file_path in self._markdown_files():
            content = self._resolver.read_note_text(file_path)
            relative_path = file_path.relative_to(self.vault_path).as_posix()
            snapshot[relative_path] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
        return snapshot

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

    def _task_bullets(self, items: List[Dict], empty: str) -> str:
        if not items:
            return f"- {empty}"
        return "\n".join(f"- [ ] {item['text']} (`{item['file_path']}`)" for item in items)

    def _bullets(self, items: List[str], empty: str) -> str:
        if not items:
            return f"- {empty}"
        return "\n".join(f"- `{item}`" for item in items)
