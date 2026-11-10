import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import Base
from app.models import CompanySource, Job, JobDescriptionSnapshot, OpportunityDiscoveryState, OpportunitySourceObservation, UserProfile
from app.schemas.discovery import RawOpportunity, DiscoverySearchQuery
from app.services.discovery_records import canonical_opportunity, eligibility_facts, record_absence
from app.services.dedupe import same_job, possible_duplicate
from app.services.official_source_resolver import OfficialSourceResolver
from app.services.unified_discovery import criteria_for, import_external
from app.sources.ashby import AshbyAdapter
from app.sources.freehire import FreehireSource
from app.sources.external import ManualSource
from app.sources.greenhouse import GreenhouseAdapter
from app.sources.lever import LeverAdapter


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.info["owner_user_id"] = "discovery-owner"
        session.add(UserProfile(owner_user_id="discovery-owner", full_name="Alex Rivera", degree="Robotics and Digital Systems Engineering", university="Example Institute of Technology", graduation_year=2028, nationality="Mexican", gpa=3.7, gpa_scale=4, preferred_roles=["Robotics", "Embedded Systems"], countries_to_search=["United States", "Canada", "Mexico"]))
        session.commit()
        yield session
    engine.dispose()


def raw(**changes):
    return RawOpportunity(**({"sourceName": "External A", "sourceUrl": "https://aggregator.example/jobs/1", "externalId": "a1", "title": "Robotics Intern", "company": "Example Robotics", "location": "Seattle, United States", "description": "Undergraduate robotics internship using Python and embedded systems.", "canonicalUrl": "https://jobs.lever.co/example/job1"} | changes))


async def no_resolution(self, normalized):
    return normalized


def test_raw_input_rejects_private_urls_and_unknown_eligibility_is_not_invented():
    with pytest.raises(ValueError):
        raw(canonicalUrl="http://127.0.0.1/private")
    normalized = ManualSource("External", "manual", "https://example.com").normalize_job(raw().model_dump(mode="json"))
    facts = eligibility_facts(normalized)
    assert facts["internationalEligibility"] == facts["visaSponsorship"] == facts["canApplyFromMexico"] == "unknown"
    assert facts["studentLevel"] == "Undergraduate"


def test_greenhouse_updated_date_is_not_misrepresented_as_posted_date():
    job = GreenhouseAdapter("Example", "example", "https://boards.greenhouse.io/example").normalize_job({"id": 7, "title": "Robotics Intern", "location": {"name": "Seattle, United States"}, "absolute_url": "https://boards.greenhouse.io/example/jobs/7", "updated_at": "2026-11-01T00:00:00Z", "content": "Robotics internship"})
    assert job.posted_at is None
    assert job.raw_data["updated_at"] == "2026-11-01T00:00:00Z"


def test_lever_preserves_original_published_date_and_posting_identity():
    job = LeverAdapter("Example", "example", "https://jobs.lever.co/example").normalize_job({"id": "id-1", "text": "Embedded Intern", "categories": {"location": "Toronto, Canada"}, "hostedUrl": "https://jobs.lever.co/example/id-1", "applyUrl": "https://jobs.lever.co/example/id-1/apply", "createdAt": 1793491200000})
    assert job.external_id == "id-1" and job.posted_at.year == 2026
    assert job.original_source_url.endswith("/id-1")


def test_ashby_parsing_uses_published_at_job_and_apply_urls():
    adapter = AshbyAdapter("Example", "example-board", "https://jobs.ashbyhq.com/example-board")
    job = adapter.normalize_job({"title": "FPGA Intern", "location": "Toronto, Canada", "jobUrl": "https://jobs.ashbyhq.com/example-board/job-id", "applyUrl": "https://jobs.ashbyhq.com/example-board/job-id/application", "descriptionPlain": "Verilog internship", "publishedAt": "2026-11-01T00:00:00Z", "employmentType": "Intern"})
    assert job.external_id == "job-id" and job.posted_at.day == 1
    assert job.verification_status == "verified"
    assert job.canonical_official_url.endswith("/job-id/application")
    with pytest.raises(ValueError):
        _ = AshbyAdapter("Invalid", "../private", "https://jobs.ashbyhq.com/x").api_url


def test_freehire_normalizes_original_url_and_preserves_attribution():
    job = FreehireSource("Freehire", "search", "https://freehire.me").normalize_job({"public_slug": "robotics-1", "external_id": "agg-1", "url": "https://jobs.lever.co/example/official-id", "title": "Robotics Intern", "company": "Example", "location": "Canada", "posted_at": "2026-11-01", "source": "lever"})
    assert job.apply_url == "https://jobs.lever.co/example/official-id"
    assert job.source_url.startswith("https://freehire.me/api/v1/jobs/")
    assert job.discovered_from_source == "Freehire"
    assert job.verification_status == "unverified"
    assert "Freehire" in job.raw_data["_discovery_metadata"]["attribution"]


def test_freehire_is_opt_in_and_uses_filtered_search_endpoint(monkeypatch):
    adapter = FreehireSource("Freehire", "search", "https://freehire.me")
    monkeypatch.setattr(settings, "freehire_enabled", False)
    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(adapter.fetch_jobs())
    assert adapter.API_URL.endswith("/jobs/search")


def test_uncertain_fuzzy_matches_are_flagged_instead_of_merged():
    left = {"company": "Example", "title": "Software Engineering Intern", "location": "Canada"}
    right = {**left, "title": "Software Engineer Internship"}
    assert not same_job(left, right)
    confidence, found = possible_duplicate([left], right)
    assert confidence > .75 and found is left
    assert not same_job({**left, "source_name": "Greenhouse", "external_id": "1", "apply_url": "https://boards.greenhouse.io/a/jobs/1"}, {**left, "source_name": "Lever", "external_id": "1", "title": "Different Intern", "apply_url": "https://jobs.lever.co/a/1"})


def test_imports_share_pipeline_preserve_seen_dates_sources_and_description_history(db, monkeypatch):
    monkeypatch.setattr(OfficialSourceResolver, "resolve", no_resolution)
    first, summary = asyncio.run(import_external(db, "discovery-owner", raw(postedAt="2026-10-01T00:00:00Z")))
    assert summary["jobs_created"] == 1 and first.status == "completed"
    job = db.scalar(select(Job))
    first_seen, published = job.first_seen_at, job.posted_at
    job.status = "applied"
    db.commit()
    second, summary = asyncio.run(import_external(db, "discovery-owner", raw(sourceName="External B", sourceUrl="https://other.example/jobs/7", externalId="b7", description="Updated undergraduate robotics internship using Python and embedded systems.")))
    assert summary["duplicates_removed"] == 1 and summary["jobs_created"] == 0
    assert job.first_seen_at == first_seen and job.last_seen_at >= first_seen and job.posted_at == published
    assert job.status == "applied"
    assert len(db.scalars(select(OpportunitySourceObservation)).all()) == 2
    assert len(db.scalars(select(JobDescriptionSnapshot)).all()) == 2
    view = canonical_opportunity(db, job)
    assert view["internationalEligibility"] == "unknown" and view["fundingType"] == "Unknown"
    assert view["fitScore"] is not None and view["eligibilityScore"] is not None


def test_first_seen_defines_new_not_old_posted_date(db, monkeypatch):
    monkeypatch.setattr(OfficialSourceResolver, "resolve", no_resolution)
    asyncio.run(import_external(db, "discovery-owner", raw(postedAt="2020-01-01")))
    job = db.scalar(select(Job))
    assert canonical_opportunity(db, job)["isNew"]
    job.first_seen_at = datetime.now(timezone.utc) - timedelta(days=10)
    assert not canonical_opportunity(db, job)["isNew"]


def test_filtered_search_absence_cannot_close_job(db, monkeypatch):
    monkeypatch.setattr(OfficialSourceResolver, "resolve", no_resolution)
    asyncio.run(import_external(db, "discovery-owner", raw()))
    job = db.scalar(select(Job))
    before = job.missing_refreshes
    record_absence(db, job, complete_snapshot=False)
    assert job.missing_refreshes == before and job.is_active
    state = db.scalar(select(OpportunityDiscoveryState))
    assert state.availability != "CLOSED"
    record_absence(db, job, complete_snapshot=True)
    assert state.availability == "MISSING"


def test_explicit_citizenship_restriction_keeps_fit_separate_from_eligibility():
    job = SimpleNamespace(description="Undergraduate robotics program. Must be a US citizen.", requirements="", verification_status="verified", canonical_official_url="https://example.edu/program", official_apply_url="https://example.edu/apply", source_url="https://example.edu/program")
    facts = eligibility_facts(job)
    assert facts["internationalEligibility"] == "notEligible"
    assert facts["canApplyFromMexico"] == "no"
    assert facts["eligibilityEvidence"] and facts["eligibilitySourceUrl"].startswith("https://example.edu")


def test_negated_international_and_visa_statements_are_not_positive_matches():
    job = SimpleNamespace(description="Not open to international students. No visa sponsorship required.", requirements="", verification_status="verified", canonical_official_url="https://example.edu/program", official_apply_url="https://example.edu/apply", source_url="https://example.edu/program")
    facts = eligibility_facts(job)
    assert facts["internationalEligibility"] == "notEligible"
    assert facts["visaSponsorship"] == "notRequired"
    job.verification_status = "unverified"
    assert eligibility_facts(job)["internationalEligibility"] == "unknown"


def test_profile_drives_dynamic_queries_and_countries(db):
    profile = db.scalar(select(UserProfile))
    criteria = criteria_for(profile, DiscoverySearchQuery())
    assert criteria["include_keywords"] == ["Robotics", "Embedded Systems"]
    assert criteria["countries"] == ["United States", "Canada"]
    criteria = criteria_for(profile, DiscoverySearchQuery(query="FPGA firmware", countries=["Germany"]))
    assert criteria["include_keywords"] == ["FPGA", "firmware"] and criteria["countries"] == ["Germany"]


def test_resolver_prefers_verified_official_posting_and_keeps_freehire_observation(db, monkeypatch):
    from app.sources.base import NormalizedJob
    from app.services import job_url_import
    original = FreehireSource("Freehire", "search", "https://freehire.me").normalize_job({"public_slug": "r1", "external_id": "agg1", "url": "https://jobs.lever.co/example/official1", "title": "Robotics Intern", "company": "Example Robotics", "location": "Seattle, United States"})
    official = LeverAdapter("Example Robotics", "example", "https://jobs.lever.co/example").normalize_job({"id": "official1", "text": "Robotics Intern", "descriptionPlain": "Open to international undergraduate students. Python robotics internship.", "categories": {"location": "Seattle, United States"}, "hostedUrl": "https://jobs.lever.co/example/official1", "applyUrl": "https://jobs.lever.co/example/official1/apply"})
    async def extract(_):
        return official
    monkeypatch.setattr(job_url_import, "extract_job_url", extract)
    resolved = asyncio.run(OfficialSourceResolver().resolve(original))
    assert resolved.verification_status == "verified"
    assert resolved.canonical_official_url.startswith("https://jobs.lever.co")
    assert resolved.discovered_from_source == "Freehire"
    job = Job(owner_user_id="discovery-owner", **resolved.to_dict())
    db.add(job); db.flush()
    from app.services.discovery_records import record_discovery
    record_discovery(db, job, resolved.to_dict()); db.flush()
    assert {o.source for o in db.scalars(select(OpportunitySourceObservation))} == {"Freehire", "Lever"}
    assert eligibility_facts(job)["internationalEligibility"] == "confirmed"


def test_resolver_does_not_verify_title_company_mismatch(monkeypatch):
    from app.services import job_url_import
    original = ManualSource("External", "manual", "https://example.com").normalize_job(raw().model_dump(mode="json"))
    other = LeverAdapter("Other Employer", "other", "https://jobs.lever.co/other").normalize_job({"id": "1", "text": "Robotics Intern", "hostedUrl": "https://jobs.lever.co/other/1", "descriptionPlain": "Internship"})
    async def extract(_): return other
    monkeypatch.setattr(job_url_import, "extract_job_url", extract)
    resolved = asyncio.run(OfficialSourceResolver().resolve(original))
    assert resolved.verification_status == "unverified"


def test_repeated_complete_snapshots_close_but_filtered_runs_do_not(db, monkeypatch):
    from app.jobs import refresh
    source = CompanySource(owner_user_id="discovery-owner", company="Example Robotics", source_type="lever", source_identifier="example", source_url="https://jobs.lever.co/example", enabled=True, reference_only=False, registry_type="OFFICIAL_ATS")
    db.add(source); db.flush()
    normalized = LeverAdapter(source.company, source.source_identifier, source.source_url).normalize_job({"id": "job1", "text": "Robotics Intern", "categories": {"location": "Seattle, United States"}, "hostedUrl": "https://jobs.lever.co/example/job1", "descriptionPlain": "Undergraduate robotics internship"})
    job = Job(owner_user_id="discovery-owner", **normalized.to_dict())
    db.add(job); db.commit()
    class EmptyBoard:
        complete_snapshot = True
        all_external_ids = {"job1"}  # Job exists on full board but query didn't select it.
        async def collect(self): return []
    monkeypatch.setattr(refresh, "create_adapter", lambda *a, **k: EmptyBoard())
    asyncio.run(refresh.refresh_all_sources(db, source_ids={source.id}, criteria={"include_keywords": ["firmware"]}, send_notifications=False))
    assert job.missing_refreshes == 0 and job.is_active
    EmptyBoard.all_external_ids = set()  # Subsequent full snapshots prove absence.
    for expected in (1, 2, 3):
        asyncio.run(refresh.refresh_all_sources(db, source_ids={source.id}, criteria={"include_keywords": ["firmware"]}, send_notifications=False))
        assert job.missing_refreshes == expected
    assert not job.is_active and job.status == "archived"
    assert db.scalar(select(OpportunityDiscoveryState)).availability == "CLOSED"


def test_one_failed_source_does_not_stop_other_sources_or_send_email(db, monkeypatch):
    from app.jobs import refresh
    broken = CompanySource(owner_user_id="discovery-owner", company="A Broken", source_type="ashby", source_identifier="broken", source_url="https://jobs.ashbyhq.com/broken", enabled=True)
    healthy = CompanySource(owner_user_id="discovery-owner", company="B Healthy", source_type="lever", source_identifier="healthy", source_url="https://jobs.lever.co/healthy", enabled=True)
    db.add_all([broken, healthy]); db.commit()
    normalized = ManualSource("External", "manual", "https://example.com").normalize_job(raw().model_dump(mode="json"))
    class Broken:
        async def collect(self):
            raise httpx.HTTPStatusError("Unavailable", request=httpx.Request("GET", "https://example.com"), response=httpx.Response(403))
    class Healthy:
        complete_snapshot = False
        async def collect(self): return [normalized]
    monkeypatch.setattr(refresh, "create_adapter", lambda source, **k: Broken() if source.id == broken.id else Healthy())
    def unexpected(*a): raise AssertionError("Discovery may not send email")
    monkeypatch.setattr(refresh, "_dispatch_notifications", unexpected)
    summary = asyncio.run(refresh.refresh_all_sources(db, source_ids={broken.id, healthy.id}, send_notifications=False))
    assert summary["sources_checked"] == 2 and len(summary["errors"]) == 1
    assert summary["jobs_created"] == 1 and len(db.scalars(select(Job)).all()) == 1


def test_observations_and_external_import_never_cross_candidate_scope(db, monkeypatch):
    monkeypatch.setattr(OfficialSourceResolver, "resolve", no_resolution)
    with pytest.raises(ValueError, match="scope"):
        asyncio.run(import_external(db, "another-owner", raw()))
    assert db.scalars(select(Job)).all() == []


def test_source_cadence_uses_catalog_without_replacing_existing_scheduler():
    from app.services.discovery_orchestration import refresh_interval_hours
    assert refresh_interval_hours(SimpleNamespace(source_type="ashby")) == 6
    assert refresh_interval_hours(SimpleNamespace(source_type="workday")) == 12
    assert refresh_interval_hours(SimpleNamespace(source_type="web_search")) == 24


def test_partial_enrichment_cannot_erase_verified_employer_or_reset_absence(db):
    from app.jobs.refresh import _merge_duplicate
    official = LeverAdapter("Example Robotics", "example", "https://jobs.lever.co/example").normalize_job({"id": "1", "text": "Robotics Intern", "hostedUrl": "https://jobs.lever.co/example/1", "descriptionPlain": "Verified source description"})
    job = Job(owner_user_id="discovery-owner", **official.to_dict())
    db.add(job); db.flush()
    job.missing_refreshes = 2
    partial = official.to_dict() | {"company": "Unknown", "verification_status": "partially_verified", "description": "Weak search snippet"}
    _merge_duplicate(job, partial)
    assert job.company == "Example Robotics" and job.verification_status == "verified"
    assert job.description == "Verified source description"
    assert job.missing_refreshes == 2


def test_cached_filter_does_not_truncate_before_finding_older_matches(db):
    from app.models import SearchRun
    from app.services.unified_discovery import search_results
    for i in range(105):
        db.add(Job(owner_user_id="discovery-owner", source_name="Manual", source_url=f"https://example.edu/{i}", title="Unrelated sales role", company="Example", apply_url=f"https://example.edu/{i}", description="Sales", raw_data_hash=str(i)))
    wanted = Job(owner_user_id="discovery-owner", source_name="Manual", source_url="https://example.edu/robotics", title="Robotics Internship", company="Example", apply_url="https://example.edu/robotics", description="Robotics", raw_data_hash="robotics", first_seen_at=datetime.now(timezone.utc) - timedelta(days=100))
    db.add(wanted)
    run = SearchRun(owner_user_id="discovery-owner", search_type="discovery_quick", result_count=0, criteria_json={"include_keywords": ["robotics"]})
    db.add(run); db.commit()
    assert [r["id"] for r in search_results(db, "discovery-owner", run)] == [wanted.id]


def test_unverified_sightings_and_network_failures_never_manufacture_closure():
    from app.jobs.refresh import _apply_verification_failures
    previous = SimpleNamespace(verification_failures=9)
    for method in ("external_discovery", "http_error", "not_attempted"):
        data = {"verification_status": "unverified", "official_status": "unknown", "verification_method": method, "is_active": True}
        _apply_verification_failures(previous, data)
        assert data["official_status"] == "unknown" and data["is_active"]


def test_company_official_url_stays_preferred_over_ats_enrichment(db):
    from app.jobs.refresh import _merge_duplicate
    job = Job(owner_user_id="discovery-owner", source_name="Official Careers", source_url="https://careers.example.org", company="Example", title="Robotics Intern", apply_url="https://careers.example.org/jobs/1", official_apply_url="https://careers.example.org/jobs/1", canonical_official_url="https://careers.example.org/jobs/1", verification_status="verified", official_status="open", raw_data_hash="official")
    db.add(job); db.flush()
    other = LeverAdapter("Example", "example", "https://jobs.lever.co/example").normalize_job({"id": "1", "text": "Robotics Intern", "hostedUrl": "https://jobs.lever.co/example/1", "descriptionPlain": "ATS copy"})
    _merge_duplicate(job, other.to_dict())
    assert job.canonical_official_url == "https://careers.example.org/jobs/1"


def test_per_host_pacing_uses_public_source_policy(monkeypatch):
    from app.services import source_rate_limit as limiter
    delays = []
    async def sleep(delay): delays.append(delay)
    monkeypatch.setattr(settings, "source_rate_limit_seconds", .25)
    monkeypatch.setattr(limiter, "_next_request", {})
    monkeypatch.setattr(limiter, "monotonic", lambda: 100.0)
    monkeypatch.setattr(limiter.asyncio, "sleep", sleep)
    request = httpx.Request("GET", "https://freehire.me/api/v1/jobs/search")
    asyncio.run(limiter.pace_request(request)); asyncio.run(limiter.pace_request(request))
    assert delays == [1.0]


def test_verified_company_posting_is_canonical_with_ats_application_link(monkeypatch):
    from app.services import safe_job_fetch
    from app.services.safe_job_fetch import FetchedPage
    url = "https://careers.example.org/jobs/robotics-1"
    html = '''<html><script type="application/ld+json">{"@type":"JobPosting","title":"Robotics Intern","url":"https://careers.example.org/jobs/robotics-1","hiringOrganization":{"name":"Example Robotics"},"description":"Undergraduate robotics internship developing Python tools and embedded systems with sensors and hardware integration."}</script><h1>Robotics Intern</h1><a href="https://jobs.lever.co/example/1/apply">Apply Now</a></html>'''
    async def fetch(_): return FetchedPage(url, 200, "text/html", html)
    monkeypatch.setattr(safe_job_fetch, "fetch_job_page", fetch)
    normalized = ManualSource("External", "manual", "https://example.com").normalize_job(raw(canonicalUrl=url).model_dump(mode="json"))
    result = asyncio.run(OfficialSourceResolver(["careers.example.org"]).resolve(normalized))
    assert result.canonical_official_url == url
    assert result.apply_url == "https://jobs.lever.co/example/1/apply"


def test_slug_derived_employer_can_be_partial_without_fabricating_display_name(monkeypatch):
    from app.services import job_url_import
    original = ManualSource("External", "manual", "https://example.com").normalize_job(raw(company="Example Robotics Inc").model_dump(mode="json"))
    official = LeverAdapter("example", "example", "https://jobs.lever.co/example").normalize_job({"id": "job1", "text": "Robotics Intern", "hostedUrl": "https://jobs.lever.co/example/job1", "descriptionPlain": "Undergraduate robotics internship"})
    official.raw_data["_employer_identity"] = "board_slug"
    async def extract(_): return official
    monkeypatch.setattr(job_url_import, "extract_job_url", extract)
    result = asyncio.run(OfficialSourceResolver().resolve(original))
    assert result.company == "Example Robotics Inc"
    assert result.verification_status == "partially_verified"
