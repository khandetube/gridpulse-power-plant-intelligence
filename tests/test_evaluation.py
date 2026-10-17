import json
import sys

from gridpulse.evaluation import evaluate_retrieval, main


def sample_cases():
    return [
        {
            "query": "vibration inspection limits",
            "documents": [
                {"title": "Maintenance", "source_id": "DOC-1", "text": "Vibration inspection limits are defined by approved equipment procedures."},
                {"title": "Fuel", "source_id": "DOC-2", "text": "Fuel input and net output are used for thermal efficiency."},
            ],
            "relevant_source_ids": ["DOC-1"],
        },
        {
            "query": "unmatched turbine metallurgy topic",
            "documents": [
                {"title": "Fuel", "source_id": "DOC-2", "text": "Fuel input and net output are used for thermal efficiency."},
            ],
            "relevant_source_ids": [],
        },
    ]


def test_retrieval_evaluation_scores_relevant_sources_and_abstention():
    report = evaluate_retrieval(sample_cases(), k=3)
    assert report["network_access"] is False
    assert report["case_count"] == 2
    assert report["recall_at_k"] == 1.0
    assert report["correct_abstentions"] == 1
    assert report["false_positive_abstentions"] == 0


def test_retrieval_evaluation_rejects_invalid_k_and_empty_cases():
    for cases, k in [([], 5), (sample_cases(), 0)]:
        try:
            evaluate_retrieval(cases, k)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid evaluation input should be rejected")


def test_evaluation_cli_writes_json_report(tmp_path, monkeypatch):
    source = tmp_path / "benchmark.json"
    output = tmp_path / "report.json"
    source.write_text(json.dumps({"cases": sample_cases()}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["gridpulse-evaluate", str(source), "--output", str(output)])
    assert main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["case_count"] == 2
