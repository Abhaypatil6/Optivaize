"""
RAG (Retrieval-Augmented Generation) component.

Chunks the knowledge-base Markdown articles, indexes them using a pure-Python
TF-IDF & Cosine Similarity retriever, and exposes a retrieve(query, top_k) function.

No API keys or large ML library downloads required. Extremely lightweight and fast.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import NamedTuple

# ── Path configuration ──────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_KB_DIR = _HERE.parent / "support_resolution_pack" / "knowledge_base"

CHUNK_SIZE = 300       # characters (not tokens) — fast and good enough
CHUNK_OVERLAP = 60


class Chunk(NamedTuple):
    text: str
    source: str        # e.g. "kb-003"
    article_title: str


# ── Chunking ────────────────────────────────────────────────────────────────

def _extract_article_id(filename: str) -> str:
    """kb-001-shipping-times.md → kb-001"""
    return "-".join(filename.split("-")[:2])


def _extract_title(content: str) -> str:
    """Return the first H1 heading, or the filename stem."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Unknown"


def _chunk_text(text: str, source: str, title: str) -> list[Chunk]:
    """Return the entire text as a single chunk to maximize search precision."""
    return [Chunk(text=text.strip(), source=source, article_title=title)]


def _load_all_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    if not _KB_DIR.exists():
        return chunks
    for md_file in sorted(_KB_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        source = _extract_article_id(md_file.name)
        title = _extract_title(content)
        chunks.extend(_chunk_text(content, source, title))
    return chunks


# ── Text Tokenization ────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Lowercase and extract alphanumeric tokens of length >= 2."""
    return re.findall(r'[a-zA-Z0-9]+', text.lower())


# ── Index build / load ───────────────────────────────────────────────────────

_chunks: list[Chunk] = []
_doc_freqs: dict[str, int] = {}
_idf: dict[str, float] = {}


def _ensure_index() -> None:
    """Lazily load chunks and build the TF-IDF vocabulary index."""
    global _chunks, _doc_freqs, _idf
    if _chunks:
        return

    _chunks = _load_all_chunks()
    if not _chunks:
        return

    # Calculate document frequencies
    _doc_freqs = {}
    for chunk in _chunks:
        unique_tokens = set(tokenize(chunk.text))
        for token in unique_tokens:
            _doc_freqs[token] = _doc_freqs.get(token, 0) + 1

    # Calculate Inverse Document Frequency (IDF) using standard formulation
    N = len(_chunks)
    _idf = {}
    for token, df in _doc_freqs.items():
        # Using a smooth math.log to prevent division/log of 0, plus 1 to keep it positive
        _idf[token] = math.log(1.0 + (N / (1.0 + df)))


# ── Public API ───────────────────────────────────────────────────────────────

class SearchResult(NamedTuple):
    text: str
    source: str           # article ID, e.g. "kb-003"
    article_title: str
    score: float          # cosine similarity [0,1]


def retrieve(query: str, top_k: int = 3) -> list[SearchResult]:
    """
    Find and return the top_k most relevant KB chunks using TF-IDF & Cosine Similarity.
    Returns an empty list if the KB is empty or indexing/search fails.
    """
    try:
        _ensure_index()
    except Exception:
        return []

    if not _chunks:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # 1. Compute Query TF vector
    query_tf: dict[str, int] = {}
    for token in query_tokens:
        query_tf[token] = query_tf.get(token, 0) + 1

    # 2. Compute Query TF-IDF values and query vector norm
    query_vec: dict[str, float] = {}
    query_norm_sq = 0.0
    for token, tf in query_tf.items():
        idf = _idf.get(token, 0.0)
        val = tf * idf
        query_vec[token] = val
        query_norm_sq += val * val

    if query_norm_sq == 0.0:
        # None of the query terms appear anywhere in the corpus
        return []
    query_norm = math.sqrt(query_norm_sq)

    # 3. Calculate similarity score for each chunk
    results: list[SearchResult] = []
    for chunk in _chunks:
        chunk_tokens = tokenize(chunk.text)
        if not chunk_tokens:
            continue

        # Compute Chunk TF vector
        chunk_tf: dict[str, int] = {}
        for token in chunk_tokens:
            chunk_tf[token] = chunk_tf.get(token, 0) + 1

        # Compute dot product and chunk vector norm
        dot_product = 0.0
        chunk_norm_sq = 0.0

        for token, tf in chunk_tf.items():
            idf = _idf.get(token, 0.0)
            val = tf * idf
            chunk_norm_sq += val * val

            # Accumulate dot product if the token is also in the query
            if token in query_vec:
                dot_product += val * query_vec[token]

        if chunk_norm_sq == 0.0:
            continue

        chunk_norm = math.sqrt(chunk_norm_sq)
        score = dot_product / (query_norm * chunk_norm)

        results.append(SearchResult(
            text=chunk.text,
            source=chunk.source,
            article_title=chunk.article_title,
            score=score,
        ))

    # 4. Sort results descending by score and return top_k
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_k]
