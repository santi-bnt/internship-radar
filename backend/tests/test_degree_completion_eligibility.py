from __future__ import annotations

from copy import deepcopy

from app.services.education_eligibility import (
    COMPLETED_REQUIRED,
    IN_PROGRESS_ALLOWED,
    UNKNOWN,
    evaluate_degree_eligibility,
    extract_degree_requirements,
)
from app.services.scoring import analyze_job


def posting(base_job, requirements: str, **overrides):
    job = deepcopy(base_job)
    job.update(
        {
            "requirements": requirements,
            "preferred_qualifications": "",
            "description": "Engineering opportunity.",
        }
    )
    job.update(overrides)
    return job


def education(job, profile):
    requirements = extract_degree_requirements(job)
    return requirements, evaluate_degree_eligibility(requirements, profile)


def test_completed_bachelors_required_rejects_degree_in_progress(base_job, profile):
    job = posting(base_job, "Must have a Bachelor's degree in Computer Engineering.")
    requirements, decision = education(job, profile)

    assert requirements.degree_completion_required == COMPLETED_REQUIRED
    assert decision.degree_completion_match == "NO_MATCH"
    assert decision.state == "NOT_ELIGIBLE"


def test_currently_pursuing_bachelors_is_eligible(base_job, profile):
    job = posting(base_job, "Currently pursuing a Bachelor's degree in Computer Engineering.")
    requirements, decision = education(job, profile)

    assert requirements.degree_completion_required == IN_PROGRESS_ALLOWED
    assert decision.degree_completion_match == "MATCH"
    assert decision.state == "ELIGIBLE"


def test_masters_or_phd_students_only_rejects_bachelors_student(base_job, profile):
    job = posting(base_job, "Currently pursuing a Master's or PhD in Computer Engineering. Students only.")
    _, decision = education(job, profile)

    assert decision.degree_level_match == "NO_MATCH"
    assert decision.state == "NOT_ELIGIBLE"


def test_bachelors_masters_or_phd_current_students_accepts_bachelors(base_job, profile):
    job = posting(
        base_job,
        "Currently pursuing a Bachelor's, Master's or PhD in Computer Science, Computer Engineering, or a related field.",
    )
    _, decision = education(job, profile)

    assert decision.degree_level_match == "MATCH"
    assert decision.degree_completion_match == "MATCH"
    assert decision.state == "ELIGIBLE"


def test_computer_engineering_matches_candidate_field(base_job, profile):
    job = posting(base_job, "Currently pursuing a Bachelor's degree in Computer Engineering.")
    _, decision = education(job, profile)

    assert decision.degree_field_match == "MATCH"


def test_field_match_does_not_override_completed_degree_requirement(base_job, profile):
    job = posting(
        base_job,
        "Minimum Qualifications: Bachelor's degree, Master or PhD in Computer Engineering, Electrical Engineering, or similar.",
        title="Software Engineer",
        employment_type="Full-time",
    )
    _, decision = education(job, profile)

    assert decision.degree_field_match == "MATCH"
    assert decision.degree_completion_match == "NO_MATCH"
    assert decision.state == "NOT_ELIGIBLE"


def test_wrong_mandatory_field_rejects_candidate(base_job, profile):
    job = posting(base_job, "Required qualifications: Bachelor's degree in Accounting or Finance.")
    _, decision = education(job, profile)

    assert decision.degree_field_match == "NO_MATCH"
    assert decision.state == "NOT_ELIGIBLE"


def test_related_engineering_field_allows_semantic_match(base_job, profile):
    job = posting(
        base_job,
        "Currently pursuing a Bachelor's degree in Electrical Engineering, Computer Engineering, or a related engineering field.",
    )
    _, decision = education(job, profile)

    assert decision.degree_field_match == "MATCH"
    assert decision.state == "ELIGIBLE"


def test_preferred_bachelors_does_not_create_hard_rejection(base_job, profile):
    job = posting(
        base_job,
        "Experience building embedded systems.",
        preferred_qualifications="Preferred qualifications: Bachelor's degree in Computer Science.",
    )
    requirements, decision = education(job, profile)

    assert requirements.degree_completion_required == UNKNOWN
    assert decision.state != "NOT_ELIGIBLE"
    assert decision.blockers == ()


def test_ambiguous_bachelors_is_unknown_not_rejected(base_job, profile):
    job = posting(base_job, "Education: Bachelor's degree in Computer Engineering or Computer Science.")
    requirements, decision = education(job, profile)

    assert requirements.degree_completion_required == UNKNOWN
    assert decision.degree_completion_match == "UNKNOWN"
    assert decision.state == "UNKNOWN"


def test_internship_enrollment_overrides_generic_degree_wording(base_job, profile):
    job = posting(
        base_job,
        "Bachelor's degree in Computer Science, Computer Engineering, or related field. Must remain enrolled and return to university after the internship.",
        title="Software Engineering Intern",
        employment_type="Internship",
    )
    requirements, decision = education(job, profile)

    assert requirements.degree_completion_required == IN_PROGRESS_ALLOWED
    assert decision.degree_completion_match == "MATCH"
    assert decision.student_status_match == "MATCH"
    assert decision.state == "ELIGIBLE"


def test_mandatory_graduation_window_before_demo_graduation_rejects(base_job, profile):
    job = posting(
        base_job,
        "Currently pursuing a Bachelor's in Computer Engineering. Graduation date between May 2026 and May 2027.",
    )
    _, decision = education(job, profile)

    assert decision.graduation_window_match == "NO_MATCH"
    assert decision.state == "NOT_ELIGIBLE"


def test_technical_score_cannot_override_education_failure(base_job, profile):
    job = posting(
        base_job,
        "Must have a Bachelor's degree in Computer Engineering. Required: C, C++, Python, Linux, Git, firmware, FPGA, Verilog, robotics, controls and testing.",
    )
    result = analyze_job(job, profile)

    assert result.technical_score >= 80
    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.recommendation == "Not Eligible"
    assert result.effective_score <= 5


def test_target_company_bonus_cannot_override_education_failure(base_job, profile):
    job = posting(
        base_job,
        "Bachelor's degree in Computer Engineering required.",
        is_target_company=True,
        company_priority_bonus=100,
    )
    result = analyze_job(job, profile)

    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.recommendation == "Not Eligible"
    assert result.effective_score <= 5


def test_existing_sponsorship_and_remote_gate_still_applies(base_job, profile):
    job = posting(
        base_job,
        "Currently pursuing a Bachelor's degree in Computer Engineering.",
        country="United States",
        location="California, United States",
        remote_type="Remote",
        remote_scope="US_ONLY",
        remote_countries_allowed=["United States"],
        remote_from_mexico_allowed=False,
        can_work_from_mexico="NO",
        physical_work_country_required="United States",
        job_requires_work_in_us=True,
        sponsorship_status="NOT_AVAILABLE",
        description="Remote in the U.S. only. No visa sponsorship is available.",
    )
    result = analyze_job(job, profile)

    assert result.education_eligibility_status == "ELIGIBLE"
    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.recommendation == "Not Eligible"
    assert result.effective_score <= 5
