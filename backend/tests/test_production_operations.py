import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.url import normalize_database_url
from app.main import app
from app.models import SearchRun
from app.services.search_runs import create_search_run, execute_search_run
from conftest import security_headers


def test_database_url_uses_installed_psycopg_driver():
    database_url = "postgresql://owner:secret@example.neon.tech/neondb?sslmode=require"
    assert normalize_database_url(database_url).startswith("postgresql+psycopg://")


def test_database_url_preserves_explicit_driver_and_sqlite():
    psycopg_url = "postgresql+psycopg://owner:secret@example.neon.tech/neondb"
    sqlite_url = "sqlite:///internship_radar.db"
    assert normalize_database_url(psycopg_url) == psycopg_url
    assert normalize_database_url(sqlite_url) == sqlite_url


def test_health_checks_database_and_tectonic(monkeypatch):
    monkeypatch.setattr("app.main.shutil.which", lambda _: "/usr/local/bin/tectonic")

    class Result:
        returncode = 0

    monkeypatch.setattr("app.main.subprocess.run", lambda *args, **kwargs: Result())
    with TestClient(app, headers=security_headers()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
    assert response.json()["latex_compiler"] == "available"
    assert "last_successful_search" in response.json()


def test_only_one_search_can_be_created_at_a_time():
    with SessionLocal() as db:
        db.query(SearchRun).delete()
        db.commit()
        first = create_search_run(db, search_type="general")
        second = create_search_run(db, search_type="general")
        assert first is not None
        assert second is None
        first.status = "completed"
        first.completed_at = datetime.now(timezone.utc)
        db.commit()


def test_managed_execution_records_results(monkeypatch):
    async def fake_refresh(db, source_types=None, source_ids=None):
        return {
            "sources_checked": 3,
            "jobs_fetched": 7,
            "jobs_created": 2,
            "jobs_updated": 4,
            "errors": [],
        }

    monkeypatch.setattr("app.services.search_runs.refresh_all_sources", fake_refresh)
    monkeypatch.setattr("app.services.search_runs.expire_past_deadline_jobs", lambda db: 1)
    with SessionLocal() as db:
        db.query(SearchRun).delete()
        db.commit()
        run = create_search_run(db, search_type="general", trigger="test")
        run_id = run.id
    asyncio.run(execute_search_run(run_id))
    with SessionLocal() as db:
        stored = db.get(SearchRun, run_id)
        assert stored.status == "completed"
        assert stored.progress_status == "Completed"
        assert stored.sources_checked == 3
        assert stored.jobs_added == 2
        assert stored.jobs_expired == 1


def test_high_priority_search_still_uses_every_enabled_source(monkeypatch):
    captured = {}

    async def fake_refresh(db, source_types=None, source_ids=None):
        captured["source_types"] = source_types
        captured["source_ids"] = source_ids
        return {
            "sources_checked": 5,
            "jobs_fetched": 0,
            "jobs_created": 0,
            "jobs_updated": 0,
            "errors": [],
        }

    monkeypatch.setattr("app.services.search_runs.refresh_all_sources", fake_refresh)
    monkeypatch.setattr("app.services.search_runs.expire_past_deadline_jobs", lambda db: 0)
    with SessionLocal() as db:
        db.query(SearchRun).delete()
        db.commit()
        run = create_search_run(db, search_type="high_priority", trigger="test")
        run_id = run.id
    asyncio.run(execute_search_run(run_id))
    assert captured == {"source_types": None, "source_ids": None}


def test_stats_uses_last_completed_search_run():
    completed_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.query(SearchRun).delete()
        db.add(
            SearchRun(
                search_type="general",
                status="completed",
                progress_status="Completed",
                completed_at=completed_at,
            )
        )
        db.commit()
    with TestClient(app, headers=security_headers()) as client:
        response = client.get("/api/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["last_update"] is not None
    assert payload["latest_search_status"] == "completed"
