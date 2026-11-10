import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app


@pytest.mark.parametrize("path", ["/api/discovery/search", "/api/discovery/import", "/api/opportunities/bootstrap", "/api/opportunities"])
def test_public_demo_never_runs_discovery_or_writes_candidate_data(monkeypatch, path):
    monkeypatch.setattr(settings, "public_demo_mode", True)
    response = TestClient(app).post(path, json={})
    assert response.status_code == 403
    assert response.json()["detail"] == "Read-only public demo."
