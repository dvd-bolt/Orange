from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List

from core import db
from core.graph_api import get_notes_graph
from core.services.write_preview_service import WritePreviewService


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[(?P<done>[ xX])\]\s+(?P<text>.+)$", re.MULTILINE)
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class ProjectPagesService:
    """Builds generated project overview pages without rewriting source notes."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.writer = WritePreviewService(vault_path)

    def preview_project_pages(self, limit: int = 30) -> Dict:
        projects = self._discover_projects(limit)
        plans = []
        page_links = []
        for project in projects:
            content = self._build_project_page(project)
            target_rel = f"_Orange/Project Pages/{self._safe_filename(project['title'])}.md"
            plans.append(self.writer.build_plan(target_rel, content, action="project_page"))
            page_links.append(f"- [[{Path(target_rel).stem}]] - source: `{project['relative_path']}`")

        index_content = "# Project Pages\n\n" + "\n".join(page_links) + "\n"
        plans.insert(0, self.writer.build_plan("_Orange/Project Pages/Project Index.md", index_content, action="project_index"))
        db.add_audit_event("project_pages", "proposed", f"Generated {len(projects)} project page previews")
        return {"status": "success", "plans": plans, "count": len(projects)}

    async def apply_project_pages(self) -> Dict:
        preview = self.preview_project_pages()
        for plan in preview["plans"]:
            await self.writer.apply_plan(plan)
        db.add_audit_event("project_pages", "applied", f"Applied {len(preview['plans'])} project page writes")
        return {"status": "success", "message": f"Project pages updated: {len(preview['plans'])} files", "plans": preview["plans"]}

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

        graph = get_notes_graph(str(self.vault_path))
        project_nodes = [node for node in graph["nodes"] if node.get("type") == "project"][:limit]
        for node in project_nodes:
            file_path = self.vault_path / node["path"]
            if file_path.exists():
                projects.append(self._read_project(file_path))
        return projects

    def _read_project(self, file_path: Path) -> Dict:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        rel = str(file_path.relative_to(self.vault_path))
        title = self._extract_title(content) or file_path.stem
        return {"title": title, "path": str(file_path), "relative_path": rel, "content": content}

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
        if not self.vault_path.exists():
            return []
        result = []
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
            for filename in files:
                if filename.endswith(".md"):
                    result.append(Path(root) / filename)
        return sorted(result)

    def _extract_title(self, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _safe_filename(self, title: str) -> str:
        value = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().replace(" ", "_")
        return value[:80] or "Project"
