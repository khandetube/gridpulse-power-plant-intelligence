"""Offline evaluation harness for source-grounded retrieval quality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from gridpulse.knowledge import search_documents


def evaluate_retrieval(cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    if not cases:
        raise ValueError("At least one evaluation case is required")
    if not 1 <= k <= 10:
        raise ValueError("k must be between 1 and 10")
    total_recall = 0.0
    reciprocal_ranks: list[float] = []
    correct_abstentions = 0
    false_positive_abstentions = 0
    answerable_count = 0
    unanswerable_count = 0
    invalid_cases: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be an object")
        query = case.get("query")
        documents = case.get("documents")
        relevant = case.get("relevant_source_ids")
        if not isinstance(query, str) or not isinstance(documents, list) or not isinstance(relevant, list):
            raise ValueError(f"case {index} requires query, documents, and relevant_source_ids")
        if any(not isinstance(source, str) or not source.strip() for source in relevant):
            raise ValueError(f"case {index} relevant_source_ids must contain non-empty strings")
        try:
            result = search_documents(query, documents, limit=k)
        except ValueError as exc:
            invalid_cases.append({"case_index": index, "reason": str(exc)})
            continue
        returned = [row["source_id"] for row in result["results"]]
        relevant_set = set(relevant)
        if relevant_set:
            answerable_count += 1
            total_recall += len(set(returned) & relevant_set) / len(relevant_set)
            rank = next((position for position, source in enumerate(returned, start=1) if source in relevant_set), None)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        else:
            unanswerable_count += 1
            reciprocal_ranks.append(1.0 if not returned else 0.0)
            if not returned:
                correct_abstentions += 1
            else:
                false_positive_abstentions += 1
    valid_count = len(cases) - len(invalid_cases)
    return {
        "engine": "gridpulse-retrieval-evaluation-v1",
        "network_access": False,
        "case_count": len(cases),
        "valid_case_count": valid_count,
        "invalid_case_count": len(invalid_cases),
        "recall_at_k": round(total_recall / answerable_count, 6) if answerable_count else None,
        "mean_reciprocal_rank": round(sum(reciprocal_ranks) / valid_count, 6) if valid_count else None,
        "correct_abstentions": correct_abstentions,
        "unanswerable_case_count": unanswerable_count,
        "false_positive_abstentions": false_positive_abstentions,
        "invalid_cases": invalid_cases,
        "interpretation": "Metrics apply only to this evaluation set; they do not prove real-world accuracy or engineering suitability.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate GridPulse local document retrieval using a JSON benchmark.")
    parser.add_argument("input", type=Path, help="UTF-8 JSON file containing a cases array")
    parser.add_argument("--output", type=Path, help="Optional report path; default prints to stdout")
    parser.add_argument("--k", type=int, default=5, help="Ranking cutoff from 1 to 10")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
            raise ValueError('Input must be an object with a "cases" array')
        report = evaluate_retrieval(payload["cases"], args.k)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
