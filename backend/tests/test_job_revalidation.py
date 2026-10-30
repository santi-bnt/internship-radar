import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.jobs.refresh import revalidate_existing_jobs
from app.services.job_revalidation import is_revalidation_due, revalidate_job
from app.services.research_application_status import apply_research_application_status
from app.services.verification import VerificationResult


NOW = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)


def saved_job(**changes):
    values = {
        "id": 17,
        "owner_user_id": "candidate-1",
        "title": "Software Engineering Intern",
        "external_id": "req-17",
        "status": "active",
        "is_active": True,
        "official_apply_url": "https://careers.example.com/jobs/17",
        "canonical_official_url": "https://careers.example.com/jobs/17",
        "posting_url": "https://careers.example.com/jobs/17",
        "application_url": "https://careers.example.com/jobs/17",
        "apply_url": "https://legacy.example.test/jobs/17",
        "official_status": "open",
        "verification_status": "verified",
        "verification_method": "official_page",
        "status_reason": "Previously verified.",
        "application_url_status": "VERIFIED",
        "application_url_diagnostic": "",
        "last_verified_at": NOW - timedelta(days=2),
        "application_url_last_verified_at": NOW - timedelta(days=2),
        "last_checked_at": NOW - timedelta(days=2),
        "verification_failures": 0,
        "raw_data": {},
        "expires_at": None,
        "application_deadline": None,
        "deadline_confidence": None,
        "expired_at": None,
        "analysis": SimpleNamespace(recommendation="Apply Now"),
        "country": "United States",
        "location": "Seattle, United States",
        "region": "Washington",
        "employment_type": "Internship",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def result(
    official_status: str,
    verification_status: str = "verified",
    *,
    reason: str = "Official page checked.",
) -> VerificationResult:
    return VerificationResult(
        official_status,
        verification_status,
        "official_page",
        reason,
        "https://careers.example.com/jobs/17",
        NOW,
    )


def verifier_for(value: VerificationResult):
    async def verify(*_args):
        return value
    return verify


def test_active_job_stays_apply_now_after_a_successful_official_recheck():
    job = saved_job(title="Research Intern")
    outcome = asyncio.run(revalidate_job(job, verifier_for(result("open")), now=NOW))

    analysis = SimpleNamespace(recommendation="Review", eligibility_status="ELIGIBLE", blocker_reasons=[])
    apply_research_application_status(job, analysis, now=NOW)

    assert outcome.state == "open"
    assert job.status == "active"
    assert job.application_url_status == "VERIFIED"
    assert job.last_verified_at == NOW
    assert analysis.recommendation == "Apply Now"


def test_expired_or_closed_official_posting_becomes_expired_and_is_not_apply_now():
    for official_status in ("expired", "closed", "unavailable"):
        job = saved_job()
        outcome = asyncio.run(revalidate_job(job, verifier_for(result(official_status)), now=NOW))
        assert outcome.state == "expired"
        assert job.status == "expired"
        assert job.is_active is False
        assert job.application_url_status == "INACTIVE"


def test_temporary_network_failure_does_not_expire_the_job():
    job = saved_job()
    network_failure = result(
        "unknown", "verification_failed", reason="Official page request failed: ConnectError."
    )

    outcome = asyncio.run(revalidate_job(job, verifier_for(network_failure), now=NOW))

    assert outcome.state == "needs_verification"
    assert job.status == "active"
    assert job.is_active is True
    assert job.official_status == "unknown"
    assert job.application_url_status == "UNKNOWN"
    assert job.last_verified_at == NOW - timedelta(days=2)


def test_unknown_official_status_becomes_needs_verification_without_losing_history():
    job = saved_job()
    outcome = asyncio.run(revalidate_job(job, verifier_for(result("unknown", "partially_verified")), now=NOW))

    assert outcome.state == "needs_verification"
    assert job.status_reason.startswith("Needs Verification:")
    assert job.apply_url == "https://legacy.example.test/jobs/17"


def test_revalidation_keeps_a_bounded_history_of_previous_application_urls():
    job = saved_job(application_url="https://careers.example.com/jobs/17/apply")
    redirect = VerificationResult(
        "open", "verified", "official_page", "Official page checked.",
        "https://careers.example.com/jobs/17/new-apply", NOW,
    )

    asyncio.run(revalidate_job(job, verifier_for(redirect), now=NOW))

    assert job.application_url.endswith("/new-apply")
    assert job.raw_data["_radar_revalidation_history"][-1]["application_url"].endswith("/apply")


def test_revalidation_updates_last_verified_timestamp_only_after_success():
    job = saved_job()
    asyncio.run(revalidate_job(job, verifier_for(result("open")), now=NOW))
    assert job.last_checked_at == NOW
    assert job.last_verified_at == NOW
    assert job.application_url_last_verified_at == NOW


def test_manual_force_rechecks_a_saved_job_even_when_it_is_not_yet_due(monkeypatch):
    job = saved_job(status="saved", last_checked_at=NOW - timedelta(minutes=1))
    assert is_revalidation_due(job, now=NOW) is False

    class FakeDb:
        committed = False

        def scalars(self, _query):
            return [job]

        def scalar(self, _query):
            return SimpleNamespace(owner_user_id="candidate-1")

        def commit(self):
            self.committed = True

    async def verified_open(*_args):
        return result("open")

    monkeypatch.setattr("app.jobs.refresh.verify_official_application", verified_open)
    monkeypatch.setattr("app.jobs.refresh.persist_analysis", lambda *_args: job.analysis)

    summary = asyncio.run(revalidate_existing_jobs(FakeDb(), owner_user_id="candidate-1", job_id=17, force=True))
    assert summary["checked"] == 1
    assert summary["open"] == 1


def test_existing_saved_jobs_are_due_for_revalidation_independently_of_discovery():
    job = saved_job(status="saved", last_checked_at=NOW - timedelta(days=2))
    assert is_revalidation_due(job, now=NOW) is True


def test_explicit_past_deadline_expires_without_a_network_request():
    job = saved_job(application_deadline=date(2026, 9, 22), deadline_confidence=1.0)

    async def should_not_run(*_args):
        raise AssertionError("Past structured deadline should not fetch the posting")

    outcome = asyncio.run(revalidate_job(job, should_not_run, now=NOW))
    assert outcome.state == "expired"
    assert job.status == "expired"
