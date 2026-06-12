import os
import re
from typing import Dict, List, Set, Any

def get_notes_graph(vault_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parses all markdown files in the vault to collect note nodes and
    extract their inner Wikilinks [[TargetNote]] as graph edges.
    Returns a D3.js compatible dict with "nodes" and "links".
    """
    abs_vault = os.path.abspath(vault_path)
    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    node_ids: Set[str] = set()

    # Gather md files
    note_files: List[str] = []
    for root, _, files in os.walk(abs_vault):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                # Ignore service/hidden paths
                if any(part.startswith('.') for part in file_path.replace(abs_vault, '').split(os.sep)):
                    continue
                note_files.append(file_path)

    # First pass: collect note nodes
    for file_path in note_files:
        name = os.path.splitext(os.path.basename(file_path))[0]
        if name and not name.startswith('.'):
            node_ids.add(name)
            
            # Simple grouping rule (e.g. check if in 04-projects folder)
            group = 1
            if "04-projects" in file_path:
                group = 2
            elif "_Inbox" in file_path:
                group = 3
                
            nodes.append({"id": name, "group": group})

    # Second pass: extract connections
    for file_path in note_files:
        source_name = os.path.splitext(os.path.basename(file_path))[0]
        if source_name not in node_ids:
            continue
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # Regex matching WikiLinks: [[TargetName]] or [[TargetName|Alias]]
            matches = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)
            for target_name in matches:
                target_name = target_name.strip()
                if target_name in node_ids and source_name != target_name:
                    # De-duplicate links to avoid rendering duplicate lines
                    link_exists = any(
                        (l["source"] == source_name and l["target"] == target_name) or
                        (l["source"] == target_name and l["target"] == source_name)
                        for l in links
                    )
                    if not link_exists:
                        links.append({
                            "source": source_name,
                            "target": target_name,
                            "value": 1
                        })
        except Exception as e:
            print(f"[GraphAPI Warning] Failed to parse links in {file_path}: {e}")

    return {"nodes": nodes, "links": links}
