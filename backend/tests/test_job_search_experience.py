import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.main import app
from app.models import Job, SearchRun, SearchRunJob
from app.schemas.api import SearchCriteria
from app.services.search_criteria import (
    discovery_search_terms,
    matches_discovery_criteria,
    matches_eligibility_criteria,
    search_result_sort_key,
    select_sources_for_criteria,
)
from app.services.search_runs import create_search_run, execute_search_run
from app.sources.official_careers import OfficialCareersAdapter
from conftest import security_headers


def criteria(**overrides):
    values = SearchCriteria().model_dump(mode="json")
    values.update(overrides)
    return values


def finish_active_searches() -> None:
    init_db()
    with SessionLocal() as db:
        for run in db.scalars(
            select(SearchRun).where(SearchRun.status.in_(("pending", "running")))
        ):
            run.status = "completed"
            run.progress_status = "Completed"
            run.completed_at = datetime.now(timezone.utc)
        db.commit()


def test_search_criteria_normalizes_and_validates_keyword_conflicts():
    payload = SearchCriteria(
        companies=[" Oracle ", "oracle", "Intel"],
        work_models=["REMOTE"],
    )
    assert payload.companies == ["Oracle", "Intel"]
    assert payload.remote_scopes == ["MEXICO", "LATAM", "GLOBAL"]
    with pytest.raises(ValidationError):
        SearchCriteria(include_keywords=["Python"], exclude_keywords=["python"])


def test_oracle_software_and_intel_guadalajara_matching():
    oracle = {
        "company": "Oracle",
        "title": "Software Engineering Intern",
        "location": "Mexico City, Mexico",
        "country": "Mexico",
        "remote_type": "Hybrid",
        "area": "Software / SDE",
    }
    matched, _ = matches_discovery_criteria(
        oracle,
        criteria(companies=["Oracle"], role_categories=["SOFTWARE_ENGINEERING"]),
    )
    assert matched
    intel = {
        **oracle,
        "company": "Intel",
        "title": "Embedded Software Intern",
        "location": "Guadalajara, Jalisco, Mexico",
        "city": "Guadalajara",
        "region": "Jalisco",
        "area": "Firmware / Embedded",
    }
    matched, _ = matches_discovery_criteria(
        intel,
        criteria(companies=["Intel"], cities=["Guadalajara"]),
    )
    assert matched


def test_research_engineering_category_matches_research_internships():
    researcher = {
        "company": "Google",
        "title": "Student Researcher, BS/MS, Winter/Summer 2027",
        "location": "Mountain View, California, United States",
        "country": "United States",
        "remote_type": "On-site",
        "area": "Research / Research Engineering",
    }
    matched, _ = matches_discovery_criteria(
        researcher,
        criteria(role_categories=["RESEARCH_ENGINEERING"]),
    )
    assert matched


def test_remote_us_only_never_matches_mexico_scope():
    remote_job = {
        "company": "Example",
        "title": "Software Intern",
        "location": "Remote - United States",
        "remote_type": "Remote",
        "remote_scope": "US_ONLY",
    }
    mexico_match, _ = matches_discovery_criteria(
        remote_job,
        criteria(work_models=["REMOTE"], remote_scopes=["MEXICO", "LATAM", "GLOBAL"]),
    )
    us_match, _ = matches_discovery_criteria(
        remote_job,
        criteria(work_models=["REMOTE"], remote_scopes=["US_ONLY"]),
    )
    assert not mexico_match
    assert us_match


def test_hard_ineligible_and_unknown_preferences_are_final_authority():
    ineligible = SimpleNamespace(
        analysis=SimpleNamespace(eligibility_status="NOT_ELIGIBLE")
    )
    unknown = SimpleNamespace(analysis=SimpleNamespace(eligibility_status="UNKNOWN"))
    assert not matches_eligibility_criteria(ineligible, criteria())
    assert matches_eligibility_criteria(unknown, criteria(include_unknown_eligibility=True))
    assert not matches_eligibility_criteria(unknown, criteria(include_unknown_eligibility=False))


def test_selected_company_prioritizes_its_official_source_and_keeps_community():
    sources = [
        SimpleNamespace(company="Oracle", registry_type="OFFICIAL_ATS", priority=100),
        SimpleNamespace(company="Intel", registry_type="OFFICIAL_COMPANY", priority=100),
        SimpleNamespace(company="Community", registry_type="COMMUNITY_REPO", priority=70),
        SimpleNamespace(company="Other board", registry_type="JOB_BOARD", priority=50),
    ]
    selected = select_sources_for_criteria(sources, criteria(companies=["Oracle"]), [])
    assert [source.company for source in selected] == ["Oracle", "Community"]


def test_remote_search_builds_scope_specific_queries_for_real_adapters():
    payload = criteria(
        work_models=["REMOTE"],
        remote_scopes=["MEXICO", "LATAM", "GLOBAL"],
        role_categories=["SOFTWARE_ENGINEERING"],
    )
    terms = discovery_search_terms(payload)
    assert "software engineering intern remote Mexico" in terms
    assert "software engineering intern remote LATAM" in terms
    assert "software engineering intern global remote" in terms
    adapter = OfficialCareersAdapter(
        "Google",
        "google",
        "https://www.google.com/about/careers/applications/jobs/results/?q=intern",
        search_criteria=payload,
    )
    urls = adapter.search_urls()
    assert any("remote+Mexico" in url for url in urls)
    assert all("q=" in url for url in urls)


def test_search_sorting_prefers_technical_match_then_freshness():
    stronger = SimpleNamespace(
        analysis=SimpleNamespace(
            eligibility_status="ELIGIBLE",
            technical_score=92,
            freshness_score=20,
        ),
        country="Mexico",
        can_work_from_mexico="YES",
        remote_from_mexico_allowed=False,
        remote_type="On-site",
        official_status="open",
        verification_status="verified",
        is_target_company=False,
    )
    fresher = SimpleNamespace(
        analysis=SimpleNamespace(
            eligibility_status="ELIGIBLE",
            technical_score=88,
            freshness_score=100,
        ),
        country="Mexico",
        can_work_from_mexico="YES",
        remote_from_mexico_allowed=False,
        remote_type="On-site",
        official_status="open",
        verification_status="verified",
        is_target_company=True,
    )
    assert search_result_sort_key(stronger) > search_result_sort_key(fresher)


def test_post_search_run_stores_canonical_criteria(monkeypatch):
    async def no_op(_: int) -> None:
        return None

    monkeypatch.setattr("app.main.execute_search_run", no_op)
    finish_active_searches()
    with TestClient(app, headers=security_headers()) as client:
        response = client.post(
            "/api/search-runs",
            json=criteria(companies=["Oracle"], role_categories=["SOFTWARE_ENGINEERING"]),
        )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["criteria_json"]["companies"] == ["Oracle"]
    with SessionLocal() as db:
        run = db.get(SearchRun, payload["id"])
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def test_sources_scan_starts_general_discovery_run(monkeypatch):
    async def no_op(_: int) -> None:
        return None

    monkeypatch.setattr("app.main.execute_search_run", no_op)
    finish_active_searches()
    with TestClient(app, headers=security_headers()) as client:
        response = client.post("/api/jobs/search")
    assert response.status_code == 202
    payload = response.json()
    assert payload["search_type"] == "general"
    assert payload["status"] == "pending"
    with SessionLocal() as db:
        run = db.get(SearchRun, payload["id"])
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def test_run_again_creates_a_new_run_and_history_delete_is_soft(monkeypatch):
    async def no_op(_: int) -> None:
        return None

    monkeypatch.setattr("app.main.execute_search_run", no_op)
    finish_active_searches()
    payload = criteria(companies=["Oracle"])
    with TestClient(app, headers=security_headers()) as client:
        first = client.post("/api/search-runs", json=payload)
        assert first.status_code == 202
        first_id = first.json()["id"]
        with SessionLocal() as db:
            run = db.get(SearchRun, first_id)
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

        second = client.post("/api/search-runs", json=payload)
        assert second.status_code == 202
        second_id = second.json()["id"]
        assert second_id != first_id
        with SessionLocal() as db:
            run = db.get(SearchRun, second_id)
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

        removed = client.delete(f"/api/search-runs/{first_id}")
        assert removed.status_code == 200
        assert removed.json() == {"id": first_id, "deleted_from_history": True}
        history_ids = {item["id"] for item in client.get("/api/search-runs").json()}
        assert first_id not in history_ids
        assert second_id in history_ids
        with SessionLocal() as db:
            assert db.get(SearchRun, first_id) is not None


def test_search_history_and_latest_status_are_scoped_to_current_user():
    init_db()
    now = datetime.now(timezone.utc) + timedelta(days=1)
    with SessionLocal() as db:
        own = SearchRun(
            owner_user_id="internship-radar-primary",
            search_type="custom",
            status="completed",
            started_at=now,
            created_at=now,
        )
        other = SearchRun(
            owner_user_id="another-candidate",
            search_type="custom",
            status="running",
            started_at=now + timedelta(seconds=1),
            created_at=now + timedelta(seconds=1),
        )
        db.add_all([own, other])
        db.commit()
        own_id, other_id = own.id, other.id

    try:
        with TestClient(app, headers=security_headers()) as client:
            history = client.get("/api/search-runs")
            stats = client.get("/api/stats")
            latest = client.get("/api/search-runs/latest")
        assert history.status_code == 200
        assert own_id in {run["id"] for run in history.json()}
        assert other_id not in {run["id"] for run in history.json()}
        assert stats.status_code == 200
        assert stats.json()["latest_search_id"] == own_id
        assert stats.json()["latest_search_status"] == "completed"
        assert latest.status_code == 200
        assert latest.json()["id"] == own_id
    finally:
        with SessionLocal() as db:
            db.query(SearchRun).filter(SearchRun.id.in_([own_id, other_id])).delete(
                synchronize_session=False
            )
            db.commit()


def test_abandoned_search_no_longer_looks_running_when_dashboard_returns():
    init_db()
    with SessionLocal() as db:
        abandoned = SearchRun(
            owner_user_id="internship-radar-primary",
            search_type="custom",
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=31),
        )
        db.add(abandoned)
        db.commit()
        run_id = abandoned.id

    try:
        with TestClient(app, headers=security_headers()) as client:
            response = client.get(f"/api/search-runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["progress_status"] == "Failed"
    finally:
        with SessionLocal() as db:
            db.query(SearchRun).filter(SearchRun.id == run_id).delete()
            db.commit()


def test_search_run_results_are_scoped_and_zero_results_do_not_fall_back():
    finish_active_searches()
    with TestClient(app, headers=security_headers()) as client:
        visible = client.get("/api/jobs", params={"page_size": 2}).json()["items"]
        assert len(visible) == 2
        included_id, excluded_id = visible[0]["id"], visible[1]["id"]
        with SessionLocal() as db:
            run = SearchRun(
                search_type="custom",
                status="completed",
                progress_status="Completed",
                criteria_json=criteria(companies=[visible[0]["company"]]),
                result_count=1,
                completed_at=datetime.now(timezone.utc),
            )
            db.add(run)
            db.flush()
            db.add(
                SearchRunJob(
                    search_run_id=run.id,
                    job_id=included_id,
                    rank=1,
                )
            )
            empty_run = SearchRun(
                search_type="custom",
                status="completed",
                progress_status="Completed",
                criteria_json=criteria(companies=["No Such Company"]),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(empty_run)
            db.commit()
            run_id = run.id
            empty_run_id = empty_run.id
        scoped = client.get("/api/jobs", params={"search_run_id": run_id, "page_size": 100})
        assert scoped.status_code == 200
        scoped_ids = {job["id"] for job in scoped.json()["items"]}
        assert included_id in scoped_ids
        assert excluded_id not in scoped_ids
        empty = client.get("/api/jobs", params={"search_run_id": empty_run_id})
        assert empty.status_code == 200
        assert empty.json()["total"] == 0
        assert empty.json()["items"] == []


def test_execution_keeps_job_record_and_creates_search_membership(monkeypatch):
    finish_active_searches()
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.status == "active"))
        assert job and job.analysis
        job_id = job.id
        run = create_search_run(
            db,
            search_type="custom",
            trigger="test",
            criteria=criteria(limit=25),
        )
        assert run
        run_id = run.id

    async def fake_refresh(db, criteria=None, progress_callback=None):
        summary = {
            "sources_checked": 1,
            "source_total": 1,
            "jobs_fetched": 1,
            "jobs_created": 0,
            "jobs_updated": 1,
            "verified_matches": 1,
            "eligible_matches": 1,
            "duplicates_removed": 0,
            "matched_jobs": {
                str(job_id): {
                    "discovered_during_run": False,
                    "matched_criteria": {"company": "Existing"},
                }
            },
            "source_metrics": [],
            "errors": [],
        }
        if progress_callback:
            progress_callback(summary)
        return summary

    monkeypatch.setattr("app.services.search_runs.refresh_all_sources", fake_refresh)
    monkeypatch.setattr("app.services.search_runs.expire_past_deadline_jobs", lambda db: 0)
    asyncio.run(execute_search_run(run_id))
    with SessionLocal() as db:
        stored = db.get(SearchRun, run_id)
        membership = db.scalar(
            select(SearchRunJob).where(
                SearchRunJob.search_run_id == run_id,
                SearchRunJob.job_id == job_id,
            )
        )
        assert stored.status == "completed"
        assert stored.result_count == 1
        assert membership is not None
        assert db.get(Job, job_id) is not None
