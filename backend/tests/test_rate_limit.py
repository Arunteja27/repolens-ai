from fastapi.testclient import TestClient
from repolens.core.config import Settings
from repolens.main import create_app


def _settings(tmp_path):
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / ".data",
        temp_repo_dir=tmp_path / ".data" / "repos",
        chroma_dir=tmp_path / ".data" / "chroma",
        database_path=tmp_path / ".data" / "repolens.db",
        rate_limit_enabled=True,
        rate_limit_query_requests=2,
        rate_limit_query_window_seconds=3600,
    )
    settings.ensure_directories()
    return settings


def test_rate_limiter_rejects_repeated_query_requests(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    app = create_app()

    payload = {
        "repo_id": "missing-repo",
        "question": "Where is the entrypoint?",
        "retrieval_mode": "hybrid",
        "top_k": 3,
    }

    with TestClient(app) as client:
        headers = {"X-Forwarded-For": "203.0.113.10"}
        first = client.post("/api/query", json=payload, headers=headers)
        second = client.post("/api/query", json=payload, headers=headers)
        third = client.post("/api/query", json=payload, headers=headers)

    assert first.status_code == 404
    assert second.status_code == 404
    assert third.status_code == 429
    assert third.headers["X-RateLimit-Policy"] == "query"
    assert third.headers["X-RateLimit-Remaining"] == "0"
    assert int(third.headers["Retry-After"]) >= 1
    assert third.json()["policy"] == "query"
    assert "Rate limit exceeded for query requests." in third.json()["detail"]


def test_rate_limiter_uses_forwarded_ip_as_client_key(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.rate_limit_query_requests = 1
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    app = create_app()

    payload = {
        "repo_id": "missing-repo",
        "question": "Where is the entrypoint?",
        "retrieval_mode": "hybrid",
        "top_k": 3,
    }

    with TestClient(app) as client:
        headers = {"X-Forwarded-For": "198.51.100.4"}
        first = client.post("/api/query", json=payload, headers=headers)
        limited = client.post("/api/query", json=payload, headers=headers)
        other_client = client.post(
            "/api/query",
            json=payload,
            headers={"X-Forwarded-For": "198.51.100.5"},
        )

    assert first.status_code == 404
    assert limited.status_code == 429
    assert other_client.status_code == 404


def test_rate_limited_response_keeps_cors_headers(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.rate_limit_query_requests = 1
    settings.cors_allowed_origins = ["https://demo.example"]
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    app = create_app()

    payload = {
        "repo_id": "missing-repo",
        "question": "Where is the entrypoint?",
        "retrieval_mode": "hybrid",
        "top_k": 3,
    }

    with TestClient(app) as client:
        headers = {
            "X-Forwarded-For": "198.51.100.4",
            "Origin": "https://demo.example",
        }
        client.post("/api/query", json=payload, headers=headers)
        limited = client.post("/api/query", json=payload, headers=headers)

    assert limited.status_code == 429
    assert limited.headers["Access-Control-Allow-Origin"] == "https://demo.example"
