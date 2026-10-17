from fastapi.testclient import TestClient

from gridpulse.knowledge import search_documents
from gridpulse.main import app


def docs():
    return [
        {
            "title": "Maintenance Standard",
            "source_id": "DOC-MAINT-01",
            "text": "Section 1: Scope\nThis document describes inspection requirements.\n\nSection 2: Vibration\nVibration readings must be compared with approved equipment-specific limits.\nRecord date, unit, and instrument calibration.",
        },
        {
            "title": "Fuel Performance Guide",
            "source_id": "DOC-FUEL-02",
            "text": "Thermal efficiency is calculated from net electrical output and fuel thermal input.\nAlways retain measurement units and the reporting period.",
        },
    ]


def test_local_retrieval_returns_source_and_line_provenance():
    result = search_documents("vibration equipment-specific limits", docs())
    assert result["network_access"] is False
    assert result["results"]
    top = result["results"][0]
    assert top["source_id"] == "DOC-MAINT-01"
    assert top["start_line"] == 4
    assert top["end_line"] == 6
    assert "vibration" in top["matched_terms"]


def test_local_retrieval_abstains_when_no_terms_match():
    result = search_documents("turbine blade metallography", docs())
    assert result["results"] == []
    assert "do not invent" in result["evidence_policy"]


def test_local_retrieval_rejects_empty_or_oversized_inputs():
    try:
        search_documents("  ", docs())
    except ValueError as exc:
        assert "not be empty" in str(exc)
    else:
        raise AssertionError("Empty query must be rejected")
    try:
        search_documents("vibration", [{"title": "x", "source_id": "s", "text": "x" * 200001}])
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:
        raise AssertionError("Oversized document must be rejected")


def test_knowledge_search_api_returns_citations():
    client = TestClient(app)
    response = client.post(
        "/api/v1/ai/knowledge/search",
        json={"query": "vibration limits", "documents": docs(), "limit": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["network_access"] is False
    assert body["results"][0]["source_id"] == "DOC-MAINT-01"
