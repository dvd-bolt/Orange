import os
import re
import asyncio
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple
from core.markdown_ops import search_notes_cli
from core.path_safety import VaultPathResolver

SEARCH_TOKEN_PATTERN = re.compile(r"[A-Za-zА-Яа-я0-9_]{2,}")

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
    Searches through Obsidian CLI when available and always has a local fallback.
    Returned paths are relative to the vault root.
    """
    print("[HybridSearch] Starting bounded vault search.")
    try:
        cli_paths = await asyncio.wait_for(
            search_notes_cli(query, vault_path=vault_path),
            timeout=5.0,
        )
    except Exception as e:
        print(f"[HybridSearch Error] CLI search failed: {type(e).__name__}")
        cli_paths = []

    local_paths = local_search_vault(query, vault_path, limit=max(limit * 3, 10))
    text_paths = list(dict.fromkeys([*cli_paths, *local_paths]))
    vector_paths = []
    if api_key:
        try:
            vector_paths = await asyncio.wait_for(
                embedding_search_vault(
                    query,
                    vault_path,
                    api_key,
                    limit=max(limit * 2, 10),
                ),
                timeout=8.0,
            )
        except Exception as exc:
            print(f"[HybridSearch Warning] Embedding search unavailable: {type(exc).__name__}")

    ranked = reciprocal_rank_fusion(text_paths, vector_paths)
    return [path for path, _ in ranked[:limit]]


def local_search_vault(query: str, vault_path: str, limit: int = 20) -> List[str]:
    """Deterministic local note search used when Obsidian CLI is unavailable."""
    resolver = VaultPathResolver(vault_path)
    root = resolver.root
    if not root.is_dir():
        return []

    query_tokens = {
        token.lower()
        for token in SEARCH_TOKEN_PATTERN.findall(query)
        if len(token) >= 2
    }
    normalized_query = query.strip().lower()
    if not query_tokens and not normalized_query:
        return []

    scored: List[Tuple[float, str]] = []
    for file_path in resolver.iter_notes(exclude_generated=True):
        try:
            relative = file_path.relative_to(root)
        except ValueError:
            continue
        try:
            content = resolver.read_note_text(file_path)
        except OSError:
            continue

        title = file_path.stem.lower()
        lowered = content.lower()
        score = 0.0
        if normalized_query and normalized_query in title:
            score += 12.0
        if normalized_query and normalized_query in lowered:
            score += 6.0
        for token in query_tokens:
            if token in title:
                score += 5.0
            occurrences = lowered.count(token)
            score += min(occurrences, 8) * 0.75
        if score:
            scored.append((score, relative.as_posix()))

    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [path for _, path in scored[:limit]]


async def embedding_search_vault(
    query: str,
    vault_path: str,
    api_key: str,
    *,
    limit: int = 10,
) -> List[str]:
    """Rank vault notes by cached embeddings with a small bounded warm-up."""
    from core import db
    from core.tools import cosine_similarity, get_embedding

    resolver = VaultPathResolver(vault_path)
    root = resolver.root
    if not root.is_dir() or not query.strip():
        return []

    query_vector = await get_embedding(query[:2_000], api_key)
    records = []
    for file_path in resolver.iter_notes(exclude_generated=True):
        try:
            relative = file_path.relative_to(root)
        except ValueError:
            continue
        try:
            stat = file_path.stat()
        except OSError:
            continue
        records.append((file_path, relative.as_posix(), stat.st_mtime))

    records.sort(key=lambda item: (-item[2], item[1].lower()))
    warmup_limit = max(0, min(int(os.environ.get("ORANGE_EMBEDDING_WARMUP_LIMIT", "4")), 20))
    uncached_budget = warmup_limit
    scored = []
    pending = []

    for file_path, relative_path, modified_at in records:
        cache_key = _note_embedding_cache_key(root, relative_path)
        cached = db.get_note_embedding(cache_key)
        if cached and cached.get("last_modified") == modified_at:
            vector = cached.get("embedding")
            similarity = cosine_similarity(query_vector, vector)
            scored.append((similarity, relative_path))
            continue
        if uncached_budget <= 0:
            continue
        uncached_budget -= 1
        pending.append((file_path, relative_path, modified_at, cache_key))

    semaphore = asyncio.Semaphore(2)

    async def embed_record(record):
        file_path, relative_path, modified_at, cache_key = record
        async with semaphore:
            content = await asyncio.to_thread(
                resolver.read_note_text,
                file_path,
                max_chars=4_000,
            )
            vector = await get_embedding(
                f"Title: {file_path.stem}\n\n{content}",
                api_key,
            )
            db.save_note_embedding(cache_key, json.dumps(vector), modified_at)
            return cosine_similarity(query_vector, vector), relative_path

    if pending:
        results = await asyncio.gather(
            *(embed_record(record) for record in pending),
            return_exceptions=True,
        )
        scored.extend(result for result in results if isinstance(result, tuple))

    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [path for score, path in scored[:limit] if score > 0.18]


def _note_embedding_cache_key(
    root: Path,
    relative_path: str,
    model_name: str = "",
) -> str:
    selected_model = model_name or os.environ.get(
        "ORANGE_EMBEDDING_MODEL",
        "gemini-embedding-2",
    )
    vault_id = hashlib.sha256(
        f"{root}\0{selected_model}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{vault_id}:{relative_path}"
