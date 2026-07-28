from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Dict, Optional

from core.path_safety import VaultPathResolver

class WritePreviewService:
    """Builds diff previews and applies confirmed vault writes."""

    max_write_bytes = 2 * 1024 * 1024

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root
        self._previews: Dict[str, Dict] = {}
        self._latest_preview_id = ""

    def resolve_vault_path(self, note_path: str) -> Path:
        self._resolver.ensure_root()
        return self._resolver.resolve_note(note_path)

    def build_plan(self, note_path: str, new_content: str, action: str = "write") -> Dict:
        if not isinstance(new_content, str):
            raise ValueError("Proposed note content must be text.")
        if len(new_content.encode("utf-8")) > self.max_write_bytes:
            raise ValueError("Proposed note content exceeds the 2 MB write limit.")
        target_path = self.resolve_vault_path(note_path)
        before_exists = target_path.exists()
        old_content = self._read_existing(target_path) if before_exists else ""
        relative_path = target_path.relative_to(self.vault_path).as_posix()
        plan = {
            "preview_id": uuid.uuid4().hex,
            "action": action,
            "path": str(target_path),
            "relative_path": relative_path,
            "old_content": old_content,
            "new_content": new_content,
            "before_hash": self._content_hash(old_content),
            "after_hash": self._content_hash(new_content),
            "before_exists": before_exists,
            "status": "pending",
            "diff": self.build_diff(relative_path, old_content, new_content),
        }
        self._previews[plan["preview_id"]] = plan
        self._latest_preview_id = plan["preview_id"]
        return plan

    def build_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
        return "\n".join(diff) or f"No content changes for {relative_path}"

    async def apply_plan(self, plan: Dict):
        target_path = self.validate_plan(plan)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await self.write_text(target_path, plan["new_content"])
        plan["status"] = "applied"
        if plan.get("preview_id"):
            self._previews[plan["preview_id"]] = plan
            if self._latest_preview_id == plan["preview_id"]:
                self._latest_preview_id = ""

    def validate_plan(self, plan: Dict) -> Path:
        if plan.get("status") != "pending":
            raise PreviewStateError(
                f"Preview is not pending: {plan.get('status', 'unknown')}"
            )
        target_path = self.resolve_vault_path(plan["path"])
        current_exists = target_path.exists()
        current_content = self._read_existing(target_path) if current_exists else ""
        if current_exists != bool(plan.get("before_exists", bool(plan.get("old_content")))):
            plan["status"] = "stale"
            raise StalePreviewError(
                f"File existence changed after preview: {plan.get('relative_path', target_path.name)}"
            )
        expected_hash = plan.get("before_hash", self._content_hash(plan.get("old_content", "")))
        if self._content_hash(current_content) != expected_hash:
            plan["status"] = "stale"
            raise StalePreviewError(
                f"File changed after preview: {plan.get('relative_path', target_path.name)}"
            )
        new_content = plan.get("new_content")
        if not isinstance(new_content, str):
            raise PreviewStateError("Preview content is invalid.")
        if len(new_content.encode("utf-8")) > self.max_write_bytes:
            raise PreviewStateError("Preview content exceeds the 2 MB write limit.")
        expected_after_hash = plan.get("after_hash")
        if expected_after_hash and self._content_hash(new_content) != expected_after_hash:
            raise PreviewStateError("Preview content changed after it was built.")
        return target_path

    async def write_text(self, target_path: Path, content: str):
        try:
            from core.file_ops import atomic_write_obsidian_note

            await atomic_write_obsidian_note(str(target_path), content)
            return
        except ModuleNotFoundError:
            pass

        temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        await asyncio.to_thread(temp_path.write_text, content, encoding="utf-8")
        await asyncio.to_thread(os.replace, temp_path, target_path)

    def build_preview(self, note_path: str, new_content: str, action: str = "write") -> Dict:
        plan = self.build_plan(note_path, new_content, action)
        return {
            "status": "success",
            "data": plan,
            "preview": plan,
            "preview_id": plan["preview_id"],
            "preview_status": plan["status"],
            "path": plan["path"],
            "relative_path": plan["relative_path"],
            "diff": plan["diff"],
        }

    def get_preview(self, preview_id: str) -> Optional[Dict]:
        return self._previews.get(preview_id)

    def get_latest_preview(
        self,
        note_path: str = "",
        new_content: Optional[str] = None,
    ) -> Optional[Dict]:
        candidates = []
        if self._latest_preview_id:
            latest = self.get_preview(self._latest_preview_id)
            if latest:
                candidates.append(latest)
        candidates.extend(reversed(list(self._previews.values())))

        target = str(self.resolve_vault_path(note_path)) if note_path else ""
        seen = set()
        for plan in candidates:
            preview_id = plan.get("preview_id")
            if preview_id in seen:
                continue
            seen.add(preview_id)
            if plan.get("status") != "pending":
                continue
            if target and plan.get("path") != target:
                continue
            if new_content is not None and plan.get("new_content") != new_content:
                continue
            return plan
        return None

    def reject_preview(self, preview_id: str = "") -> Dict:
        plan = self.get_preview(preview_id) if preview_id else self.get_latest_preview()
        if not plan or plan.get("status") != "pending":
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Pending write preview was not found.",
            }
        plan["status"] = "rejected"
        if self._latest_preview_id == plan["preview_id"]:
            self._latest_preview_id = ""
        return {
            "status": "success",
            "message": f"Rejected write preview: {plan['relative_path']}",
            "preview_id": plan["preview_id"],
            "preview_status": plan["status"],
        }

    async def apply_write(
        self,
        note_path: str,
        new_content: str,
        preview_id: str = "",
    ) -> Dict:
        plan = (
            self.get_preview(preview_id)
            if preview_id
            else self.get_latest_preview(note_path, new_content)
        )
        if plan is None:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Pending write preview is missing or expired. Build a new preview.",
            }
        elif plan["path"] != str(self.resolve_vault_path(note_path)) or plan["new_content"] != new_content:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Preview content does not match the requested write.",
            }
        try:
            await self.apply_plan(plan)
            return {
                "status": "success",
                "message": f"Applied write preview: {plan['relative_path']}",
                "preview_id": plan["preview_id"],
                "relative_path": plan["relative_path"],
            }
        except StalePreviewError as exc:
            return {
                "status": "error",
                "error_code": "STALE_PREVIEW",
                "message": str(exc),
                "preview_id": plan.get("preview_id", ""),
            }
        except PreviewStateError as exc:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": str(exc),
                "preview_id": plan.get("preview_id", ""),
            }

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_existing(self, target_path: Path) -> str:
        if not target_path.is_file():
            raise ValueError("Vault write target must be a Markdown file.")
        if target_path.stat().st_size > self.max_write_bytes:
            raise ValueError("Existing note exceeds the 2 MB write limit.")
        return target_path.read_text(encoding="utf-8", errors="ignore")

    @classmethod
    def audit_details(cls, plan: Dict) -> str:
        """Return content-free metadata suitable for persistent audit logs."""
        new_content = plan.get("new_content")
        return json.dumps(
            {
                "preview_id": plan.get("preview_id", ""),
                "action": plan.get("action", "write"),
                "relative_path": plan.get("relative_path", ""),
                "before_hash": plan.get("before_hash", ""),
                "after_hash": plan.get("after_hash", ""),
                "bytes": len(new_content.encode("utf-8"))
                if isinstance(new_content, str)
                else 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


class StalePreviewError(RuntimeError):
    """Raised when a target changed after its diff was presented."""


class PreviewStateError(RuntimeError):
    """Raised when an applied/rejected/stale preview is reused."""


async def confirm_and_apply_plan(deps, plan: Dict, event_type: str, summary: str) -> bool:
    """Asks the UI to approve a diff preview before applying a write plan."""
    from core import db

    audit_details = WritePreviewService.audit_details(plan)
    db.add_audit_event(event_type, "proposed", summary, audit_details)
    if not getattr(deps, "request_override", None):
        db.add_audit_event(event_type, "denied", f"{summary}: no approval callback", audit_details)
        return False

    try:
        approved = await deps.request_override(
            f"DIFF_PREVIEW_REQUIRED\n{summary}\n\n{plan.get('diff', '')}"
        )
    except Exception as exc:
        db.add_audit_event(
            event_type,
            "failed",
            f"{summary}: approval callback failed ({type(exc).__name__})",
            audit_details,
        )
        raise
    if not approved:
        plan["status"] = "rejected"
        db.add_audit_event(event_type, "denied", summary, audit_details)
        return False

    try:
        await WritePreviewService(deps.obsidian_vault_path).apply_plan(plan)
    except StalePreviewError as exc:
        db.add_audit_event(event_type, "stale", summary, audit_details)
        return False
    except Exception as exc:
        db.add_audit_event(
            event_type,
            "failed",
            f"{summary}: {type(exc).__name__}",
            audit_details,
        )
        raise
    db.add_audit_event(event_type, "applied", summary, audit_details)
    return True
