from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch, fresh_db, token: str = "", required: bool = False):
    from vellum import config
    from vellum.main import create_app

    monkeypatch.setattr(config, "API_TOKEN", token)
    monkeypatch.setattr(config, "API_AUTH_REQUIRED", required)
    return TestClient(create_app())


def test_empty_api_token_keeps_local_api_open(fresh_db, monkeypatch):
    with _client(monkeypatch, fresh_db) as client:
        resp = client.get("/api/dossiers")

    assert resp.status_code == 200, resp.text


def test_configured_api_token_protects_api_but_not_health(fresh_db, monkeypatch):
    with _client(monkeypatch, fresh_db, token="secret") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/dossiers").status_code == 401
        assert client.get(
            "/api/dossiers", headers={"Authorization": "Bearer secret"}
        ).status_code == 200
        assert client.get(
            "/api/dossiers", headers={"X-Vellum-Api-Token": "secret"}
        ).status_code == 200


def test_auth_required_without_token_fails_closed(fresh_db, monkeypatch):
    with _client(monkeypatch, fresh_db, required=True) as client:
        assert client.get("/health").status_code == 200
        resp = client.get("/api/dossiers")

    assert resp.status_code == 503, resp.text
