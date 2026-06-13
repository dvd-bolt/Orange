import os
from typing import List
from core.markdown_ops import search_notes_cli

async def hybrid_search(
    query: str,
    vault_path: str,
    api_key: str = None,
    limit: int = 5
) -> List[str]:
    """
    Performs search across Obsidian vault files using Obsidian CLI.
    Returns relative paths (relative to the vault root).
    """
    print(f"[HybridSearch] Query: '{query}' in vault: {vault_path}")
    try:
        paths = await search_notes_cli(query)
        # Filter and limit results
        return paths[:limit]
    except Exception as e:
        print(f"[HybridSearch Error] CLI search failed: {e}")
        return []

