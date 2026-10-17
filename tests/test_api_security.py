from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def test_cors_allows_public_dashboard_origin_for_local_api():
    response = client.options(
        "/api/v1/project",
        headers={
            "Origin": "https://khandetube.github.io",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://khandetube.github.io"
    assert "x-api-key" in response.headers.get("access-control-allow-headers", "").lower()


def test_cors_does_not_allow_arbitrary_origins():
    response = client.options(
        "/api/v1/project",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_configured_api_key_is_required_for_api_v1(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_API_KEY", "test-only-secret")
    missing = client.get("/api/v1/project")
    assert missing.status_code == 401
    allowed = client.get("/api/v1/project", headers={"X-API-Key": "test-only-secret"})
    assert allowed.status_code == 200
    health = client.get("/health")
    assert health.status_code == 200
