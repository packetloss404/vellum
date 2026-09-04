from __future__ import annotations


def test_health_and_readiness_are_public_and_healthy(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"ok": True}
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "ready": True}


def test_readiness_fails_closed_without_leaking_database_error(
    fresh_db, monkeypatch
):
    from fastapi.testclient import TestClient
    from vellum import db
    from vellum.main import create_app

    app = create_app()

    def unavailable():
        raise RuntimeError("secret database path")

    monkeypatch.setattr(db, "connect", unavailable)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"ok": False, "ready": False}
    assert "secret database path" not in response.text
