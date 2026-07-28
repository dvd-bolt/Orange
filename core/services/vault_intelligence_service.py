from __future__ import annotations

import math
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set

from core import db
from core.graph_api import get_notes_graph
from core.path_safety import VaultPathResolver


TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[(?P<done>[ xX])\]\s+(?P<text>.+)$", re.MULTILINE)
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-я0-9_]{3,}")

STOP_WORDS = {
    "and", "the", "for", "with", "this", "that", "from", "into", "have", "will", "what", "when", "where",
    "как", "что", "это", "для", "или", "если", "надо", "нужно", "будет", "есть", "все", "при", "над",
    "про", "его", "она", "они", "уже", "тут", "там", "так", "без", "под", "после", "перед",
}

POSITIVE_MARKERS = {
    "must", "should", "use", "enable", "keep", "do", "add", "нужно", "надо", "использовать",
    "включить", "делать", "оставить", "добавить", "решили", "решение",
}

NEGATIVE_MARKERS = {
    "must not", "should not", "do not", "dont", "don't", "avoid", "disable", "remove", "skip",
    "нельзя", "не надо", "не делать", "избегать", "выключить", "убрать", "удалить", "не использовать",
}


class VaultIntelligenceService:
    """Local analytical layer over the Obsidian vault."""

    def __init__(self, vault_path: str):
        self._resolver = VaultPathResolver(vault_path)
        self.vault_path = self._resolver.root

    def build_time_machine(self, days: int = 90) -> Dict:
        days = max(1, min(int(days), 3650))
        records = self._records()
        now = datetime.now()
        horizon = now - timedelta(days=days)
        recent = [record for record in records if record["modified_at"] >= horizon]
        git_timeline = self._git_timeline(days)
        history_source = "git" if git_timeline else "file_activity"
        timeline = git_timeline or self._mtime_timeline(records, now, days)

        themes = self._top_terms(recent or records, limit=12)
        bursts = sorted(recent, key=lambda record: (record["task_count"], record["link_count"], record["size"]), reverse=True)[:12]
        quiet = sorted(records, key=lambda record: record["modified_at"])[:12]
        db.add_audit_event("vault_time_machine", "viewed", f"Built vault time machine for {days} days")
        return {
            "status": "success",
            "generated_at": now.isoformat(timespec="seconds"),
            "scope_days": days,
            "history_source": history_source,
            "total_notes": len(records),
            "recent_notes": len(recent),
            "themes": themes,
            "timeline": timeline,
            "activity_bursts": [self._brief_note(record) for record in bursts],
            "quietest_notes": [self._brief_note(record) for record in quiet],
        }

    def find_contradictions(self, limit: int = 40) -> Dict:
        limit = max(1, min(int(limit), 200))
        records = self._records()
        statements = self._decision_statements(records)
        findings = []

        for index, left in enumerate(statements):
            for right in statements[index + 1:]:
                if left["polarity"] == right["polarity"]:
                    continue
                overlap = self._jaccard(left["terms"], right["terms"])
                if overlap < 0.22:
                    continue
                findings.append({
                    "type": "policy_conflict",
                    "severity": round(min(0.99, overlap + 0.35), 2),
                    "topic": ", ".join(sorted(left["terms"] & right["terms"])[:5]) or "shared topic",
                    "left": left,
                    "right": right,
                    "suggestion": "Pick one current rule, mark the older line as superseded, and link both notes.",
                    "confidence": "possible",
                })
                if len(findings) >= limit:
                    break
            if len(findings) >= limit:
                break

        task_states: Dict[str, Dict[str, List[Dict]]] = {}
        for record in records:
            for task in record["tasks"]:
                normalized = self._normalize_task(task["text"])
                if not normalized:
                    continue
                bucket = task_states.setdefault(normalized, {"open": [], "done": []})
                bucket["done" if task["done"] else "open"].append({
                    "path": record["path"],
                    "line": task["line"],
                    "text": task["text"],
                })

        for normalized, states in task_states.items():
            if states["open"] and states["done"]:
                findings.append({
                    "type": "task_state_conflict",
                    "severity": 0.7,
                    "topic": normalized,
                    "left": states["open"][0],
                    "right": states["done"][0],
                    "suggestion": "Decide whether this task is actually done, then remove or archive the stale duplicate.",
                    "confidence": "possible",
                })

        findings.sort(key=lambda item: item["severity"], reverse=True)
        db.add_audit_event("contradiction_finder", "viewed", f"Found {len(findings)} possible contradictions")
        return {"status": "success", "count": len(findings), "findings": findings[:limit]}

    def run_agent_debate(self, topic: str = "") -> Dict:
        return {
            "status": "error",
            "error_code": "NOT_CONFIGURED",
            "message": (
                "Agent Debate requires a configured independent multi-model runner."
            ),
        }

    def find_dormant_projects(self, stale_days: int = 30) -> Dict:
        stale_days = max(1, min(int(stale_days), 3650))
        records = [record for record in self._records() if self._is_project(record)]
        cutoff = datetime.now() - timedelta(days=stale_days)
        dormant = []
        for record in records:
            open_tasks = [task for task in record["tasks"] if not task["done"]]
            if record["modified_at"] > cutoff and open_tasks:
                continue
            age_days = max(0, (datetime.now() - record["modified_at"]).days)
            score = min(100, age_days + len(open_tasks) * 12 + max(0, 4 - record["link_count"]) * 5)
            dormant.append({
                **self._brief_note(record),
                "age_days": age_days,
                "open_tasks": [task["text"] for task in open_tasks[:8]],
                "score": score,
                "revive_action": self._revive_action(record, open_tasks),
            })
        dormant.sort(key=lambda item: item["score"], reverse=True)
        db.add_audit_event("dormant_project_radar", "viewed", f"Found {len(dormant)} dormant projects")
        return {"status": "success", "stale_days": stale_days, "items": dormant[:40]}

    def build_operating_manual(self) -> Dict:
        records = self._records()
        graph = get_notes_graph(str(self.vault_path), exclude_generated=True)
        orphan_count = sum(1 for node in graph["nodes"] if node.get("orphan"))
        open_tasks = [task for record in records for task in record["tasks"] if not task["done"]]
        themes = self._top_terms(records, limit=8)
        audit_events = db.list_audit_events(30)
        statements = self._decision_statements(records)
        explicit_principles = []
        seen_principles = set()
        for statement in statements:
            line = statement["line"]
            normalized = line.lower()
            if normalized in seen_principles:
                continue
            seen_principles.add(normalized)
            explicit_principles.append(f"{line} ({statement['path']})")
            if len(explicit_principles) >= 8:
                break

        event_counts = Counter(event["event_type"] for event in audit_events)
        review_count = event_counts.get("weekly_review", 0)
        used_features = [
            f"{event_type}: {count} recent event(s)"
            for event_type, count in event_counts.most_common(6)
        ]
        from core.runtime_settings import load_runtime_settings

        runtime_settings = load_runtime_settings()

        manual = {
            "title": "Personal Operating Manual",
            "principles": explicit_principles or ["No explicit operating principles were found in the vault."],
            "current_context": [
                f"Vault notes: {len(records)}",
                f"Open tasks detected: {len(open_tasks)}",
                f"Orphan notes detected: {orphan_count}",
                f"Dominant themes: {', '.join(term['term'] for term in themes[:5]) or 'not enough signal'}",
            ],
            "how_to_work_with_orange": used_features or ["No recent ORANGE usage patterns recorded."],
            "review_rhythm": [
                f"Weekly review events recorded in the latest audit window: {review_count}",
                f"Recent audit events considered: {len(audit_events)}",
            ],
            "safety_contract": [
                f"Auto backup: {runtime_settings.get('auto_backup_enabled', 'OFF')}",
                f"Auto push: {runtime_settings.get('auto_push_enabled', 'OFF')}",
                "Vault writes require the configured approval callback.",
            ],
            "recent_system_events": [
                f"{event['timestamp']} / {event['event_type']} / {event['status']}: {event['summary']}"
                for event in audit_events[:8]
            ],
        }
        db.add_audit_event("operating_manual", "viewed", "Built personal operating manual")
        return {"status": "success", "manual": manual}

    def _git_timeline(self, days: int) -> List[Dict]:
        try:
            repo_result = subprocess.run(
                ["git", "-C", str(self.vault_path), "rev-parse", "--show-toplevel"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if repo_result.returncode != 0:
            return []
        repo_root = Path(repo_result.stdout.strip()).resolve()
        try:
            self.vault_path.relative_to(repo_root)
        except ValueError:
            return []

        try:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "-C",
                    str(self.vault_path),
                    "log",
                    f"--since={max(1, days)} days ago",
                    "--date=iso-strict",
                    "--format=%H%x1f%ad%x1f%s",
                    "--name-only",
                    "--",
                    ".",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []

        timeline = []
        current = None
        for line in result.stdout.splitlines():
            if "\x1f" in line:
                commit_hash, timestamp, subject = line.split("\x1f", 2)
                current = {
                    "period": timestamp,
                    "commit": commit_hash[:12],
                    "subject": subject,
                    "notes": [],
                }
                timeline.append(current)
                continue
            path = line.strip()
            if not current or not path.lower().endswith(".md"):
                continue
            candidate = (repo_root / path).resolve(strict=False)
            try:
                vault_relative = candidate.relative_to(self.vault_path).as_posix()
            except ValueError:
                candidate = (self.vault_path / path).resolve(strict=False)
                try:
                    vault_relative = candidate.relative_to(self.vault_path).as_posix()
                except ValueError:
                    continue
            if vault_relative.lower().startswith("_orange/"):
                continue
            current["notes"].append({
                "path": vault_relative,
                "title": Path(vault_relative).stem,
                "modified_at": current["period"],
                "open_task_count": 0,
                "link_count": 0,
                "size": 0,
            })

        for bucket in timeline:
            bucket["notes"] = bucket["notes"][:12]
            bucket["count"] = len(bucket["notes"])
        return [bucket for bucket in timeline if bucket["count"]][:40]

    def _mtime_timeline(self, records: List[Dict], now: datetime, days: int) -> List[Dict]:
        timeline = []
        for index in range(0, days, 7):
            start = now - timedelta(days=index + 7)
            end = now - timedelta(days=index)
            notes = [record for record in records if start <= record["modified_at"] < end]
            if notes:
                timeline.append({
                    "period": f"{start.date().isoformat()}..{end.date().isoformat()}",
                    "count": len(notes),
                    "notes": [self._brief_note(record) for record in notes[:8]],
                })
        return timeline

    def _records(self) -> List[Dict]:
        records = []
        for path in self._resolver.iter_notes(exclude_generated=True):
            rel = path.relative_to(self.vault_path).as_posix()
            try:
                records.append(self._record(path, rel))
            except OSError:
                continue
        return sorted(records, key=lambda record: record["modified_at"], reverse=True)

    def _record(self, path: Path, rel: str) -> Dict:
        content = self._resolver.read_note_text(path)
        tasks = []
        for match in TASK_PATTERN.finditer(content):
            tasks.append({
                "done": match.group("done").lower() == "x",
                "text": match.group("text").strip(),
                "line": content.count("\n", 0, match.start()) + 1,
            })
        links = sorted(set(WIKILINK_PATTERN.findall(content)))
        stat = path.stat()
        title = self._extract_title(content) or path.stem
        terms = self._terms(content)
        return {
            "path": rel,
            "title": title,
            "content": content,
            "modified_at": datetime.fromtimestamp(stat.st_mtime),
            "size": stat.st_size,
            "tasks": tasks,
            "task_count": len(tasks),
            "open_task_count": sum(1 for task in tasks if not task["done"]),
            "links": links,
            "link_count": len(links),
            "terms": terms,
        }

    def _decision_statements(self, records: List[Dict]) -> List[Dict]:
        statements = []
        for record in records:
            for line_number, line in enumerate(record["content"].splitlines(), start=1):
                stripped = line.strip("-*# \t")
                lowered = stripped.lower()
                if len(stripped) < 10:
                    continue
                polarity = ""
                if any(self._contains_marker(lowered, marker) for marker in NEGATIVE_MARKERS):
                    polarity = "negative"
                elif any(self._contains_marker(lowered, marker) for marker in POSITIVE_MARKERS):
                    polarity = "positive"
                if not polarity:
                    continue
                terms = self._terms(stripped)
                if terms:
                    statements.append({
                        "path": record["path"],
                        "line_number": line_number,
                        "line": stripped[:260],
                        "polarity": polarity,
                        "terms": terms,
                    })
        return statements[:500]

    def _top_terms(self, records: List[Dict], limit: int) -> List[Dict]:
        counter = Counter()
        for record in records:
            counter.update(record["terms"])
        return [{"term": term, "count": count} for term, count in counter.most_common(limit)]

    def _relevant_records(self, records: List[Dict], topic: str, limit: int) -> List[Dict]:
        topic_terms = self._terms(topic)
        scored = []
        for record in records:
            overlap = len(topic_terms & record["terms"])
            if topic.lower() in record["content"].lower():
                overlap += 3
            if overlap:
                scored.append((overlap + math.log(record["link_count"] + 1), record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:limit]] or records[:limit]

    def _brief_note(self, record: Dict) -> Dict:
        return {
            "path": record["path"],
            "title": record["title"],
            "modified_at": record["modified_at"].isoformat(timespec="seconds"),
            "open_task_count": record["open_task_count"],
            "link_count": record["link_count"],
            "size": record["size"],
        }

    def _is_project(self, record: Dict) -> bool:
        rel = record["path"].lower()
        content = record["content"].lower()
        return "project" in rel or "04-projects" in rel or "# project" in content or "проект" in content

    def _revive_action(self, record: Dict, open_tasks: List[Dict]) -> str:
        if open_tasks:
            return f"Pick or archive first task: {open_tasks[0]['text']}"
        if record["link_count"] == 0:
            return "Either link this project to an active note or archive it."
        return "Add a next action or mark the project complete."

    def _default_topic(self, records: List[Dict]) -> str:
        terms = self._top_terms(records, 3)
        return " / ".join(term["term"] for term in terms) or "ORANGE project direction"

    def _extract_title(self, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _terms(self, text: str) -> Set[str]:
        terms = set()
        for word in WORD_PATTERN.findall(text.lower()):
            if word in STOP_WORDS or len(word) < 3:
                continue
            terms.add(word)
        return terms

    def _jaccard(self, left: Set[str], right: Set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _normalize_task(self, text: str) -> str:
        words = [word for word in WORD_PATTERN.findall(text.lower()) if word not in STOP_WORDS]
        return " ".join(words[:12])

    def _contains_marker(self, text: str, marker: str) -> bool:
        return bool(re.search(rf"(?<![\w]){re.escape(marker)}(?![\w])", text))
