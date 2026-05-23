from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Chunk:
    doc_id: str
    title: str
    text: str
    chunk_index: int


@dataclass
class RetrievalResult:
    doc_id: str
    title: str
    passage: str
    score: float


class KnowledgeBaseIndex:
    def __init__(self, kb_dir: Path, chunk_size: int = 400, chunk_overlap: int = 80):
        self.kb_dir = kb_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunks: list[Chunk] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None

    def _split_text(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text.strip())
        if len(text) <= self.chunk_size:
            return [text]
        parts: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            parts.append(text[start:end])
            if end >= len(text):
                break
            start = end - self.chunk_overlap
        return parts

    def load(self) -> None:
        self.chunks.clear()
        for path in sorted(self.kb_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            title_match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else path.stem
            doc_id = path.stem
            for i, piece in enumerate(self._split_text(raw)):
                self.chunks.append(Chunk(doc_id=doc_id, title=title, text=piece, chunk_index=i))

        corpus = [c.text for c in self.chunks]
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self._vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.08) -> list[RetrievalResult]:
        if not self.chunks or self._vectorizer is None or self._matrix is None:
            return []
        q_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self._matrix).flatten()
        ranked = np.argsort(scores)[::-1]
        results: list[RetrievalResult] = []
        for idx in ranked[: top_k * 2]:
            score = float(scores[idx])
            if score < min_score:
                continue
            ch = self.chunks[int(idx)]
            results.append(
                RetrievalResult(
                    doc_id=ch.doc_id,
                    title=ch.title,
                    passage=ch.text,
                    score=score,
                )
            )
            if len(results) >= top_k:
                break
        return results
