from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.classification import qualifies_priority_alert
from app.services.email_service import _eligible_for_email
from app.services.scoring import UNIVERSITY_BLOCKER_REASON, analyze_job, university_eligibility


def with_requirements(base_job, text, *, country=None, location=None):
    job = deepcopy(base_job)
    job["requirements"] = text
    if country:
        job["country"] = country
    if location:
        job["location"] = location
    return job


@pytest.mark.parametrize(
    "requirement",
    [
        "Currently enrolled at an accredited university.",
        "Must return to university after the internship.",
    ],
)
def test_generic_university_requirements_are_acceptable(profile, base_job, requirement):
    result = analyze_job(with_requirements(base_job, requirement), profile)
    assert result.recommendation != "Not Eligible"
    assert UNIVERSITY_BLOCKER_REASON not in result.blocker_reasons


@pytest.mark.parametrize(
    "requirement",
    [
        "Currently enrolled at an accredited U.S. university.",
        "Must attend a university in Canada.",
        "UIUC students only.",
        "Must be enrolled in the company's approved co-op university program.",
    ],
)
def test_country_or_institution_restriction_is_not_eligible(
    profile, base_job, requirement
):
    job = with_requirements(
        base_job,
        requirement,
        country="United States",
        location="California, United States",
    )
    result = analyze_job(job, profile)
    assert result.recommendation == "Not Eligible"
    assert UNIVERSITY_BLOCKER_REASON in result.blocker_reasons


@pytest.mark.parametrize(
    ("country", "location"),
    [
        ("United States", "California, United States"),
        ("Canada", "Toronto, Canada"),
    ],
)
def test_foreign_job_accepting_any_university_is_review_or_apply_today(
    profile, base_job, country, location
):
    job = with_requirements(
        base_job,
        "Currently enrolled at an accredited university.",
        country=country,
        location=location,
    )
    result = analyze_job(job, profile)
    assert result.recommendation in {"Review", "Apply Today"}
    assert result.recommendation != "Not Eligible"
    assert result.blocker_reasons == []


def test_mexico_job_accepts_tecnologico_de_monterrey_student(profile, base_job):
    job = with_requirements(
        base_job,
        "Currently pursuing a Bachelor's degree at an accredited institution.",
    )
    result = analyze_job(job, profile)
    assert result.recommendation != "Not Eligible"
    assert result.blocker_reasons == []


def test_participating_us_universities_only_is_not_eligible(profile, base_job):
    job = with_requirements(
        base_job,
        "Students from participating U.S. universities only.",
        country="United States",
        location="Austin, Texas, United States",
    )
    result = analyze_job(job, profile)
    assert result.recommendation == "Not Eligible"
    assert UNIVERSITY_BLOCKER_REASON in result.blocker_reasons


def test_university_blocker_excludes_priority_alerts_and_email(profile, base_job):
    job = with_requirements(
        base_job,
        "Must attend a U.S.-based university.",
        country="United States",
        location="Seattle, Washington, United States",
    )
    job.update(
        {
            "discovery_status": "discovered",
            "official_apply_url": "https://example.com/jobs/123",
        }
    )
    result = analyze_job(job, profile)

    assert result.recommendation == "Not Eligible"
    assert not qualifies_priority_alert(job, profile, result)

    email_job = SimpleNamespace(**job, apply_url=job["official_apply_url"])
    email_analysis = SimpleNamespace(**result.to_dict())
    assert not _eligible_for_email(email_job, email_analysis, minimum_score=0)


def test_university_and_work_authorization_are_evaluated_separately(profile, base_job):
    university_status, blocker = university_eligibility(
        "Currently enrolled at an accredited university."
    )
    job = with_requirements(
        base_job,
        "Currently enrolled at an accredited university.",
        country="United States",
        location="California, United States",
    )
    result = analyze_job(job, profile)

    assert university_status == "Eligible"
    assert blocker is None
    assert result.blocker_reasons == []
    assert result.recommendation == "Review"
    assert any(
        "sponsorship" in risk.lower() or "work authorization" in risk.lower()
        for risk in result.risk_flags
    )
