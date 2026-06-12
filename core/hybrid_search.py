import os
import json
from typing import List, Dict, Tuple
from core.bm25 import global_bm25_indexer
from core import db
from core.tools import get_embedding, cosine_similarity

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

    # Rank is 1-indexed
    for rank, doc in enumerate(bm25_results, start=1):
        rrf_scores[doc] = rrf_scores.get(doc, 0.0) + (1.0 / (k + rank))

    for rank, doc in enumerate(vector_results, start=1):
        rrf_scores[doc] = rrf_scores.get(doc, 0.0) + (1.0 / (k + rank))

    # Sort descending
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs

async def hybrid_search(
    query: str,
    vault_path: str,
    api_key: str = None,
    limit: int = 5
) -> List[str]:
    """
    Performs hybrid search across Obsidian vault files:
    1. BM25 full-text search.
    2. Vector semantic search (with SQLite caching).
    3. Fuses rankings using RRF.
    """
    print(f"[HybridSearch] Query: '{query}' in vault: {vault_path}")

    # 1. BM25 Search
    bm25_scored = global_bm25_indexer.search(query, limit=limit * 3)
    bm25_paths = [path for path, score in bm25_scored]

    # If api_key is missing, fallback to BM25 directly
    if not api_key:
        print("[HybridSearch] No API key provided, fallback to BM25 search.")
        return bm25_paths[:limit]

    # 2. Vector Search
    vector_paths = []
    try:
        query_vector = await get_embedding(query, api_key)
        
        abs_vault_path = os.path.abspath(vault_path)
        scored_docs: List[Tuple[str, float]] = []

        # Walk through vault to gather notes
        for root, _, files in os.walk(abs_vault_path):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    # Ignore service files and dot folders
                    if any(part.startswith('.') for part in file_path.replace(abs_vault_path, '').split(os.sep)):
                        continue

                    try:
                        mtime = os.path.getmtime(file_path)
                        cached = db.get_note_embedding(file_path)

                        # Check if embedding cache is valid
                        if cached and abs(cached["last_modified"] - mtime) < 1.0:
                            note_vector = cached["embedding"]
                        else:
                            # Re-generate embedding (use first 1000 characters)
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(1000).strip()
                            
                            if not content:
                                continue
                            
                            note_vector = await get_embedding(content, api_key)
                            db.save_note_embedding(file_path, json.dumps(note_vector), mtime)

                        similarity = cosine_similarity(query_vector, note_vector)
                        scored_docs.append((file_path, similarity))

                    except Exception as e:
                        print(f"[HybridSearch Warning] Failed to compute embedding for {file_path}: {e}")

        # Sort vector results
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        # Keep only values with similarity > 0.3 for quality control
        vector_paths = [doc for doc, sim in scored_docs[:limit * 3] if sim > 0.3]

    except Exception as e:
        print(f"[HybridSearch Error] Vector search failed: {e}. Falling back to BM25.")
        return bm25_paths[:limit]

    # 3. Reciprocal Rank Fusion
    fused_results = reciprocal_rank_fusion(bm25_paths, vector_paths)
    final_paths = [doc for doc, score in fused_results[:limit]]
    
    print(f"[HybridSearch] Fused top results: {[os.path.basename(p) for p in final_paths]}")
    return final_paths
