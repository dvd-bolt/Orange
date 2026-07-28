from __future__ import annotations

import os
import re
import asyncio
import hashlib
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.path_safety import VaultPathResolver


class InboxService:
    """Creates review proposals for files in `_Inbox` and applies them only after user confirmation."""

    max_note_bytes = 2 * 1024 * 1024

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root
        self.inbox_path = self.vault_path / "_Inbox"
        self._proposals: Dict[str, Dict] = {}
        self._proposal_keys: Dict[tuple[str, str], str] = {}
        self._proposal_lock = threading.RLock()
        self._apply_lock = asyncio.Lock()

    def _resolve_inside_vault(self, file_path: str) -> Path:
        resolved = self._resolver.resolve_note(file_path, must_exist=True)
        try:
            resolved.relative_to(self.inbox_path.resolve(strict=False))
        except ValueError as exc:
            raise ValueError(f"Smart Inbox only accepts notes from _Inbox: {file_path}") from exc
        return resolved

    def classify_text(self, text: str) -> Dict:
        lowered = text.lower()
        urls = re.findall(r"https?://\S+", text)
        scores = {
            "task": 0.9 if re.search(r"(^|\n)\s*[-*]\s*\[[ xX]\]|\b(todo|task|надо|сделать|дедлайн)\b", lowered) else 0.0,
            "link": 0.82 if urls else 0.0,
            "meeting": 0.8 if re.search(r"\b(meeting|митинг|созвон|встреча|agenda|повестка)\b", lowered) else 0.0,
            "project": 0.76 if re.search(r"\b(project|проект|roadmap|milestone|релиз)\b", lowered) else 0.0,
            "idea": 0.55,
        }
        priority = {"task": 0, "meeting": 1, "project": 2, "link": 3, "idea": 4}
        ranked = sorted(scores.items(), key=lambda item: (-item[1], priority[item[0]]))
        category, confidence = ranked[0]
        alternatives = [
            {"category": name, "confidence": score}
            for name, score in ranked[1:]
            if score > 0
        ]

        first_line = next((line.strip("# -*\t ") for line in text.splitlines() if line.strip()), "")
        summary = first_line[:180] or "Empty inbox note"
        return {
            "category": category,
            "confidence": confidence,
            "summary": summary,
            "links": urls[:5],
            "action_label": self._action_label(category),
            "alternatives": alternatives,
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
        if resolved.stat().st_size > self.max_note_bytes:
            raise ValueError("Smart Inbox note exceeds the 2 MB limit.")
        content = resolved.read_text(encoding="utf-8", errors="ignore")
        classification = self.classify_text(content)
        relative_path = resolved.relative_to(self.vault_path).as_posix()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        proposal_key = (relative_path, content_hash)
        with self._proposal_lock:
            existing_id = self._proposal_keys.get(proposal_key)
            existing = self._proposals.get(existing_id or "")
            if existing and existing.get("proposal_status") == "pending":
                return dict(existing)

        proposal = {
            "status": "success",
            "proposal_status": "pending",
            "proposal_id": uuid.uuid4().hex,
            "file_path": relative_path,
            "relative_path": relative_path,
            "filename": resolved.name,
            "content_hash": content_hash,
            **classification,
        }
        with self._proposal_lock:
            self._proposals[proposal["proposal_id"]] = proposal
            self._proposal_keys[proposal_key] = proposal["proposal_id"]
        return dict(proposal)

    def list_proposals(self, limit: int = 50) -> List[Dict]:
        if not self.inbox_path.exists():
            return []
        safe_limit = max(1, min(int(limit), 200))
        proposals = []
        applied_sources = self._applied_sources()
        candidates = []
        for file_path in self._resolver.iter_notes():
            try:
                file_path.relative_to(self.inbox_path.resolve(strict=False))
                modified_at = file_path.stat().st_mtime
            except (OSError, ValueError):
                continue
            candidates.append((modified_at, file_path))

        candidates.sort(
            key=lambda item: (-item[0], item[1].as_posix().casefold())
        )
        for _, file_path in candidates:
            if file_path.name == "Inbox Review.md":
                continue
            relative_path = file_path.relative_to(self.vault_path).as_posix()
            try:
                proposal = self.build_proposal(str(file_path))
                applied_hashes = applied_sources.get(relative_path, set())
                if "*" in applied_hashes or proposal["content_hash"] in applied_hashes:
                    continue
                proposals.append(proposal)
            except Exception as exc:
                proposals.append({
                    "status": "error",
                    "file_path": file_path.relative_to(self.vault_path).as_posix(),
                    "filename": file_path.name,
                    "message": f"Proposal could not be built: {type(exc).__name__}",
                })
            if len(proposals) >= safe_limit:
                break
        return proposals

    async def apply_proposal(
        self,
        file_path: str,
        category: str = "",
        proposal_id: str = "",
    ) -> Dict:
        with self._proposal_lock:
            stored = self._proposals.get(str(proposal_id)) if proposal_id else None
            proposal = dict(stored) if stored else None
        if proposal is None:
            proposal = self.build_proposal(file_path)
        if proposal.get("proposal_status") != "pending":
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Smart Inbox proposal is no longer pending.",
                "proposal_id": proposal.get("proposal_id", ""),
            }
        resolved = self._resolve_inside_vault(file_path)
        resolved_relative = resolved.relative_to(self.vault_path).as_posix()
        if resolved_relative != proposal.get("relative_path"):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Smart Inbox proposal does not match the requested file.",
                "proposal_id": proposal.get("proposal_id", ""),
            }
        current_content = resolved.read_text(encoding="utf-8", errors="ignore")
        current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
        if current_hash != proposal.get("content_hash"):
            self._set_proposal_status(proposal["proposal_id"], "stale")
            return {
                "status": "error",
                "error_code": "STALE_PREVIEW",
                "message": "Inbox note changed after the proposal was shown. Build a new proposal.",
                "proposal_id": proposal["proposal_id"],
            }

        category = category or proposal["category"]
        if category not in {"task", "idea", "link", "project", "meeting"}:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"Unsupported Smart Inbox category: {category}",
            }
        async with self._apply_lock:
            target_path = self._resolver.resolve_note("_Inbox/Inbox Review.md")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and target_path.stat().st_size > self.max_note_bytes:
                raise ValueError("Inbox Review exceeds the 2 MB limit.")
            existing = target_path.read_text(encoding="utf-8", errors="ignore") if target_path.exists() else "# Inbox Review\n\n"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            applied_hashes = self._applied_sources(existing).get(proposal["relative_path"], set())
            if "*" in applied_hashes or proposal["content_hash"] in applied_hashes:
                self._set_proposal_status(proposal["proposal_id"], "applied")
                return {
                    "status": "success",
                    "outcome": "already_applied",
                    "message": f"Inbox proposal was already applied: {proposal['relative_path']}",
                    "proposal_id": proposal["proposal_id"],
                }
            block = (
                f"\n## {timestamp} - {proposal['filename']}\n"
                f"- Category: {category}\n"
                f"- Source path: `{proposal['relative_path']}`\n"
                f"- Source hash: `{proposal['content_hash']}`\n"
                f"- Source: [[{Path(proposal['relative_path']).stem}]]\n"
                f"- Summary: {proposal['summary']}\n"
                f"- Action: {self._action_label(category)}\n"
            )
            new_content = existing.rstrip() + "\n" + block
            if len(new_content.encode("utf-8")) > self.max_note_bytes:
                raise ValueError("Inbox Review would exceed the 2 MB limit.")
            await self._write_review_note(target_path, new_content)
            self._set_proposal_status(proposal["proposal_id"], "applied")
            return {
                "status": "success",
                "outcome": "applied",
                "message": "Inbox proposal applied to _Inbox/Inbox Review.md",
                "proposal_id": proposal["proposal_id"],
                "relative_path": proposal["relative_path"],
                "content_hash": proposal["content_hash"],
                "category": category,
            }

    def _set_proposal_status(self, proposal_id: str, status: str) -> None:
        with self._proposal_lock:
            proposal = self._proposals.get(proposal_id)
            if proposal:
                proposal["proposal_status"] = status

    def _applied_sources(self, review_content: str | None = None) -> Dict[str, set[str]]:
        if review_content is None:
            try:
                review_path = self._resolver.resolve_note(
                    "_Inbox/Inbox Review.md"
                )
            except ValueError:
                return {}
            if not review_path.exists():
                return {}
            if review_path.stat().st_size > self.max_note_bytes:
                return {}
            review_content = review_path.read_text(encoding="utf-8", errors="ignore")
        sources: Dict[str, set[str]] = {}
        blocks = re.split(r"(?=^##\s)", review_content, flags=re.MULTILINE)
        for block in blocks:
            path_match = re.search(
                r"^- Source path:\s*`([^`]+)`\s*$",
                block,
                re.MULTILINE,
            )
            if not path_match:
                continue
            hash_match = re.search(
                r"^- Source hash:\s*`([0-9a-f]{64})`\s*$",
                block,
                re.MULTILINE,
            )
            relative_path = path_match.group(1).strip()
            sources.setdefault(relative_path, set()).add(
                hash_match.group(1) if hash_match else "*"
            )
        return sources

    def _applied_paths(self, review_content: str | None = None) -> set[str]:
        """Compatibility helper retained for older callers/tests."""
        return set(self._applied_sources(review_content))

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
