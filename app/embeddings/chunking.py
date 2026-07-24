"""Word-based chunking with overlap for knowledge-base documents."""
from __future__ import annotations

from typing import List


def chunk_text(text: str, max_words: int = 400, overlap_words: int = 50) -> List[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()]

    chunks = []
    start = 0
    step = max(max_words - overlap_words, 1)
    while start < len(words):
        chunk_words = words[start : start + max_words]
        chunks.append(" ".join(chunk_words).strip())
        if start + max_words >= len(words):
            break
        start += step
    return chunks
