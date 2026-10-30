import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.jobs.refresh import verify_research_openings
from app.services.research_application_status import apply_research_application_status
from app.services.verification import VerificationResult


def research_job(**changes):
    values = {
        "title": "Research Intern",
        "employment_type": "Internship",
        "company": "Example Research Lab",
        "country": "United States",
        "location": "Redmond, Washington, United States",
        "region": "Washington",
        "status": "active",
        "is_active": True,
        "official_status": "open",
        "verification_status": "verified",
        "application_url_status": "VERIFIED",
        "official_apply_url": "https://careers.example.com/jobs/research-intern",
        "application_url": "https://careers.example.com/jobs/research-intern",
        "apply_url": "https://careers.example.com/jobs/research-intern",
        "application_deadline": None,
        "expires_at": None,
        "status_reason": "",
        "expired_at": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def eligible_analysis(**changes):
    values = {
        "recommendation": "Review",
        "eligibility_status": "ELIGIBLE",
        "blocker_reasons": [],
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_verified_open_us_research_internship_is_apply_now():
    job = research_job()
    analysis = eligible_analysis()

    result = apply_research_application_status(job, analysis)

    assert result == "Apply Now"
    assert analysis.recommendation == "Apply Now"
    assert job.status == "active"


def test_us_research_internship_with_expired_deadline_is_expired():
    job = research_job(application_deadline=date.today() - timedelta(days=1))
    analysis = eligible_analysis()

    result = apply_research_application_status(job, analysis)

    assert result == "Expired"
    assert analysis.recommendation == "Expired"
    assert job.status == "expired"
    assert job.is_active is False


def test_us_research_internship_with_inactive_application_is_expired():
    job = research_job(application_url_status="INACTIVE")
    analysis = eligible_analysis()

    result = apply_research_application_status(job, analysis)

    assert result == "Expired"
    assert analysis.recommendation == "Expired"
    assert job.status == "expired"


def test_microsoft_beijing_research_intern_is_not_a_us_research_shortcut():
    job = research_job(
        company="Microsoft",
        external_id="200050325",
        country="China",
        location="Beijing, China",
        region="Beijing",
    )
    analysis = eligible_analysis()

    result = apply_research_application_status(job, analysis)

    assert result is None
    assert analysis.recommendation == "Review"
    assert analysis.recommendation != "Apply Now"


def test_research_internship_with_unknown_application_status_needs_verification():
    job = research_job(
        official_status="unknown",
        verification_status="partially_verified",
        application_url_status="UNKNOWN",
    )
    analysis = eligible_analysis()

    result = apply_research_application_status(job, analysis)

    assert result == "Needs Verification"
    assert analysis.recommendation == "Needs Verification"


def test_verified_hard_eligibility_blocker_never_becomes_apply_now():
    job = research_job()
    analysis = eligible_analysis(
        recommendation="Not Eligible",
        eligibility_status="NOT_ELIGIBLE",
        blocker_reasons=["Verified work authorization requirement conflicts with the profile."],
    )

    result = apply_research_application_status(
        job,
        analysis,
        now=datetime.now(timezone.utc),
    )

    assert result is None
    assert analysis.recommendation == "Not Eligible"


def test_research_verification_pass_checks_official_application_before_apply_now(monkeypatch):
    job = research_job(owner_user_id="candidate-1", external_id="research-1")
    job.analysis = eligible_analysis()

    class FakeDb:
        committed = False

        def scalars(self, _query):
            return [job]

        def scalar(self, _query):
            return SimpleNamespace(owner_user_id="candidate-1")

        def commit(self):
            self.committed = True

    async def verified_open(*_args):
        return VerificationResult(
            "open",
            "verified",
            "official_page",
            "Official application is still accepting submissions.",
            job.official_apply_url,
            datetime.now(timezone.utc),
        )

    def persist_after_verification(_db, current_job, _profile):
        apply_research_application_status(current_job, current_job.analysis)
        return current_job.analysis

    fake_db = FakeDb()
    monkeypatch.setattr("app.jobs.refresh.verify_official_application", verified_open)
    monkeypatch.setattr("app.jobs.refresh.persist_analysis", persist_after_verification)

    summary = asyncio.run(verify_research_openings(fake_db, owner_user_id="candidate-1"))

    assert summary == {"checked": 1, "open": 1, "expired": 0, "needs_verification": 0}
    assert job.application_url_status == "VERIFIED"
    assert job.analysis.recommendation == "Apply Now"
    assert fake_db.committed is True
