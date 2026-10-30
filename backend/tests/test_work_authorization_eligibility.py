from copy import deepcopy

import pytest

from app.services.eligibility import (
    discovery_search_plan,
    evaluate_work_eligibility,
    extract_job_eligibility_signals,
)
from app.services.dedupe import find_duplicate
from app.services.scoring import analyze_job


def make_job(base_job, *, country="United States", location="Austin, Texas, United States", text=""):
    job = deepcopy(base_job)
    job.update({"country": country, "location": location, "remote_type": "On-site"})
    job["requirements"] = f"Required: C++, Python, Linux, embedded systems. {text}"
    return job


@pytest.mark.parametrize(
    ("country", "location", "text", "expected"),
    [
        ("United States", "Austin, Texas, United States", "We will not sponsor employment visas.", "NOT_ELIGIBLE"),
        ("United States", "Austin, Texas, United States", "This opportunity will not offer work authorization sponsorship. Interested candidates must be currently eligible to work in the US.", "NOT_ELIGIBLE"),
        ("United States", "Austin, Texas, United States", "Employment sponsorship is available.", "LIKELY_ELIGIBLE"),
        ("United States", "Austin, Texas, United States", "", "UNKNOWN"),
        ("Mexico", "Monterrey, Mexico", "", "ELIGIBLE"),
        ("Canada", "Toronto, Canada", "No employment sponsorship.", "NOT_ELIGIBLE"),
        ("Canada", "Toronto, Canada", "", "UNKNOWN"),
        ("United States", "Remote", "Remote worldwide. Work from anywhere.", "ELIGIBLE"),
        ("United States", "Remote", "Remote across Latin America.", "ELIGIBLE"),
        ("United States", "Remote", "Remote from Mexico.", "ELIGIBLE"),
        ("United States", "Remote", "US remote only. We will not sponsor.", "NOT_ELIGIBLE"),
        ("United States", "Remote", "This is a remote internship.", "UNKNOWN"),
        ("United States", "Remote", "Eligible countries: Mexico, Canada, and United States.", "ELIGIBLE"),
        ("United States", "Remote", "Global remote, excluding Mexico. We will not sponsor.", "NOT_ELIGIBLE"),
    ],
)
def test_work_eligibility_matrix(profile, base_job, country, location, text, expected):
    job = make_job(base_job, country=country, location=location, text=text)
    if "Remote" in location or "remote" in text.lower():
        job["remote_type"] = "Remote"
        job["description"] = text
    signals = extract_job_eligibility_signals(job)
    assert evaluate_work_eligibility(signals, profile).state == expected


def test_us_company_remote_from_mexico_does_not_require_us_authorization(profile, base_job):
    job = make_job(base_job, location="Remote", text="Remote from Mexico.")
    job.update({"company": "U.S. Company", "remote_type": "Remote", "description": "Remote from Mexico."})
    signals = extract_job_eligibility_signals(job)
    assert signals.physical_work_country_required == "Mexico"
    assert signals.job_requires_work_in_us is False
    assert evaluate_work_eligibility(signals, profile).state == "ELIGIBLE"


def test_no_sponsorship_is_a_hard_gate_even_with_excellent_skills(profile, base_job):
    job = make_job(base_job, text="Must be authorized to work in the U.S. We will not sponsor.")
    result = analyze_job(job, profile)
    assert result.technical_score >= 70
    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.effective_score <= 5
    assert result.recommendation == "Not Eligible"
    assert any("U.S. work authorization required" in reason for reason in result.blocker_reasons)


def test_remote_eligible_bonus_requires_mexico_eligibility(profile, base_job):
    global_job = make_job(base_job, location="Remote", text="Remote worldwide. Work from anywhere.")
    global_job.update({"remote_type": "Remote", "description": "Remote worldwide. Work from anywhere."})
    unknown_job = {**global_job, "description": "Remote internship.", "requirements": "C++ and Python."}
    assert analyze_job(global_job, profile).remote_eligibility_bonus == 33
    assert analyze_job(unknown_job, profile).remote_eligibility_bonus == 0


def test_remote_relocation_bonus_component_is_removed(profile, base_job):
    job = make_job(base_job, location="Remote", text="Remote LATAM.")
    job.update({"remote_type": "Remote", "description": "Remote LATAM.", "relocation_required": True})
    assert analyze_job(job, profile).remote_eligibility_bonus == 25


def test_sponsorship_evidence_and_source_are_persistable(base_job):
    job = make_job(base_job, text="Our company will not sponsor employment visas.")
    job.update({"official_apply_url": "https://company.example/jobs/1", "verification_status": "verified"})
    signals = extract_job_eligibility_signals(job)
    assert signals.sponsorship_status == "NOT_AVAILABLE"
    assert "sponsor" in signals.sponsorship_evidence_text.lower()
    assert signals.sponsorship_source_url == "https://company.example/jobs/1"


def test_discovery_plan_always_reserves_remote_capacity():
    plan = discovery_search_plan()
    assert plan["allocation"] == {
        "mexico": 0.40,
        "eligible_remote": 0.30,
        "international_target_companies": 0.30,
    }
    assert len(plan["remote_queries"]) >= 10
    assert all("remote" in query.lower() for query in plan["remote_queries"])


def test_available_sponsorship_never_becomes_apply_today_without_review(profile, base_job):
    job = make_job(base_job, text="Employment sponsorship is available.")
    result = analyze_job(job, profile)
    assert result.eligibility_status == "LIKELY_ELIGIBLE"
    assert result.recommendation in {"Apply Today", "Review"}
    assert result.effective_score > 5


def test_us_hybrid_without_sponsorship_is_not_eligible(profile, base_job):
    job = make_job(base_job, text="No visa sponsorship now or in the future.")
    job["remote_type"] = "Hybrid"
    result = analyze_job(job, profile)
    assert result.eligibility_status == "NOT_ELIGIBLE"
    assert result.effective_score <= 5


def test_us_only_remote_never_receives_remote_bonus(profile, base_job):
    job = make_job(base_job, location="Remote", text="US remote only. Sponsorship is available.")
    job.update({"remote_type": "Remote", "description": "US remote only. Sponsorship is available."})
    result = analyze_job(job, profile)
    assert result.eligibility_status == "LIKELY_ELIGIBLE"
    assert result.remote_eligibility_bonus == 0


def test_applied_ineligible_job_is_found_as_existing_not_rediscovered(base_job):
    stored = {
        **base_job,
        "external_id": "existing-application-1",
        "source_name": "Official",
        "apply_url": "https://company.example/jobs/existing-application-1",
        "status": "applied",
        "eligibility_status": "NOT_ELIGIBLE",
    }
    candidate = {
        **stored,
        "status": "active",
        "eligibility_status": "UNKNOWN",
    }
    assert find_duplicate([stored], candidate) is stored
