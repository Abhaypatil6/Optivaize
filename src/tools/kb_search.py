from __future__ import annotations

from src.config import KB_DIR
from src.rag.indexer import KnowledgeBaseIndex, RetrievalResult

_index: KnowledgeBaseIndex | None = None


def _get_index() -> KnowledgeBaseIndex:
    global _index
    if _index is None:
        _index = KnowledgeBaseIndex(KB_DIR)
        _index.load()
    return _index


def kb_search(query: str, top_k: int = 3) -> dict:
    try:
        hits: list[RetrievalResult] = _get_index().search(query, top_k=top_k)
    except Exception as exc:
        return {"ok": False, "results": [], "error": f"kb_search_failed: {exc}"}

    if not hits:
        return {
            "ok": True,
            "results": [],
            "error": "no_relevant_passages",
        }

    return {
        "ok": True,
        "results": [
            {
                "doc_id": h.doc_id,
                "title": h.title,
                "passage": h.passage,
                "score": round(h.score, 4),
            }
            for h in hits
        ],
    }
