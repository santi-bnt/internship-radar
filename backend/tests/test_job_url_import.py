"""Targeted manual URL import, candidate isolation, dedupe and SSRF coverage."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.main import app
from app.models import CandidateJobOverride, GeneratedResume, Job, JobAnalysis, UserProfile
from app.security.identity import ALONSO_USER_ID, JOSHUA_EMAIL, JOSHUA_USER_ID
from app.security.rate_limit import sensitive_operation
from app.services.job_url_import import (
    JobExtractionError, _generic_job, extract_job_url, persist_imported_job,
)
from app.services.safe_job_fetch import (
    FetchedPage, JobFetchError, UnsafeJobURL, fetch_job_page, validate_job_url,
)
from app.sources.official_careers import OfficialCareersAdapter
from conftest import security_headers


init_db()


@pytest.fixture(scope="module", autouse=True)
def _seed_profiles():
    with TestClient(app):
        with SessionLocal() as db:
            for owner, name in [(JOSHUA_USER_ID, "Taylor Morgan"), (ALONSO_USER_ID, "Jordan Lee")]:
                if db.query(UserProfile).filter(UserProfile.owner_user_id == owner).first() is None:
                    db.add(UserProfile(owner_user_id=owner, full_name=name, degree="Computer Engineering",
                        university="Example Institute", graduation_year=2029, gpa=3.7, gpa_scale=4.0,
                        nationality="Mexican", skills=["Python"], projects=[]))
            db.commit()
        yield


def _normalized(external_id="MANUAL-123", description="Official software internship building and testing Python APIs with database integration."):
    url = f"https://careers.example.org/jobs/{external_id}"
    adapter = OfficialCareersAdapter("Example Corporation", "manual_url", url)
    return adapter.build_job(
        {"external_id": external_id, "title": "Software Engineering Intern"},
        external_id=external_id, title="Software Engineering Intern",
        location="Guadalajara, Jalisco, Mexico", description=description,
        requirements="Python and API development", apply_url=url,
        original_source_url=url, official_apply_url=url,
        official_status="open", verification_status="verified",
        verification_method="official_test", discovered_from_source="manual_url",
    )


def _delete(db, job_id):
    db.query(CandidateJobOverride).filter(CandidateJobOverride.job_id == job_id).delete()
    db.query(GeneratedResume).filter(GeneratedResume.job_id == job_id).delete()
    db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).delete()
    db.query(Job).filter(Job.id == job_id).delete()
    db.commit()


def test_new_url_and_tracking_variants_reuse_one_candidate_job():
    normalized = _normalized()
    with SessionLocal() as db:
        first = persist_imported_job(db, normalized, normalized.apply_url + "?utm_source=email", settings.effective_primary_user_id, False)
        job_id = first.job.id
        try:
            second = persist_imported_job(db, normalized, normalized.apply_url + "?utm_source=linkedin", settings.effective_primary_user_id, False)
            assert first.created is True
            assert second.created is False
            assert second.job.id == job_id
            assert second.job.analysis is not None
            assert db.query(Job).filter(Job.owner_user_id == settings.effective_primary_user_id, Job.external_id == "MANUAL-123").count() == 1
        finally:
            _delete(db, job_id)


def test_linkedin_discovery_and_official_url_reuse_canonical_job():
    normalized = _normalized(external_id="MANUAL-LINKEDIN")
    with SessionLocal() as db:
        first = persist_imported_job(
            db, normalized, "https://www.linkedin.com/jobs/view/123456789", settings.effective_primary_user_id, False,
        )
        try:
            second = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, False)
            assert second.job.id == first.job.id
            assert second.created is False
            assert any("linkedin.com" in item.get("submitted_url", "") for item in second.job.alternate_sources)
        finally:
            _delete(db, first.job.id)


def test_conflicting_official_job_ids_do_not_reuse_a_url_match():
    first = _normalized(external_id="10552937")
    second = _normalized(external_id="10559762")
    with SessionLocal() as db:
        stored = persist_imported_job(
            db, first, first.apply_url, settings.effective_primary_user_id, False,
        )
        imported = None
        try:
            # Simulate a stale/corrupt URL association: a different Amazon
            # requisition must not be merged into the existing canonical job.
            second.apply_url = stored.job.apply_url
            second.official_apply_url = stored.job.official_apply_url
            second.canonical_official_url = stored.job.canonical_official_url
            imported = persist_imported_job(
                db, second, stored.job.apply_url, settings.effective_primary_user_id, False,
            )
            assert imported.created is True
            assert imported.job.id != stored.job.id
            assert imported.job.external_id == "10559762"
            assert stored.job.external_id == "10552937"
        finally:
            if imported is not None and imported.job.id != stored.job.id:
                _delete(db, imported.job.id)
            _delete(db, stored.job.id)


def test_reimport_enriches_weak_record_and_preserves_applied_resume_and_override():
    weak = _normalized(description="Short description")
    rich = _normalized()
    with SessionLocal() as db:
        first = persist_imported_job(db, weak, weak.apply_url, settings.effective_primary_user_id, True)
        job = first.job
        job_id = job.id
        resume = GeneratedResume(
            user_id=settings.effective_primary_user_id, job_id=job_id, version=1,
            status="compiled", target_role=job.title, content_hash="manual-import-resume",
            latex_source="\\documentclass{article}", compiled_pdf=b"%PDF-1.4",
            resume_target="recommended", generation_model="local",
        )
        db.add(resume)
        db.flush()
        job.status = "applied"
        job.submitted_resume_id = resume.id
        db.commit()
        resume_id = resume.id
        try:
            result = persist_imported_job(db, rich, rich.apply_url, settings.effective_primary_user_id, True)
            assert result.created is False
            assert result.job.id == job_id
            assert "Python APIs" in result.job.description
            assert result.job.status == "applied"
            assert result.job.submitted_resume_id == resume_id
            assert db.get(GeneratedResume, resume_id) is not None
            assert result.job.candidate_job_override.force_apply_now is True
            assert result.force_apply_error is not None
        finally:
            _delete(db, job_id)


def test_force_apply_changes_only_santiagos_action_and_not_analysis():
    normalized = _normalized(external_id="MANUAL-ISOLATION")
    with SessionLocal() as db:
        joshua_before = db.query(CandidateJobOverride).filter(CandidateJobOverride.owner_user_id == JOSHUA_USER_ID).count()
        alonso_before = db.query(CandidateJobOverride).filter(CandidateJobOverride.owner_user_id == ALONSO_USER_ID).count()
        first = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, False)
        job_id = first.job.id
        before = (first.job.analysis.eligibility_status, first.job.analysis.technical_score, list(first.job.analysis.blocker_reasons))
        try:
            result = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, True)
            assert result.job.id == job_id
            assert result.force_apply_now is True
            assert (result.job.analysis.eligibility_status, result.job.analysis.technical_score, list(result.job.analysis.blocker_reasons)) == before
            assert db.query(CandidateJobOverride).filter(CandidateJobOverride.owner_user_id == JOSHUA_USER_ID).count() == joshua_before
            assert db.query(CandidateJobOverride).filter(CandidateJobOverride.owner_user_id == ALONSO_USER_ID).count() == alonso_before
        finally:
            _delete(db, job_id)


def test_confirmed_closed_cannot_force_and_unknown_is_not_closed():
    closed = _normalized(external_id="MANUAL-CLOSED")
    closed = replace(closed, official_status="closed")
    unknown = _normalized(external_id="MANUAL-UNKNOWN")
    unknown = replace(unknown, official_status="unknown", verification_status="unverified")
    with SessionLocal() as db:
        closed_result = persist_imported_job(db, closed, closed.apply_url, settings.effective_primary_user_id, True)
        unknown_result = persist_imported_job(db, unknown, unknown.apply_url, settings.effective_primary_user_id, False)
        try:
            assert closed_result.force_apply_now is False
            assert "closed" in (closed_result.force_apply_error or "").lower()
            assert unknown_result.job.official_status == "unknown"
        finally:
            _delete(db, closed_result.job.id)
            _delete(db, unknown_result.job.id)


def test_jsonld_official_page_extracts_description_and_application():
    description = "Build and test Python services and data workflows for an engineering internship."
    html = """<html><main><h1>Engineering Intern</h1><a href='/apply/123'>Apply</a>
    <script type='application/ld+json'>""" + json.dumps({
        "@type": "JobPosting", "title": "Engineering Intern", "description": description,
        "hiringOrganization": {"name": "Example Corporation"},
        "identifier": {"value": "123"},
        "jobLocation": {"address": {"addressLocality": "Guadalajara", "addressCountry": "Mexico"}},
    }) + "</script></main></html>"
    normalized, official_link = _generic_job(FetchedPage("https://careers.example.org/jobs/123", 200, "text/html", html))
    assert official_link is None
    assert description in normalized.description
    assert normalized.official_status == "open"
    assert normalized.external_id == "123"


def test_apple_hydration_data_extracts_posting_and_requires_explicit_open_state():
    job = {
        "jobNumber": "200663981-3810",
        "postingTitle": "Hardware Undergrad Engineering Internships",
        "selectedLocale": "en_US",
        "locations": [{"name": "United States", "active": True}],
        "jobSummary": "Work with hardware engineering teams on product design and system validation.",
        "description": "The internship provides practical engineering work across hardware teams and product development.",
        "minimumQualifications": "Pursuing a BS in engineering or a related field.",
        "preferredQualifications": "Experience with hardware or embedded systems.",
        "postingDate": "2026-05-21",
        "postingFooters": ["Apple accepts applications to this posting on an ongoing basis."],
    }
    hydration = {"loaderData": {"jobDetails": {"jobsData": job}}}
    encoded = json.dumps(json.dumps(hydration))
    html = f'<html><script>window.__staticRouterHydrationData = JSON.parse({encoded});</script></html>'

    normalized, _ = _generic_job(FetchedPage(
        "https://jobs.apple.com/en-us/details/200663981-3810/hardware-undergrad-engineering-internships",
        200, "text/html", html,
    ))

    assert normalized.company == "Apple"
    assert normalized.external_id == "200663981-3810"
    assert normalized.location == "United States"
    assert "minimumQualifications" not in normalized.description
    assert normalized.requirements == "Pursuing a BS in engineering or a related field."
    assert normalized.official_status == "open"
    assert normalized.official_apply_url.endswith("/apply/200663981-3810")


def test_tesla_embedded_state_reads_trailing_requisition_and_expiration():
    job = {
        "id": 279991,
        "title": "Internship, Firmware Engineer, New Programs Engineering",
        "location": "Fremont, California",
        "jobDescription": "Build and validate embedded firmware for new vehicle programs and engineering systems.",
        "jobResponsibilities": "Develop firmware and debug hardware/software integration.",
        "jobRequirements": "Currently pursuing an engineering degree with C or C++ experience.",
        "postUntilDate": "2026-01-01",
        "subWorkerType": "Intern/Apprentice",
    }
    state = {"App": {"initialReduxState": {"root": {"jobs": {"data": {"279991": job}}}}}}
    html = f'<html><script>window.tesla = {json.dumps(state)};</script></html>'

    normalized, _ = _generic_job(FetchedPage(
        "https://www.tesla.com/careers/search/job/internship-firmware-engineer-winter-spring-2027-279991",
        200, "text/html", html,
    ))

    assert normalized.company == "Tesla"
    assert normalized.external_id == "279991"
    assert normalized.title == job["title"]
    assert normalized.location == "Fremont, California"
    assert normalized.requirements == job["jobRequirements"]
    assert normalized.official_status == "closed"
    assert normalized.is_active is False


def test_linkedin_page_discovers_official_workday_posting(monkeypatch):
    from app.services import job_url_import
    submitted = "https://www.linkedin.com/jobs/view/123456789"
    official = "https://hp.wd5.myworkdayjobs.com/en-US/ExternalCareerSite/job/Internship_3169469-1"
    description = "Build and validate software services, databases and engineering workflows for HP interns."
    html = "<html><main><h1>Data Analysis Intern</h1>" + (
        "<script type='application/ld+json'>" + json.dumps({
            "@type": "JobPosting", "title": "Data Analysis Intern", "description": description,
            "hiringOrganization": {"name": "HP"},
        }) + "</script>"
    ) + f"<a href='{official}'>Apply</a></main></html>"

    async def fake_fetch(url, **_kwargs):
        if url == submitted:
            return FetchedPage(url, 200, "text/html", html)
        if url.endswith("/jobs"):
            return FetchedPage(url, 200, "application/json", json.dumps({
                "jobPostings": [{"externalPath": "/job/Internship_3169469-1"}],
            }))
        if "/wday/cxs/" in url:
            return FetchedPage(url, 200, "application/json", json.dumps({
                "jobPostingInfo": {
                    "jobReqId": "3169469", "title": "Data Analysis Intern",
                    "location": "Tlaquepaque, Jalisco, Mexico", "jobDescription": description,
                },
            }))
        raise AssertionError(url)

    monkeypatch.setattr(job_url_import, "fetch_job_page", fake_fetch)
    normalized = asyncio.run(extract_job_url(submitted))
    assert normalized.external_id == "3169469"
    assert normalized.company == "HP"
    assert normalized.official_status == "open"
    assert description in normalized.description


def test_nxp_workday_prefixed_requisition_is_preserved_and_extracted(monkeypatch):
    from app.services import job_url_import

    submitted = "https://nxp.wd3.myworkdayjobs.com/en-US/careers/job/INTERN---Automotive-MCU-NPI_R-10063630"
    description = (
        "Provide support for Automotive Microcontrollers. Develop NXP S32K5xx and "
        "S32K1xx documentation and code samples; measure power consumption; "
        "review application notes; test software, stacks, operating systems, and "
        "drivers for SPI, I2C, UART, Ethernet, CAN, LIN, and PWM."
    )

    async def fake_fetch(url, **kwargs):
        if url.endswith("/jobs"):
            assert kwargs["json_body"]["searchText"] == "R-10063630"
            return FetchedPage(url, 200, "application/json", json.dumps({
                "jobPostings": [{
                    "externalPath": "/job/INTERN---Automotive-MCU-NPI_R-10063630",
                    "title": "INTERN - Automotive MCU NPI",
                    "locationsText": "Guadalajara",
                }],
            }))
        if "/wday/cxs/" in url:
            return FetchedPage(url, 200, "application/json", json.dumps({
                "jobPostingInfo": {
                    "jobReqId": "R-10063630",
                    "title": "INTERN - Automotive MCU NPI",
                    "location": "Guadalajara, Jalisco, Mexico",
                    "timeType": "Part time",
                    "jobDescription": description,
                    "canApply": True,
                },
            }))
        raise AssertionError(url)

    monkeypatch.setattr(job_url_import, "fetch_job_page", fake_fetch)
    normalized = asyncio.run(extract_job_url(submitted))

    assert normalized.external_id == "R-10063630"
    assert normalized.company == "NXP"
    assert normalized.title == "INTERN - Automotive MCU NPI"
    assert normalized.location == "Guadalajara, Jalisco, Mexico"
    assert normalized.official_status == "open"
    assert description in normalized.description


def test_official_link_is_used_even_when_job_board_page_has_no_extractable_description(monkeypatch):
    from app.services import job_url_import
    submitted = "https://www.linkedin.com/jobs/view/123456789"
    official = "https://job-boards.greenhouse.io/example/jobs/1234567"
    official_job = _normalized(external_id="1234567")

    async def fake_fetch(url, **_kwargs):
        assert url == submitted
        return FetchedPage(url, 200, "text/html", f"<html><a href='{official}'>Apply</a></html>")

    async def fake_ats(url):
        return official_job if url == official else None

    monkeypatch.setattr(job_url_import, "fetch_job_page", fake_fetch)
    monkeypatch.setattr(job_url_import, "_ats_job", fake_ats)
    assert asyncio.run(extract_job_url(submitted)) is official_job


def test_saved_state_is_preserved_on_reimport():
    normalized = _normalized(external_id="MANUAL-SAVED")
    with SessionLocal() as db:
        first = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, False)
        job_id = first.job.id
        first.job.status = "saved"
        db.commit()
        try:
            second = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, False)
            assert second.job.status == "saved"
        finally:
            _delete(db, job_id)


def test_official_reverification_can_restore_stale_expired_record():
    normalized = _normalized(external_id="MANUAL-RESTORE")
    with SessionLocal() as db:
        first = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, False)
        job_id = first.job.id
        first.job.status = "expired"
        first.job.official_status = "unknown"
        db.commit()
        try:
            result = persist_imported_job(db, normalized, normalized.apply_url, settings.effective_primary_user_id, True)
            assert result.job.id == job_id
            assert result.job.status == "active"
            assert result.job.official_status == "open"
            assert result.force_apply_now is True
        finally:
            _delete(db, job_id)


def test_html_without_usable_description_does_not_create_job():
    with pytest.raises(JobExtractionError):
        _generic_job(FetchedPage("https://careers.example.org/jobs/123", 200, "text/html", "<h1>Intern</h1><p>Apply</p>"))


@pytest.mark.parametrize("url", [
    "http://localhost/jobs", "http://127.0.0.1/jobs", "http://10.0.0.2/jobs",
    "http://169.254.169.254/latest/meta-data", "http://[::1]/jobs",
    "file:///etc/passwd", "ftp://example.org/job", "data:text/plain,hello",
])
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(UnsafeJobURL):
        validate_job_url(url)


def test_private_redirect_oversized_and_timeout_fail_safely(monkeypatch):
    from app.services import safe_job_fetch
    original_client = httpx.AsyncClient
    async def public_addresses(_host, _port):
        return ["93.184.215.14"]
    monkeypatch.setattr(safe_job_fetch, "_public_addresses", public_addresses)

    def client_with(response):
        def factory(**kwargs):
            kwargs.pop("trust_env", None)
            return original_client(transport=httpx.MockTransport(lambda request: response(request)), **kwargs)
        return factory

    monkeypatch.setattr(safe_job_fetch.httpx, "AsyncClient", client_with(
        lambda _request: httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})
    ))
    with pytest.raises(UnsafeJobURL):
        asyncio.run(fetch_job_page("https://careers.example.org/job/1"))
    monkeypatch.setattr(safe_job_fetch.httpx, "AsyncClient", client_with(
        lambda _request: httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 100)
    ))
    with pytest.raises(JobFetchError):
        asyncio.run(fetch_job_page("https://careers.example.org/job/1", max_bytes=50))
    monkeypatch.setattr(safe_job_fetch.httpx, "AsyncClient", client_with(
        lambda _request: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout"))
    ))
    with pytest.raises(JobFetchError):
        asyncio.run(fetch_job_page("https://careers.example.org/job/1"))


def test_dns_resolution_to_private_address_is_rejected(monkeypatch):
    from app.services import safe_job_fetch
    def private_dns(*_args, **_kwargs):
        return [(None, None, None, None, ("10.0.0.4", 443))]
    monkeypatch.setattr(safe_job_fetch.socket, "getaddrinfo", private_dns)
    with pytest.raises(UnsafeJobURL):
        asyncio.run(fetch_job_page("https://careers.example.org/job/1"))


def test_http_endpoint_uses_current_authenticated_candidate(monkeypatch):
    async def fake_extract(_url):
        return _normalized(external_id="MANUAL-ENDPOINT")
    monkeypatch.setattr("app.main.extract_job_url", fake_extract)
    with TestClient(app, headers=security_headers()) as client:
        response = client.post("/api/jobs/import-url", json={"url": "https://careers.example.org/jobs/MANUAL-ENDPOINT", "force_apply_now": True})
        assert response.status_code == 200, response.text
        payload = response.json()
        job_id = payload["job_id"]
        try:
            assert payload["created"] is True
            assert payload["force_apply_now"] is True
            with SessionLocal() as db:
                candidate_jobs = db.query(Job).filter(Job.external_id == "MANUAL-ENDPOINT").all()
                by_owner = {job.owner_user_id: job for job in candidate_jobs}
                assert set(by_owner) == {settings.effective_primary_user_id, JOSHUA_USER_ID, ALONSO_USER_ID}
                assert by_owner[settings.effective_primary_user_id].id == job_id
                assert all(job.analysis is not None for job in candidate_jobs)
                assert by_owner[settings.effective_primary_user_id].candidate_job_override.force_apply_now is True
                assert by_owner[JOSHUA_USER_ID].candidate_job_override is None
                assert by_owner[ALONSO_USER_ID].candidate_job_override is None
        finally:
            with SessionLocal() as db:
                imported_ids = [job.id for job in db.query(Job).filter(Job.external_id == "MANUAL-ENDPOINT").all()]
                for imported_id in imported_ids:
                    _delete(db, imported_id)



def test_manual_job_creation_is_candidate_scoped_and_deduplicates():
    payload = {
        "company": "Manual Posting Co",
        "title": "Intern Engineer",
        "location": "Mexico City",
        "category": "Software",
        "apply_url": "https://careers.example.org/jobs/manual-123/apply",
        "source_url": "https://careers.example.org/jobs/manual-123",
        "description": "Build tools.",
        "requirements": "Python experience.",
        "preferred_qualifications": "TypeScript experience.",
    }
    with TestClient(app, headers=security_headers()) as client:
        first = client.post("/api/jobs/manual", json=payload)
        assert first.status_code == 201, first.text
        first_job = first.json()
        second = client.post("/api/jobs/manual", json=payload)
        assert second.status_code == 201, second.text
        second_job = second.json()
        try:
            assert second_job["id"] == first_job["id"]
            assert first_job["opportunity_type"] == "job"
            assert first_job["verification_status"] == "manual"
            assert first_job["official_status"] == "unknown"
            assert first_job["application_url_status"] == "unknown"
            assert first_job["company"] == payload["company"]
            assert first_job["requirements"] == payload["requirements"]
            with SessionLocal() as db:
                saved = db.get(Job, first_job["id"])
                assert saved.owner_user_id == settings.effective_primary_user_id
                assert db.query(Job).filter(Job.owner_user_id.in_([JOSHUA_USER_ID, ALONSO_USER_ID]), Job.title == payload["title"]).count() == 0
        finally:
            with SessionLocal() as db:
                _delete(db, first_job["id"])


def test_manual_job_force_apply_is_candidate_specific_and_keeps_analysis():
    payload = {
        "company": "Manual Override Co",
        "title": "Intern Engineer",
        "location": "Seattle, WA",
        "apply_url": "https://careers.example.org/jobs/manual-force-456/apply",
        "source_url": "https://careers.example.org/jobs/manual-force-456",
        "description": "Build and test software systems.",
        "force_apply_now": True,
    }
    with TestClient(app, headers=security_headers()) as client:
        response = client.post("/api/jobs/manual", json=payload)
        assert response.status_code == 201, response.text
        job_id = response.json()["id"]
        try:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                assert job.candidate_job_override.force_apply_now is True
                assert job.analysis is not None
                original_eligibility = job.analysis.eligibility_status
                assert job.official_status == "unknown"
                assert job.application_url_status == "unknown"
                assert db.query(Job).filter(
                    Job.owner_user_id.in_([JOSHUA_USER_ID, ALONSO_USER_ID]),
                    Job.title == payload["title"],
                ).count() == 0
                assert job.analysis.eligibility_status == original_eligibility
        finally:
            with SessionLocal() as db:
                _delete(db, job_id)


def test_http_endpoint_rejects_unsafe_url_without_fetch():
    with TestClient(app, headers=security_headers()) as client:
        response = client.post("/api/jobs/import-url", json={"url": "http://127.0.0.1:8000/private"})
        assert response.status_code == 422


def test_url_import_is_rate_limited_per_candidate():
    rule = sensitive_operation("/api/jobs/import-url", "POST")
    assert rule is not None
    assert rule.limit <= 20


def test_current_candidate_import_is_available_to_all_profiles_without_sharing_override(monkeypatch):
    async def fake_extract(_url):
        return _normalized(external_id="MANUAL-JOSHUA")
    monkeypatch.setattr("app.main.extract_job_url", fake_extract)
    with SessionLocal() as db:
        for owner_id, name in (
            (settings.effective_primary_user_id, "Santiago"),
            (ALONSO_USER_ID, "Alonso"),
        ):
            if db.query(UserProfile).filter(UserProfile.owner_user_id == owner_id).first() is None:
                db.add(UserProfile(owner_user_id=owner_id, full_name=name, degree="Engineering", university="Test University"))
        db.commit()
        assert set(db.query(UserProfile.owner_user_id).all()) >= {
            (settings.effective_primary_user_id,), (JOSHUA_USER_ID,), (ALONSO_USER_ID,),
        }
    with TestClient(app, headers=security_headers(JOSHUA_EMAIL, subject=JOSHUA_USER_ID)) as client:
        response = client.post("/api/jobs/import-url", json={"url": "https://careers.example.org/jobs/MANUAL-JOSHUA"})
        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]
        try:
            with SessionLocal() as db:
                assert db.get(Job, job_id).owner_user_id == JOSHUA_USER_ID
                matching_jobs = db.query(Job).filter(Job.external_id == "MANUAL-JOSHUA").all()
                by_owner = {job.owner_user_id: job for job in matching_jobs}
                assert set(by_owner) == {settings.effective_primary_user_id, JOSHUA_USER_ID, ALONSO_USER_ID}
                assert all(job.analysis is not None for job in matching_jobs)
                assert by_owner[settings.effective_primary_user_id].candidate_job_override is None
                assert by_owner[ALONSO_USER_ID].candidate_job_override is None
            forbidden = client.post("/api/jobs/import-url", json={"url": "https://careers.example.org/jobs/MANUAL-JOSHUA", "force_apply_now": True})
            assert forbidden.status_code == 403
        finally:
            with SessionLocal() as db:
                job_ids = [job.id for job in db.query(Job).filter(Job.external_id == "MANUAL-JOSHUA").all()]
                for imported_job_id in job_ids:
                    _delete(db, imported_job_id)
