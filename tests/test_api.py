from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings

def test_health_is_public():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_validation_requires_secret(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ENGINE_SHARED_SECRET", "test-secret")
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post("/render/validate", json={"format": {"aspect": "16:9"}, "scenes": []})
    assert response.status_code == 401
    response = client.post("/render/validate", headers={"X-Engine-Secret": "test-secret"}, json={"format": {"aspect": "16:9"}, "scenes": []})
    assert response.status_code == 200
    get_settings.cache_clear()


def test_media_probe_requires_engine_secret(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ENGINE_SHARED_SECRET", "probe-secret")
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post("/media/probe", json={"project_id":"p1","media_id":"m1","user_id":"u1"})
    assert response.status_code == 401
    response = client.post("/media/probe", headers={"X-Engine-Secret":"probe-secret"},
                           json={"project_id":"p1","media_id":"m1","user_id":"u1"})
    assert response.status_code == 503
    get_settings.cache_clear()
