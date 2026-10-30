"""Application-state rules for research internships.

This module deliberately does not calculate fit or eligibility scores.  It only
turns already-verified posting, application, deadline, and eligibility facts
into the application status shown to a candidate.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.services.normalization import clean_text, normalized_token


ACTIVE_APPLICATION_STATUSES = {"VERIFIED"}
INACTIVE_APPLICATION_STATUSES = {"INACTIVE", "UNAVAILABLE", "EXPIRED"}
TERMINAL_OFFICIAL_STATUSES = {"closed", "expired", "unavailable"}
ELIGIBLE_STATES = {"ELIGIBLE", "LIKELY_ELIGIBLE"}


def is_research_internship(job: Any) -> bool:
    title = normalized_token(clean_text(str(getattr(job, "title", ""))))
    employment = normalized_token(clean_text(str(getattr(job, "employment_type", ""))))
    combined = f"{title} {employment}"
    return "research" in combined and any(
        term in combined for term in ("intern", "internship", "co op", "student")
    )


def is_us_research_internship(job: Any) -> bool:
    if not is_research_internship(job):
        return False
    location = normalized_token(
        " ".join(
            str(getattr(job, field, ""))
            for field in ("country", "location", "region")
        )
    )
    return any(marker in location for marker in ("united states", "usa", "u s"))


def _deadline_passed(job: Any, now: datetime) -> bool:
    deadline = getattr(job, "application_deadline", None) or getattr(job, "expires_at", None)
    if isinstance(deadline, datetime):
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline < now
    if isinstance(deadline, date):
        return deadline < now.date()
    return False


def _has_verified_hard_blocker(analysis: Any) -> bool:
    return (
        str(getattr(analysis, "eligibility_status", "")) == "NOT_ELIGIBLE"
        or bool(getattr(analysis, "blocker_reasons", None))
    )


def _mark_expired(job: Any, analysis: Any, reason: str, now: datetime) -> None:
    if getattr(job, "status", "") in {"active", "saved"}:
        job.status = "expired"
        job.expired_at = now
    job.is_active = False
    analysis.recommendation = "Expired"
    existing_reason = clean_text(str(getattr(job, "status_reason", "")))
    job.status_reason = reason if not existing_reason else f"{existing_reason} {reason}"


def apply_research_application_status(
    job: Any,
    analysis: Any,
    *,
    now: datetime | None = None,
) -> str | None:
    """Apply verified Research-intern application rules without changing scores.

    Returns the explicit recommendation when a Research rule was applied, or
    ``None`` when a non-Research/non-US open role should retain normal handling.
    Expiration is recognized for any Research internship; the Apply Now shortcut
    is intentionally US-only.
    """
    if not is_research_internship(job):
        return None

    current = now or datetime.now(timezone.utc)
    official_status = str(getattr(job, "official_status", "unknown") or "unknown").lower()
    application_status = str(getattr(job, "application_url_status", "UNKNOWN") or "UNKNOWN").upper()

    if _deadline_passed(job, current):
        if official_status not in TERMINAL_OFFICIAL_STATUSES:
            job.official_status = "expired"
        _mark_expired(job, analysis, "Research internship deadline has passed.", current)
        return "Expired"
    if official_status in TERMINAL_OFFICIAL_STATUSES or application_status in INACTIVE_APPLICATION_STATUSES:
        _mark_expired(job, analysis, "The official Research application is no longer active.", current)
        return "Expired"

    application_url = (
        getattr(job, "official_apply_url", "")
        or getattr(job, "application_url", "")
        or getattr(job, "apply_url", "")
    )
    verified_open = (
        official_status == "open"
        and str(getattr(job, "verification_status", "")) == "verified"
        and application_status in ACTIVE_APPLICATION_STATUSES
        and bool(application_url)
    )

    # A non-US role can still be kept current or expired, but must never receive
    # the US Research "Apply Now" shortcut. Unknown availability is still shown
    # honestly rather than treated as an open application.
    if not is_us_research_internship(job):
        if not verified_open and not _has_verified_hard_blocker(analysis):
            analysis.recommendation = "Needs Verification"
            return "Needs Verification"
        return None

    if not verified_open:
        analysis.recommendation = "Needs Verification"
        return "Needs Verification"
    if _has_verified_hard_blocker(analysis):
        return None
    if str(getattr(analysis, "eligibility_status", "")) not in ELIGIBLE_STATES:
        return None

    analysis.recommendation = "Apply Now"
    return "Apply Now"
