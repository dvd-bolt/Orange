from __future__ import annotations

import re
import hashlib
import uuid
from pathlib import Path
from typing import Dict, List

from core import db
from core.graph_api import get_notes_graph
from core.path_safety import VaultPathResolver
from core.services.write_preview_service import WritePreviewService
from core.services.write_preview_service import PreviewStateError, StalePreviewError


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[(?P<done>[ xX])\]\s+(?P<text>.+)$", re.MULTILINE)
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class ProjectPagesService:
    """Builds generated project overview pages without rewriting source notes."""

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root
        self.writer = WritePreviewService(vault_path)
        self._previews: Dict[str, Dict] = {}
        self._latest_preview_id = ""

    def preview_project_pages(self, limit: int = 30) -> Dict:
        safe_limit = max(1, min(int(limit), 100))
        projects = self._discover_projects(safe_limit)
        plans = []
        page_links = []
        used_target_names = {"project_index"}
        for project in projects:
            content = self._build_project_page(project)
            target_name = self._safe_filename(project["title"])
            normalized_name = target_name.casefold()
            if normalized_name in used_target_names:
                path_hash = hashlib.sha256(
                    project["relative_path"].encode("utf-8")
                ).hexdigest()[:8]
                target_name = f"{target_name}-{path_hash}"
                normalized_name = target_name.casefold()
            used_target_names.add(normalized_name)
            target_rel = f"_Orange/Project Pages/{target_name}.md"
            plans.append(self.writer.build_plan(target_rel, content, action="project_page"))
            page_links.append(f"- [[{Path(target_rel).stem}]] - source: `{project['relative_path']}`")

        index_content = "# Project Pages\n\n" + "\n".join(page_links) + "\n"
        plans.insert(0, self.writer.build_plan("_Orange/Project Pages/Project Index.md", index_content, action="project_index"))
        preview_id = uuid.uuid4().hex
        source_snapshot = {
            project["relative_path"]: project["content_hash"]
            for project in projects
        }
        self._previews[preview_id] = {
            "plans": plans,
            "source_snapshot": source_snapshot,
            "limit": safe_limit,
        }
        self._latest_preview_id = preview_id
        db.add_audit_event("project_pages", "proposed", f"Generated {len(projects)} project page previews")
        return {
            "status": "success",
            "preview_id": preview_id,
            "plans": plans,
            "count": len(projects),
        }

    async def apply_project_pages(self, preview_id: str = "") -> Dict:
        selected_id = preview_id or self._latest_preview_id
        preview = self._previews.get(selected_id)
        if not preview:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Project Pages preview is missing or expired. Build a new preview.",
            }
        plans = preview["plans"]
        try:
            current_snapshot = {
                project["relative_path"]: project["content_hash"]
                for project in self._discover_projects(preview["limit"])
            }
            if current_snapshot != preview["source_snapshot"]:
                raise StalePreviewError(
                    "Project source notes changed after the preview was built."
                )
            for plan in plans:
                self.writer.validate_plan(plan)
            for plan in plans:
                await self.writer.apply_plan(plan)
        except (StalePreviewError, PreviewStateError) as exc:
            error_code = (
                "STALE_PREVIEW"
                if isinstance(exc, StalePreviewError)
                else "VALIDATION_ERROR"
            )
            db.add_audit_event("project_pages", "stale" if error_code == "STALE_PREVIEW" else "error", str(exc))
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
                "project_pages",
                "failed",
                f"Project Pages write failed: {type(exc).__name__}",
            )
            return {
                "status": "error",
                "error_code": "PROVIDER_ERROR",
                "message": (
                    "Project Pages could not finish writing. Some files may have "
                    "changed; build a new preview before retrying."
                ),
                "preview_id": selected_id,
            }

        self._previews.pop(selected_id, None)
        if self._latest_preview_id == selected_id:
            self._latest_preview_id = ""
        db.add_audit_event("project_pages", "applied", f"Applied {len(plans)} project page writes")
        return {
            "status": "success",
            "message": f"Project pages updated: {len(plans)} files",
            "preview_id": selected_id,
            "plans": plans,
        }

    def reject_project_pages(self, preview_id: str = "") -> Dict:
        selected_id = preview_id or self._latest_preview_id
        preview = self._previews.pop(selected_id, None)
        if not preview:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "Pending Project Pages preview was not found.",
            }
        plans = preview["plans"]
        for plan in plans:
            plan["status"] = "rejected"
        if self._latest_preview_id == selected_id:
            self._latest_preview_id = ""
        db.add_audit_event(
            "project_pages",
            "rejected",
            f"Rejected {len(plans)} Project Pages writes",
        )
        return {
            "status": "success",
            "message": "Project Pages preview rejected.",
            "preview_id": selected_id,
        }

    def _discover_projects(self, limit: int) -> List[Dict]:
        projects = []
        for file_path in self._markdown_files():
            rel = str(file_path.relative_to(self.vault_path))
            rel_lower = rel.lower()
            if "project" not in rel_lower and "04-projects" not in rel_lower:
                continue
            if "_orange" in rel_lower:
                continue
            projects.append(self._read_project(file_path))
            if len(projects) >= limit:
                break

        if projects:
            return projects

        graph = get_notes_graph(str(self.vault_path), exclude_generated=True)
        project_nodes = [node for node in graph["nodes"] if node.get("type") == "project"][:limit]
        for node in project_nodes:
            file_path = self.vault_path / node["path"]
            if file_path.exists():
                projects.append(self._read_project(file_path))
        return projects

    def _read_project(self, file_path: Path) -> Dict:
        content = self._resolver.read_note_text(file_path)
        rel = file_path.relative_to(self.vault_path).as_posix()
        title = self._extract_title(content) or file_path.stem
        return {
            "title": title,
            "path": str(file_path),
            "relative_path": rel,
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    def _build_project_page(self, project: Dict) -> str:
        content = project["content"]
        tasks = TASK_PATTERN.findall(content)
        open_tasks = [text.strip() for done, text in tasks if done == " "]
        done_tasks = [text.strip() for done, text in tasks if done.lower() == "x"]
        links = sorted(set(WIKILINK_PATTERN.findall(content)))
        questions = [line.strip("-*# \t") for line in content.splitlines() if "?" in line][:12]
        decisions = [
            line.strip("-*# \t")
            for line in content.splitlines()
            if any(marker in line.lower() for marker in ("decision", "decided", "решение", "решили"))
        ][:12]

        def bullets(items: List[str], empty: str = "None") -> str:
            if not items:
                return f"- {empty}"
            return "\n".join(f"- {item}" for item in items)

        return (
            f"# {project['title']} - Project Page\n\n"
            f"Source: `{project['relative_path']}`\n\n"
            "## Status\n"
            f"- Open tasks: {len(open_tasks)}\n"
            f"- Done tasks: {len(done_tasks)}\n"
            f"- Linked notes: {len(links)}\n\n"
            "## Open Tasks\n"
            f"{bullets(open_tasks, 'No open tasks found')}\n\n"
            "## Decisions\n"
            f"{bullets(decisions, 'No explicit decisions found')}\n\n"
            "## Open Questions\n"
            f"{bullets(questions, 'No open questions found')}\n\n"
            "## Connected Notes\n"
            f"{bullets([f'[[{link}]]' for link in links], 'No wikilinks found')}\n"
        )

    def _markdown_files(self) -> List[Path]:
        return list(self._resolver.iter_notes(exclude_generated=True))

    def _extract_title(self, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _safe_filename(self, title: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", title)
        value = re.sub(r"\s+", "_", value).strip(" ._")
        return value[:80] or "Project"
