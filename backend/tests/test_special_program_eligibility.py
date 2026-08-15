from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs.refresh import persist_analysis
from app.main import app
from app.models import Job, UserProfile
from app.services.classification import qualifies_priority_alert
from app.services.dedupe import find_duplicate
from app.services.scoring import analyze_job
from app.services.special_program_eligibility import (
    PEOPLE_WITH_DISABILITIES,
    RETURN_TO_WORK_PROGRAM,
    VETERANS,
    evaluate_special_program_eligibility,
    extract_special_program_signals,
)
from conftest import security_headers


def posting(base_job, requirements="", **overrides):
    job = dict(base_job)
    job["requirements"] = requirements
    job.update(overrides)
    return job


def decision(job, profile):
    signals = extract_special_program_signals(job)
    return signals, evaluate_special_program_eligibility(signals, profile)


def test_oracle_veteran_internship_program_is_not_eligible(base_job, profile):
    job = posting(
        base_job,
        "To qualify, you must be a U.S. Veteran transitioning from active service or an active-duty military spouse.",
        title="Oracle Veteran Internship Program - Software Intern",
    )
    signals, result = decision(job, profile)

    assert signals.special_program_type == VETERANS
    assert signals.special_program_required is True
    assert result.state == "NOT_ELIGIBLE"


def test_veterans_only_role_is_not_eligible(base_job, profile):
    signals, result = decision(
        posting(base_job, "This internship is available to veterans only."),
        profile,
    )

    assert signals.special_program_required is True
    assert result.state == "NOT_ELIGIBLE"


def test_active_duty_military_spouse_program_is_not_eligible(base_job, profile):
    _, result = decision(
        posting(base_job, "Applicants must be an active-duty military spouse."),
        profile,
    )

    assert result.state == "NOT_ELIGIBLE"


def test_disability_only_program_is_not_eligible(base_job, profile):
    signals, result = decision(
        posting(base_job, "Applicants must identify as a person with a disability."),
        profile,
    )

    assert signals.special_program_type == PEOPLE_WITH_DISABILITIES
    assert result.state == "NOT_ELIGIBLE"


def test_equal_opportunity_disability_language_has_zero_negative_impact(base_job, profile):
    _, result = decision(
        posting(
            base_job,
            "We are an equal opportunity employer. Qualified applicants with disabilities will receive consideration.",
        ),
        profile,
    )

    assert result.state == "ELIGIBLE"


def test_veterans_encouraged_to_apply_has_zero_negative_impact(base_job, profile):
    _, result = decision(
        posting(base_job, "Veterans and military spouses are encouraged to apply."),
        profile,
    )

    assert result.state == "ELIGIBLE"


def test_veteran_preferred_is_not_a_hard_reject(base_job, profile):
    signals, result = decision(
        posting(base_job, preferred_qualifications="Veterans preferred."),
        profile,
    )

    assert signals.special_program_type == VETERANS
    assert signals.special_program_required is False
    assert result.state == "ELIGIBLE"


def test_title_only_special_program_signal_requires_verification(base_job, profile):
    signals, result = decision(
        posting(
            base_job,
            title="Veteran Internship Program - Firmware Intern",
            description="Build embedded systems with the engineering team.",
        ),
        profile,
    )

    assert signals.title_signal is True
    assert signals.special_program_required is False
    assert result.state == "UNKNOWN"


def test_technical_score_cannot_override_special_program_failure(base_job, profile):
    job = posting(
        base_job,
        "Veterans only. Required: C, C++, Python, Linux, Git, firmware, FPGA, Verilog, robotics, controls and testing.",
    )
    result = analyze_job(job, profile)

    assert result.technical_score >= 80
    assert result.special_program_eligibility_status == "NOT_ELIGIBLE"
    assert result.recommendation == "Not Eligible"
    assert result.effective_score <= 5


def test_target_company_bonus_cannot_override_special_program_failure(base_job, profile):
    result = analyze_job(
        posting(
            base_job,
            "This internship is limited to veterans.",
            is_target_company=True,
            company_priority_bonus=100,
        ),
        profile,
    )

    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.recommendation == "Not Eligible"
    assert result.effective_score <= 5


def test_special_program_rejection_is_hidden_by_default_but_retained():
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            profile = db.scalar(select(UserProfile).limit(1))
            job = Job(
                source_name="special-program-test",
                source_url="https://example.com/special-program-test",
                external_id="special-program-test-1",
                company="Example Special Program",
                title="Veterans Only Firmware Internship",
                location="Mexico",
                country="Mexico",
                description="Embedded firmware internship.",
                requirements="Applicants must be veterans.",
                apply_url="https://example.com/special-program-test/apply",
                official_status="open",
                verification_status="verified",
                status="active",
                is_active=True,
                first_seen_at=datetime.now(timezone.utc),
                raw_data_hash="special-program-test-1",
                raw_data={},
            )
            db.add(job)
            db.flush()
            persist_analysis(db, job, profile)
            db.commit()
            job_id = job.id

        default_ids = {
            item["id"]
            for item in client.get("/api/jobs", params={"page_size": 100}).json()["items"]
        }
        ineligible_ids = {
            item["id"]
            for item in client.get(
                "/api/jobs",
                params={"recommendation": "Not Eligible", "page_size": 100},
            ).json()["items"]
        }
        with SessionLocal() as db:
            assert db.get(Job, job_id) is not None

        assert job_id not in default_ids
        assert job_id in ineligible_ids


def test_restricted_program_does_not_use_priority_capacity_and_is_deduplicated(base_job, profile):
    job = posting(
        base_job,
        "Applicants must be veterans.",
        external_id="restricted-42",
        source_name="official",
        apply_url="https://example.com/jobs/restricted-42",
        discovery_status="discovered",
        status="active",
        area="Firmware / Embedded",
        first_seen_at=datetime.now(timezone.utc),
    )
    result = analyze_job(job, profile)

    assert qualifies_priority_alert(job, profile, result.to_dict()) is False
    assert find_duplicate([job], dict(job)) is job


def test_existing_work_authorization_gate_remains_active(base_job, profile):
    result = analyze_job(
        posting(
            base_job,
            "Currently pursuing a Bachelor's degree.",
            country="United States",
            location="California, United States",
            physical_work_country_required="United States",
            job_requires_work_in_us=True,
            sponsorship_status="NOT_AVAILABLE",
            description="Work in California. No visa sponsorship is available.",
        ),
        profile,
    )

    assert result.special_program_eligibility_status == "ELIGIBLE"
    assert result.eligibility_status == "NOT_ELIGIBLE"


def test_unknown_returnship_membership_is_not_inferred(base_job, profile):
    signals, result = decision(
        posting(
            base_job,
            "Applicants must be returning professionals after an extended career break.",
            title="Engineering Returnship",
        ),
        profile,
    )

    assert signals.special_program_type == RETURN_TO_WORK_PROGRAM
    assert signals.special_program_required is True
    assert result.state == "UNKNOWN"
