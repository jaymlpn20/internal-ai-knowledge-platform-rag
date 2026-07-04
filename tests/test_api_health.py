"""Smoke tests for the FastAPI app wiring (no external services required)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_metadata():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Internal AI Knowledge Platform"


def test_openapi_exposes_core_routes():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/documents" in paths
    assert "/query" in paths
    assert "/gateway/chat" in paths
