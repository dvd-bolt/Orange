import os
from typing import List, Dict, Tuple
from core.markdown_ops import search_notes_cli

def reciprocal_rank_fusion(
    bm25_results: List[str],
    vector_results: List[str],
    k: int = 60
) -> List[Tuple[str, float]]:
    """
    Combines two ranked lists of document paths using Reciprocal Rank Fusion (RRF).
    RRF Score(d) = sum( 1 / (k + rank(d, system)) )
    """
    rrf_scores: Dict[str, float] = {}

    for rank, doc in enumerate(bm25_results, start=1):
        rrf_scores[doc] = rrf_scores.get(doc, 0.0) + (1.0 / (k + rank))

    for rank, doc in enumerate(vector_results, start=1):
        rrf_scores[doc] = rrf_scores.get(doc, 0.0) + (1.0 / (k + rank))

    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs

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

