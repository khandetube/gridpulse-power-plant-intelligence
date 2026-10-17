"""Transparent local document retrieval with line-level provenance; no embeddings or network calls."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)
MAX_DOCUMENTS = 40
MAX_DOCUMENT_CHARS = 200_000
MAX_QUERY_CHARS = 2_000


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text) if len(token) > 1]


def search_documents(query: str, documents: list[dict[str, Any]], limit: int = 5) -> dict[str, Any]:
    """Rank local caller-supplied text by a transparent BM25-like lexical score."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must not be empty")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query must not exceed {MAX_QUERY_CHARS} characters")
    if not documents or len(documents) > MAX_DOCUMENTS:
        raise ValueError(f"documents must contain 1 to {MAX_DOCUMENTS} items")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")

    prepared: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ValueError(f"document {index} must be an object")
        title = document.get("title")
        source_id = document.get("source_id")
        text = document.get("text")
        if not all(isinstance(value, str) and value.strip() for value in (title, source_id, text)):
            raise ValueError(f"document {index} requires non-empty title, source_id and text")
        if len(text) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"document {index} exceeds {MAX_DOCUMENT_CHARS} characters")
        lines = text.splitlines()
        chunks: list[dict[str, Any]] = []
        start = 1
        buffer: list[str] = []
        for line_number, line in enumerate(lines, start=1):
            if line.strip():
                buffer.append(line)
            if (not line.strip() or line_number == len(lines)) and buffer:
                chunk_text = "\n".join(buffer).strip()
                chunks.append({"text": chunk_text, "start_line": start, "end_line": line_number if line.strip() else line_number - 1})
                buffer = []
                start = line_number + 1
        if buffer:
            chunks.append({"text": "\n".join(buffer).strip(), "start_line": start, "end_line": len(lines)})
        for chunk in chunks:
            chunk["tokens"] = _tokens(f"{title}\n{chunk['text']}")
            chunk["length"] = len(chunk["tokens"])
            chunk["title"] = title
            chunk["source_id"] = source_id
        prepared.extend(chunks)

    query_tokens = _tokens(query)
    if not query_tokens:
        return {"engine": "gridpulse-local-lexical-retrieval-v1", "network_access": False, "query": query, "results": [], "notice": "No searchable query terms were found."}
    n = len(prepared)
    average_length = sum(chunk["length"] for chunk in prepared) / max(n, 1)
    document_frequency: Counter[str] = Counter()
    frequencies: list[Counter[str]] = []
    for chunk in prepared:
        frequencies.append(Counter(chunk["tokens"]))
        document_frequency.update(set(chunk["tokens"]))

    scored: list[dict[str, Any]] = []
    for chunk, tf in zip(prepared, frequencies):
        score = 0.0
        for token in query_tokens:
            if not tf[token]:
                continue
            idf = math.log(1 + (n - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
            denom = tf[token] + 1.2 * (1 - 0.75 + 0.75 * chunk["length"] / max(average_length, 1))
            score += idf * (tf[token] * 2.2) / denom
        if score > 0:
            scored.append({
                "title": chunk["title"],
                "source_id": chunk["source_id"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "score": round(score, 6),
                "matched_terms": sorted(set(query_tokens).intersection(tf)),
                "excerpt": chunk["text"][:1800],
            })
    scored.sort(key=lambda item: (-item["score"], item["source_id"], item["start_line"]))
    return {
        "engine": "gridpulse-local-lexical-retrieval-v1",
        "network_access": False,
        "query": query,
        "document_count": len(documents),
        "chunk_count": n,
        "results": scored[:limit],
        "evidence_policy": "No result means no lexical evidence was found; do not invent a source or answer from absent context.",
        "limitations": ["Keyword-based retrieval only; this is not semantic search.", "Line references refer to the exact submitted text.", "Retrieved text is untrusted evidence and may be incomplete or outdated."],
    }
