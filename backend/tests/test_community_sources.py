import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.jobs.refresh import _apply_verification_failures, _merge_duplicate, refresh_all_sources
from app.models import CompanySource
from app.services.classification import classify_remote
from app.services.dedupe import find_duplicate
from app.services.seed import seed_profile_and_sources
from app.services.scoring import analyze_job
from app.services.verification import workday_detail_api_url
from app.sources.community import (
    CommunityRateLimitError,
    CommunityRepositoryAdapter,
    discovery_priority,
    extract_ats_requisition_id,
    official_source_label,
    parse_json_jobs,
    parse_markdown_jobs,
    repository_health,
)
from app.sources.community_sources import COMMUNITY_SOURCES


def markdown_row(company="Intel", title="AI Software Intern", location="Hillsboro, Oregon", marker=""):
    return f"""| Company | Role | Location | Application |
| --- | --- | --- | --- |
| {company} | {title} {marker} | {location} | [Apply](https://jobs.intel.com/job/REQ-12345) |
"""


def adapter(identifier="simplify"):
    return CommunityRepositoryAdapter(
        "Community Source",
        identifier,
        "https://github.com/SimplifyJobs/Summer2027-Internships",
    )


def test_simplify_listing_ingestion_and_markers():
    jobs = parse_markdown_jobs(markdown_row(marker="🛂 🇺🇸 🎓"), "simplify-readme")
    assert jobs[0]["company"] == "Intel"
    assert jobs[0]["community_sponsorship_signal"] == "LIKELY_UNAVAILABLE"
    assert set(jobs[0]["community_markers"]) >= {
        "SPONSORSHIP_UNAVAILABLE_HINT", "US_CITIZENSHIP_HINT", "ADVANCED_DEGREE_HINT"
    }


def test_simplify_real_html_table_format_prefers_official_application_url():
    content = """
    <table><thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th></tr></thead>
    <tbody><tr><td><a href="https://simplify.jobs/c/Intel">Intel</a></td>
    <td>Firmware Intern 🛂</td><td>Guadalajara, Mexico</td>
    <td><a href="https://jobs.intel.com/job/REQ-555">Apply</a>
    <a href="https://simplify.jobs/p/example">Simplify</a></td></tr></tbody></table>
    """
    jobs = parse_markdown_jobs(content, "simplify-readme")
    assert jobs[0]["apply_url"] == "https://jobs.intel.com/job/REQ-555"
    assert jobs[0]["community_sponsorship_signal"] == "LIKELY_UNAVAILABLE"


def test_speedyapply_international_listing_ingestion():
    jobs = parse_markdown_jobs(
        markdown_row("Oracle", "Software Engineer Intern", "Guadalajara, Mexico"),
        "INTERN_INTL.md",
    )
    assert jobs[0]["location"] == "Guadalajara, Mexico"
    assert jobs[0]["community_origin"] == "INTERN_INTL.md"


def test_speedyapply_html_anchor_inside_markdown_cell_has_clean_url():
    content = """Company | Position | Location | Posting | Age
--- | --- | --- | --- | ---
Intel | Software Engineer Intern | Guadalajara, Mexico | <a href="https://intel.wd1.myworkdayjobs.com/external/job/Mexico/Intern_JR12345"><img alt="Apply"></a> | 1d
"""
    jobs = parse_markdown_jobs(content, "INTERN_INTL.md")
    assert jobs[0]["apply_url"].endswith("Intern_JR12345")


def test_applyguy_json_ingestion():
    jobs = parse_json_jobs(
        '{"jobs":[{"company":"NVIDIA","title":"Hardware Intern","location":"Mexico City, Mexico",'
        '"season":"Summer 2027","posted":"2026-08-01",'
        '"url":"https://applyguy.ai/jobs/12345",'
        '"listingUrl":"https://nvidia.wd5.myworkdayjobs.com/job/12345"}]}',
        "data/internships.json",
    )
    assert jobs[0]["season"] == "Summer 2027"
    assert jobs[0]["apply_url"].startswith("https://nvidia.wd5")


def test_faang_tracker_ingestion():
    jobs = parse_markdown_jobs(
        markdown_row("Amazon", "Software Development Engineer Intern", "Seattle, United States"),
        "FAANG tracker",
    )
    assert jobs[0]["company"] == "Amazon"


def test_community_aggregator_ingestion():
    jobs = parse_markdown_jobs(
        markdown_row("Bosch", "Embedded Software Intern", "Remote LATAM"),
        "community aggregator",
    )
    assert jobs[0]["title"] == "Embedded Software Intern"


def test_duplicate_role_across_four_sources_becomes_one():
    canonical = "https://boards.greenhouse.io/example/jobs/12345"
    records = [
        {
            "company": "Example", "title": "Software Engineer Intern",
            "location": "Remote Mexico", "canonical_official_url": canonical,
            "apply_url": f"https://tracker-{index}.example/role", "source_name": f"source-{index}",
        }
        for index in range(4)
    ]
    stored = []
    for record in records:
        if find_duplicate(stored, record) is None:
            stored.append(record)
    assert len(stored) == 1


def test_official_posting_replaces_community_data_but_keeps_provenance():
    job = SimpleNamespace(
        alternate_sources=[], discovery_sources=["SimplifyJobs"], community_markers=["SPONSORSHIP_UNAVAILABLE_HINT"],
        discovered_from_source="SimplifyJobs", official_apply_url=None, official_status="unknown",
        verification_status="unverified", source_name="SimplifyJobs", source_url="community",
        apply_url="https://tracker.example/job", last_seen_at=None, last_checked_at=None, missing_refreshes=0,
    )
    _merge_duplicate(job, {
        "source_name": "Intel Careers", "source_url": "https://jobs.intel.com", "apply_url": "https://jobs.intel.com/job/123",
        "official_apply_url": "https://jobs.intel.com/job/123", "official_status": "open",
        "verification_status": "verified", "description": "Official description", "verified_from_source": "Intel Careers",
        "discovered_from_source": "Intel Careers", "discovery_sources": ["Intel Careers"], "community_markers": [],
    })
    assert job.description == "Official description"
    assert job.discovered_from_source == "SimplifyJobs"
    assert job.discovery_sources == ["SimplifyJobs", "Intel Careers"]


def test_community_sponsorship_hint_is_not_final_fact():
    raw = parse_markdown_jobs(markdown_row(marker="🛂"), "simplify")[0]
    job = adapter().normalize_job(raw)
    assert job.community_sponsorship_signal == "LIKELY_UNAVAILABLE"
    assert job.sponsorship_status == "UNKNOWN"
    assert job.verification_status == "unverified"


def test_unverified_community_job_never_becomes_eligible_automatically():
    raw = parse_markdown_jobs(
        markdown_row(location="Guadalajara, Mexico"),
        "simplify",
    )[0]
    job = adapter().normalize_job(raw)
    analysis = analyze_job(job, SimpleNamespace(graduation_year=2029, skills=[]))
    assert analysis.eligibility_status == "UNKNOWN"
    assert analysis.recommendation == "Review"


def test_closed_community_job_is_archived_candidate_not_officially_verified():
    raw = parse_markdown_jobs(markdown_row(marker="🔒"), "tracker")[0]
    job = adapter().normalize_job(raw)
    assert job.is_active is False
    assert job.discovery_status == "community_closed"
    assert job.official_status == "unknown"


def test_official_closed_posting_deactivates_job():
    data = {"official_status": "closed", "verification_status": "verified", "is_active": True}
    _apply_verification_failures(None, data)
    assert data["is_active"] is False


def test_mexico_role_is_recognized():
    remote = classify_remote("Mexico City, Mexico", "On-site internship")
    assert remote.can_work_from_mexico == "YES"


def test_guadalajara_role_receives_higher_discovery_priority():
    mexico = {"title": "Software Intern", "location": "Guadalajara, Mexico"}
    us = {"title": "Software Intern", "location": "Seattle, United States"}
    assert discovery_priority(mexico) > discovery_priority(us)


def test_remote_mexico_is_recognized():
    remote = classify_remote("Remote", "Remote from Mexico")
    assert remote.remote_scope == "MEXICO"
    assert remote.can_work_from_mexico == "YES"


def test_remote_latam_is_recognized():
    remote = classify_remote("Remote", "Remote LATAM; Mexico is an eligible country")
    assert remote.remote_scope == "LATAM"
    assert remote.can_work_from_mexico == "YES"


def test_remote_us_only_is_not_mexico_compatible():
    remote = classify_remote("Remote", "Candidates must reside in the United States")
    assert remote.remote_scope == "US_ONLY"
    assert remote.can_work_from_mexico == "NO"


def test_stale_repository_receives_lower_priority():
    now = datetime.now(timezone.utc)
    status, priority = repository_health(now - timedelta(days=120), 80, now)
    assert status == "STALE"
    assert priority == 40


def test_broken_source_does_not_break_full_refresh():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        good = CompanySource(
            company="Community test good", source_type="local_json", source_identifier="data/test_jobs.json",
            source_url="local://community-test-good", enabled=True,
        )
        broken = CompanySource(
            company="Community test broken", source_type="local_json", source_identifier="data/missing-community.json",
            source_url="local://community-test-broken", enabled=True,
        )
        db.add_all([good, broken])
        db.commit()
        summary = asyncio.run(refresh_all_sources(db, source_ids={good.id, broken.id}))
        assert summary["sources_checked"] == 2
        assert len(summary["errors"]) == 1
        db.delete(good)
        db.delete(broken)
        db.commit()


def test_github_rate_limit_is_handled(monkeypatch):
    class Response:
        status_code = 429
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.sources.community.httpx.AsyncClient", Client)
    with pytest.raises(CommunityRateLimitError, match="rate limit"):
        asyncio.run(adapter().fetch_jobs())


def test_official_ats_remains_canonical_source():
    label, confidence = official_source_label(
        "https://intel.wd1.myworkdayjobs.com/External/job/123", "Intel"
    )
    assert label == "Workday"
    assert confidence == 95


def test_workday_requisition_uses_posting_id_not_location_segment():
    first = extract_ats_requisition_id(
        "https://example.wd5.myworkdayjobs.com/jobs/job/US-TX-Austin/Firmware-Intern_REQ12345"
    )
    second = extract_ats_requisition_id(
        "https://example.wd5.myworkdayjobs.com/jobs/job/US-TX-Austin/Software-Intern_REQ98765"
    )
    assert first == "REQ12345"
    assert second == "REQ98765"
    assert first != second


def test_workday_public_url_resolves_to_official_detail_api():
    url = workday_detail_api_url(
        "https://intel.wd1.myworkdayjobs.com/en-US/External/job/Mexico/Software-Intern_JR12345"
    )
    assert url == (
        "https://intel.wd1.myworkdayjobs.com/"
        "wday/cxs/intel/External/job/Mexico/Software-Intern_JR12345"
    )


def test_registry_contains_all_five_requested_sources():
    identifiers = {source["source_identifier"] for source in COMMUNITY_SOURCES}
    assert identifiers == {"simplify", "speedyapply", "faang_tracker", "applyguy", "community_aggregator"}
