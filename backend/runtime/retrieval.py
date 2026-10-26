"""Tenant-filtered lexical BM25. Dense/hybrid search is not claimed by this runtime."""

import math
import re
from collections import Counter

from sqlalchemy import select

from .database import Chunk, Document

STOP = set(
    [
        "the",
        "and",
        "for",
        "are",
        "what",
        "how",
        "does",
        "with",
        "this",
        "that",
        "from",
        "your",
        "have",
        "can",
        "you",
        "about",
        "is",
        "a",
        "an",
        "of",
        "to",
        "in",
    ]
)


def tokens(text):
    return [w for w in re.findall(r"\w+", text.lower()) if w not in STOP]


async def search(db, org_id: str, query: str, doc_ids: list[str] | None = None, top_k=5):
    stmt = (
        select(Chunk, Document.name)
        .join(Document, Document.id == Chunk.doc_id)
        .where(
            Chunk.org_id == org_id,
            Document.org_id == org_id,
            Document.status == "indexed",
        )
    )
    if doc_ids:
        stmt = stmt.where(Document.id.in_(doc_ids))
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []
    counts = [Counter(tokens(chunk.content)) for chunk, _ in rows]
    lengths = [sum(c.values()) for c in counts]
    average = max(1, sum(lengths) / len(lengths))
    query_words = set(tokens(query))
    frequency = {word: sum(word in c for c in counts) for word in query_words}
    ranked = []
    for (chunk, name), count, length in zip(rows, counts, lengths):
        score = 0.0
        for word in query_words:
            tf = count[word]
            idf = math.log(1 + (len(rows) - frequency[word] + 0.5) / (frequency[word] + 0.5))
            score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / average))
        if score > 0:
            ranked.append(
                {
                    "chunk_id": chunk.id,
                    "doc_id": chunk.doc_id,
                    "name": name,
                    "page": chunk.page,
                    "position": chunk.position,
                    "excerpt": chunk.content,
                    "score": round(score, 4),
                }
            )
    return sorted(ranked, key=lambda h: h["score"], reverse=True)[:top_k]
