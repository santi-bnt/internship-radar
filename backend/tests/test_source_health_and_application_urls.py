import asyncio

import httpx
from sqlalchemy import select

from app.jobs.refresh import classify_source_failure
from app.jobs.refresh import refresh_all_sources
from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.models import CompanySource
from app.services.seed import seed_profile_and_sources
from app.services.application_urls import resolve_application_url
from app.services.search_criteria import matches_discovery_criteria
from app.services.dedupe import same_job
from app.services.verification import verify_official_application


def test_source_failure_classification_is_actionable_and_safe():
    request = httpx.Request("GET", "https://careers.example.org/jobs")
    response = httpx.Response(403, request=request)
    state, status, message = classify_source_failure(
        httpx.HTTPStatusError("forbidden secret-body", request=request, response=response)
    )
    assert (state, status) == ("BLOCKED", 403)
    assert "secret-body" not in message


def test_guadalajara_criteria_includes_zapopan_regression_job():
    job = {
        "company": "Amazon",
        "title": "Software Development Engineer Internship",
        "location": "Zapopan, Jalisco, Mexico",
        "city": "Zapopan",
        "region": "Jalisco",
        "remote_type": "On-site",
        "remote_scope": "NOT_REMOTE",
    }
    matched, _ = matches_discovery_criteria(job, {
        "cities": ["Guadalajara"],
        "work_models": ["ON_SITE"],
        "role_categories": ["SOFTWARE_ENGINEERING"],
    })
    assert matched


def test_application_resolution_keeps_posting_when_apply_is_missing():
    result = resolve_application_url({
        "posting_url": "https://company.example.org/jobs/req-10",
        "verification_status": "partially_verified",
        "raw_data": {},
    })
    assert result.posting_url.endswith("/req-10")
    assert result.application_url == ""
    assert result.status == "MISSING"
    assert result.diagnostic == "APPLICATION_URL_NOT_FOUND"


def test_application_resolution_uses_supplied_official_metadata_only():
    result = resolve_application_url({
        "posting_url": "https://company.example.org/jobs/req-10",
        "verification_status": "verified",
        "raw_data": {"applyUrl": "/jobs/req-10/apply"},
    })
    assert result.application_url == "https://company.example.org/jobs/req-10/apply"
    assert result.status == "VERIFIED"


def test_application_resolution_uses_discovered_direct_apply_url():
    result = resolve_application_url({
        "posting_url": "https://github.com/SimplifyJobs/Summer2027-Internships",
        "apply_url": "https://company.example.org/jobs/req-11",
        "verification_status": "unverified",
        "raw_data": {},
    })
    assert result.application_url == "https://company.example.org/jobs/req-11"
    assert result.status == "DISCOVERED"


def test_application_resolution_rejects_community_listing_as_apply_url():
    result = resolve_application_url({
        "posting_url": "https://github.com/SimplifyJobs/Summer2027-Internships",
        "apply_url": "https://simplify.jobs/p/community-copy",
        "verification_status": "unverified",
        "raw_data": {},
    })
    assert result.application_url == ""


def test_http_403_does_not_expire_job(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.services.verification.httpx.AsyncClient", Client)
    result = asyncio.run(verify_official_application(
        "https://company.example.org/jobs/req-10", "Software Intern", "req-10"
    ))
    assert result.official_status == "unknown"
    assert result.verification_method == "access_restricted"
    assert result.verification_status == "partially_verified"


def test_locale_variants_dedupe_by_company_and_requisition_id():
    english = {
        "company": "Amazon", "external_id": "3123243", "ats_requisition_id": "3123243",
        "source_name": "Amazon Jobs", "apply_url": "https://amazon.jobs/en/jobs/3123243/title",
    }
    spanish = {
        "company": "Amazon", "external_id": "3123243", "ats_requisition_id": "3123243",
        "source_name": "Amazon Jobs", "apply_url": "https://amazon.jobs/es/jobs/3123243/title",
    }
    assert same_job(english, spanish)


def test_failed_source_persists_attempt_timestamp_after_rollback():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        source = CompanySource(
            company="Unsupported Test Source", source_type="unsupported_adapter",
            source_identifier="unsupported", source_url="https://careers.example.org",
            registry_type="OFFICIAL_COMPANY", enabled=True,
        )
        db.add(source)
        db.commit()
        source_id = source.id
        result = asyncio.run(refresh_all_sources(db, source_ids={source_id}))
        db.expire_all()
        stored = db.get(CompanySource, source_id)
        assert result["errors"][0]["type"] == "UNSUPPORTED"
        assert stored.last_attempt_at is not None
        assert stored.source_status == "UNSUPPORTED"


def test_manual_watchlists_are_active_targets_not_fetch_adapters():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        apple = db.scalar(select(CompanySource).where(
            CompanySource.company == "Apple",
            CompanySource.source_type == "manual_watchlist",
        ))
        assert apple is not None
        assert apple.enabled is True
        assert apple.reference_only is True
        assert apple.source_status == "WATCHLIST_ACTIVE"
        assert apple.last_status == "Watchlist active"
        assert apple.error_count == 0


def test_duolingo_and_roblox_seed_as_official_greenhouse_sources():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        sources = {
            source.company: source
            for source in db.scalars(
                select(CompanySource).where(CompanySource.company.in_(["Duolingo", "Roblox"]))
            )
        }
        assert sources["Duolingo"].source_type == "greenhouse"
        assert sources["Duolingo"].source_identifier == "duolingounirecruitment"
        assert sources["Roblox"].source_type == "greenhouse"
        assert sources["Roblox"].source_identifier == "roblox"
        assert all(source.enabled and not source.reference_only for source in sources.values())
        assert all(source.registry_type == "OFFICIAL_ATS" for source in sources.values())
