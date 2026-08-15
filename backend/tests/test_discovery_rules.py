from copy import deepcopy
from datetime import datetime, timedelta, timezone

from app.services.classification import (
    classify_remote,
    location_allowed,
    qualifies_priority_alert,
    urgency_label,
)
from app.services.scoring import analyze_job
from app.services.verification import _looks_like_general_careers
from app.sources.embedded_jobs import EmbeddedJobsAdapter


def test_onsite_job_in_germany_is_ignored(profile, base_job):
    job = deepcopy(base_job)
    job.update({"country": "Germany", "location": "Munich, Germany", "remote_type": "On-site"})
    allowed, _ = location_allowed(job, profile)
    assert not allowed


def test_worldwide_remote_job_can_be_shown(profile, base_job):
    remote = classify_remote("Berlin, Germany", "This is remote worldwide. Work from anywhere.")
    job = {
        **base_job,
        "country": "Germany",
        "remote_type": remote.remote_type,
        "remote_from_mexico_allowed": remote.remote_from_mexico_allowed,
    }
    allowed, _ = location_allowed(job, profile)
    assert allowed
    assert remote.remote_type == "Remote from Mexico"


def test_us_remote_only_is_not_remote_from_mexico():
    remote = classify_remote("Remote", "US remote only. Must be located in the United States.")
    assert remote.remote_type == "Remote - United States only"
    assert not remote.remote_from_mexico_allowed


def test_remote_without_clear_restrictions_stays_in_review(profile, base_job):
    job = deepcopy(base_job)
    job.update(
        {
            "country": "United States",
            "location": "Remote",
            "remote_type": "Remote - Location Restrictions Unknown",
            "remote_from_mexico_allowed": False,
        }
    )
    result = analyze_job(job, profile)
    assert result.recommendation == "Review"
    assert any("restrictions" in risk.lower() for risk in result.risk_flags)


def test_mexico_job_is_allowed_when_selected(profile, base_job):
    allowed, _ = location_allowed(base_job, profile)
    assert allowed


def test_canada_job_is_hidden_when_canada_not_selected(profile, base_job):
    restricted_profile = {**profile, "countries_to_search": ["Mexico", "United States"]}
    job = {**base_job, "country": "Canada", "location": "Toronto, Canada", "remote_type": "On-site"}
    allowed, _ = location_allowed(job, restricted_profile)
    assert not allowed


def test_expired_job_is_closed(profile, base_job):
    job = deepcopy(base_job)
    job["expires_at"] = "2026-06-01T00:00:00Z"
    assert analyze_job(job, profile).recommendation == "Closed"


def test_unconfirmed_external_listing_needs_verification(profile, base_job):
    job = deepcopy(base_job)
    job.update(
        {
            "source_name": "EmbeddedJobs",
            "official_status": "unknown",
            "verification_status": "unverified",
        }
    )
    assert analyze_job(job, profile).recommendation == "Needs Verification"


def test_verified_official_job_can_apply_today(profile, base_job):
    result = analyze_job(base_job, profile)
    assert result.recommendation == "Apply Today"


def test_major_company_high_score_activates_priority(profile, base_job):
    job = {
        **base_job,
        "company": "NVIDIA",
        "company_importance": "Major company",
        "first_seen_at": datetime.now(timezone.utc),
    }
    analysis = {
        "overall_score": 75,
        "freshness_score": 90,
        "level_score": 100,
        "blocker_reasons": [],
    }
    assert qualifies_priority_alert(job, profile, analysis)


def test_major_company_with_citizenship_blocker_is_not_eligible(profile, base_job):
    job = deepcopy(base_job)
    job.update(
        {
            "company": "SpaceX",
            "company_importance": "Major company",
            "country": "United States",
            "location": "Hawthorne, California, United States",
            "requirements": "Must be a U.S. citizen. Required: embedded C.",
        }
    )
    assert analyze_job(job, profile).recommendation == "Not Eligible"


def test_embedded_jobs_uses_official_application_url():
    adapter = EmbeddedJobsAdapter("EmbeddedJobs", "internships", "https://embedded.jobs")
    raw = {
        "external_id": "firmware-intern-123",
        "title": "Firmware Intern",
        "company": "Example Semiconductor",
        "location": "Austin, United States",
        "description": "Embedded C internship",
        "employment_type": "Internship",
        "embedded_url": "https://embedded.jobs/job/firmware-intern-123",
        "official_apply_url": "https://boards.greenhouse.io/example/jobs/123",
        "official_status": "open",
        "verification_status": "verified",
    }
    normalized = adapter.normalize_job(raw)
    assert normalized.apply_url == raw["official_apply_url"]
    assert normalized.original_source_url == raw["embedded_url"]


def test_general_careers_redirect_is_not_an_open_job():
    assert _looks_like_general_careers("https://company.example/careers", False, False)
    assert not _looks_like_general_careers("https://company.example/jobs/123", True, True)


def test_deadline_within_72_hours_is_urgent(base_job):
    job = {
        **base_job,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=48),
    }
    assert urgency_label(job) == "Urgent"


def test_recycled_posting_has_lower_freshness(profile, base_job):
    current = analyze_job(base_job, profile)
    recycled = deepcopy(base_job)
    recycled["title"] = "Firmware Intern - Summer 2025"
    recycled_result = analyze_job(recycled, profile)
    assert recycled_result.freshness_score < current.freshness_score
    assert recycled_result.recommendation != "Apply Today"
