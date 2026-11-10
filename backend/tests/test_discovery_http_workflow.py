"""HTTP-to-worker integration with fixture ATS data, never external requests."""
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import AuthorizedAccount, CompanySource, Job, UserProfile
from app.services import unified_discovery
from app.sources.lever import LeverAdapter
from conftest import security_headers


def test_private_search_worker_results_save_and_health_are_connected(monkeypatch):
    from app.jobs import refresh
    owner = settings.effective_primary_user_id
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(AuthorizedAccount(user_id=owner, email="candidate@example.com", provider="google", is_active=True))
        db.add(UserProfile(owner_user_id=owner, full_name="Alex Rivera", degree="Robotics and Digital Systems Engineering", university="Example Institute of Technology", graduation_year=2028, nationality="Mexican", gpa=3.7, gpa_scale=4, preferred_roles=["Robotics"], countries_to_search=["United States", "Canada"]))
        db.add(CompanySource(owner_user_id=owner, company="Fixture Robotics", source_type="lever", source_identifier="fixture", source_url="https://jobs.lever.co/fixture", enabled=True, registry_type="OFFICIAL_ATS", reference_only=False))
        foreign = Job(owner_user_id="other-owner", title="Private Robotics Internship", company="Other", source_name="Manual", source_url="https://example.edu/private", apply_url="https://example.edu/private", raw_data_hash="private")
        db.add(foreign); db.commit(); foreign_id = foreign.id
    def database():
        with factory() as db:
            db.info["owner_user_id"] = owner
            yield db
    normalized = LeverAdapter("Fixture Robotics", "fixture", "https://jobs.lever.co/fixture").normalize_job({"id": "123", "text": "Robotics Intern", "hostedUrl": "https://jobs.lever.co/fixture/123", "applyUrl": "https://jobs.lever.co/fixture/123/apply", "descriptionPlain": "Undergraduate robotics internship with Python.", "categories": {"location": "Seattle, United States"}})
    class Fixture:
        complete_snapshot = True
        all_external_ids = {"123"}
        async def collect(self): return [normalized]
    monkeypatch.setattr(refresh, "create_adapter", lambda *a, **k: Fixture())
    monkeypatch.setattr(unified_discovery, "SessionLocal", factory)
    monkeypatch.setattr("app.main.SessionLocal", factory)
    monkeypatch.setattr(settings, "freehire_enabled", False)
    monkeypatch.setattr(settings, "opportunity_search_provider", "disabled")
    app.dependency_overrides[get_db] = database
    try:
        client = TestClient(app, headers=security_headers())
        response = client.post("/api/discovery/search", json={"mode": "quick", "query": "robotics", "countries": ["United States", "Canada"]})
        assert response.status_code == 202, response.text
        result = client.get(f"/api/discovery/runs/{response.json()['runId']}")
        assert result.status_code == 200 and result.json()["status"] == "completed", result.text
        results = result.json()["results"]
        assert len(results) == 1 and results[0]["company"] == "Fixture Robotics"
        assert results[0]["verificationStatus"] == "verified"
        assert results[0]["fitScore"] is not None and results[0]["eligibilityScore"] is not None
        assert client.post(f"/api/discovery/{results[0]['id']}/save").status_code == 200
        assert client.post(f"/api/discovery/{foreign_id}/save").status_code == 404
        assert client.get("/api/discovery/health").json()["sources"][0]["health"] == "HEALTHY"
        assert len(client.get("/api/discovery/runs").json()) == 1
        assert client.post("/api/discovery/boards", json={"company": "Unsafe", "ats": "ashby", "board_id": "unsafe", "source_url": "https://other.example/unsafe"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
