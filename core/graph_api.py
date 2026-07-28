from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.path_safety import VaultPathResolver

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def get_notes_graph(
    vault_path: str,
    *,
    exclude_generated: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build a path-stable graph for Markdown notes in an Obsidian vault."""
    resolver = VaultPathResolver(vault_path)
    root = resolver.root
    if not root.is_dir():
        return {"nodes": [], "links": []}

    records: Dict[str, Dict[str, Any]] = {}
    aliases: Dict[str, Set[str]] = defaultdict(set)

    for raw_path in resolver.iter_notes(exclude_generated=exclude_generated):
        try:
            relative = raw_path.relative_to(root)
        except ValueError:
            continue

        relative_path = relative.as_posix()
        note_id = relative.with_suffix("").as_posix()
        try:
            content = resolver.read_note_text(raw_path)
        except OSError:
            content = ""

        normalized_parts = {part.lower() for part in relative.parts}
        note_type = "note"
        group = 1
        if "04-projects" in normalized_parts or "projects" in normalized_parts:
            note_type = "project"
            group = 2
        elif "_inbox" in normalized_parts:
            note_type = "inbox"
            group = 3

        label = raw_path.stem
        records[note_id] = {
            "id": note_id,
            "label": label,
            "group": group,
            "path": relative_path,
            "type": note_type,
            "content": content,
        }
        aliases[note_id.lower()].add(note_id)
        aliases[label.lower()].add(note_id)
        for alias in _extract_aliases(content):
            aliases[alias.lower()].add(note_id)

    links: List[Dict[str, Any]] = []
    linked_pairs: Set[tuple[str, str]] = set()
    outgoing: Dict[str, Set[str]] = defaultdict(set)

    for source_id, record in records.items():
        for raw_target in WIKILINK_PATTERN.findall(record["content"]):
            target_id = _resolve_wikilink(raw_target.strip(), source_id, records, aliases)
            if not target_id or target_id == source_id:
                continue
            outgoing[source_id].add(target_id)
            pair = tuple(sorted((source_id, target_id)))
            if pair in linked_pairs:
                continue
            linked_pairs.add(pair)
            links.append({"source": source_id, "target": target_id, "value": 1})

    degrees = {note_id: 0 for note_id in records}
    for link in links:
        degrees[link["source"]] += 1
        degrees[link["target"]] += 1

    nodes = []
    for note_id, record in records.items():
        suggestions = _suggest_links(note_id, record["content"], records, outgoing[note_id])
        nodes.append({
            "id": note_id,
            "label": record["label"],
            "group": record["group"],
            "path": record["path"],
            "type": record["type"],
            "degree": degrees[note_id],
            "orphan": degrees[note_id] == 0,
            "suggested_links": suggestions,
        })

    links.sort(key=lambda item: (item["source"].lower(), item["target"].lower()))
    return {"nodes": nodes, "links": links}


def _resolve_wikilink(
    raw_target: str,
    source_id: str,
    records: Dict[str, Dict[str, Any]],
    aliases: Dict[str, Set[str]],
) -> Optional[str]:
    normalized = raw_target.replace("\\", "/").strip().removesuffix(".md")
    exact = aliases.get(normalized.lower(), set())
    if len(exact) == 1:
        return next(iter(exact))

    source_parent = Path(source_id).parent
    sibling = (source_parent / normalized).as_posix()
    if sibling in records:
        return sibling

    basename_matches = aliases.get(Path(normalized).name.lower(), set())
    if len(basename_matches) == 1:
        return next(iter(basename_matches))
    return None


def _suggest_links(
    source_id: str,
    content: str,
    records: Dict[str, Dict[str, Any]],
    existing_targets: Set[str],
) -> List[str]:
    suggestions = []
    lowered = _content_for_suggestions(content).lower()
    for candidate_id, candidate in sorted(records.items(), key=lambda item: item[0].lower()):
        if candidate_id == source_id or candidate_id in existing_targets:
            continue
        label = candidate["label"].strip()
        if len(label) < 5:
            continue
        pattern = rf"(?<![\w]){re.escape(label.lower())}(?![\w])"
        matches = re.findall(pattern, lowered)
        if len(label) < 8 and " " not in label and len(matches) < 2:
            continue
        if matches:
            suggestions.append(candidate_id)
        if len(suggestions) >= 5:
            break
    return suggestions


def _extract_aliases(content: str) -> List[str]:
    if not content.startswith("---"):
        return []
    end = content.find("\n---", 3)
    if end == -1:
        return []
    frontmatter = content[3:end]
    aliases = []
    lines = frontmatter.splitlines()
    collecting_list = False
    for line in lines:
        key_match = re.match(r"(?i)^\s*aliases?\s*:\s*(.*)$", line)
        if key_match:
            value = key_match.group(1).strip()
            collecting_list = not value
            if value.startswith("[") and value.endswith("]"):
                aliases.extend(
                    item.strip().strip("\"'")
                    for item in value[1:-1].split(",")
                    if item.strip()
                )
            elif value:
                aliases.append(value.strip("\"'"))
            continue
        if collecting_list:
            item_match = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if item_match:
                aliases.append(item_match.group(1).strip().strip("\"'"))
                continue
            if line.strip():
                collecting_list = False
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _content_for_suggestions(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4:]
    content = re.sub(r"```.*?```", " ", content, flags=re.DOTALL)
    content = WIKILINK_PATTERN.sub(" ", content)
    return content
