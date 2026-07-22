from __future__ import annotations

import asyncio
import difflib
import os
from pathlib import Path
from typing import Dict


class WritePreviewService:
    """Builds diff previews and applies confirmed vault writes."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()

    def resolve_vault_path(self, note_path: str) -> Path:
        candidate = Path(note_path)
        if not candidate.is_absolute():
            candidate = self.vault_path / candidate
        resolved = candidate.resolve()
        if resolved != self.vault_path and self.vault_path not in resolved.parents:
            raise ValueError(f"Path is outside vault: {note_path}")
        return resolved

    def build_plan(self, note_path: str, new_content: str, action: str = "write") -> Dict:
        target_path = self.resolve_vault_path(note_path)
        old_content = target_path.read_text(encoding="utf-8", errors="ignore") if target_path.exists() else ""
        relative_path = str(target_path.relative_to(self.vault_path))
        return {
            "action": action,
            "path": str(target_path),
            "relative_path": relative_path,
            "old_content": old_content,
            "new_content": new_content,
            "diff": self.build_diff(relative_path, old_content, new_content),
        }

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
        target_path = Path(plan["path"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await self.write_text(target_path, plan["new_content"])

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


async def confirm_and_apply_plan(deps, plan: Dict, event_type: str, summary: str) -> bool:
    """Asks the UI to approve a diff preview before applying a write plan."""
    from core import db

    db.add_audit_event(event_type, "proposed", summary, plan.get("diff", ""))
    if not getattr(deps, "request_override", None):
        db.add_audit_event(event_type, "denied", f"{summary}: no approval callback", plan.get("diff", ""))
        return False

    approved = await deps.request_override(
        f"DIFF_PREVIEW_REQUIRED\n{summary}\n\n{plan.get('diff', '')}"
    )
    if not approved:
        db.add_audit_event(event_type, "denied", summary, plan.get("diff", ""))
        return False

    await WritePreviewService(deps.obsidian_vault_path).apply_plan(plan)
    db.add_audit_event(event_type, "applied", summary, plan.get("diff", ""))
    return True
