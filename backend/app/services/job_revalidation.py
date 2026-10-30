"""Periodic official-posting revalidation for saved job records.

This deliberately reuses the canonical job verification facts instead of
introducing another lifecycle or status model.  A recheck only follows a stored
official URL; community and other third-party discovery URLs are never used as
evidence that an application remains open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.services.verification import VerificationResult, is_plausible_official_url


TERMINAL_OFFICIAL_STATUSES = frozenset({"closed", "expired", "unavailable"})
ACTIVE_LIFECYCLE_STATUSES = frozenset({"active", "saved"})


@dataclass(frozen=True)
class RevalidationOutcome:
    state: str
    reason: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def official_revalidation_url(job: Any) -> str:
    """Return only a stored official-company/ATS URL, never a discovery board."""
    for field in ("official_apply_url", "canonical_official_url", "posting_url"):
        value = str(getattr(job, field, "") or "").strip()
        if value and is_plausible_official_url(value):
            return value
    return ""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _deadline_near(job: Any, now: datetime, window_hours: int) -> bool:
    deadline = getattr(job, "application_deadline", None) or getattr(job, "expires_at", None)
    if isinstance(deadline, datetime):
        deadline_at = _as_utc(deadline)
        return bool(deadline_at and deadline_at <= now + timedelta(hours=window_hours))
    if isinstance(deadline, date):
        return deadline <= (now + timedelta(hours=window_hours)).date()
    return False


def is_revalidation_due(
    job: Any,
    *,
    now: datetime | None = None,
    interval_hours: int = 24,
    retry_minutes: int = 30,
    deadline_window_hours: int = 72,
    force: bool = False,
) -> bool:
    """Avoid excess traffic while retrying uncertain availability more quickly."""
    if force:
        return True
    if str(getattr(job, "status", "")) not in ACTIVE_LIFECYCLE_STATUSES:
        return False
    current = now or utc_now()
    checked_at = _as_utc(getattr(job, "last_checked_at", None))
    if checked_at is None:
        return True
    verification = str(getattr(job, "verification_status", "") or "")
    if verification in {"verification_failed", "partially_verified", "unverified"}:
        return checked_at <= current - timedelta(minutes=retry_minutes)
    if _deadline_near(job, current, deadline_window_hours):
        return checked_at <= current - timedelta(hours=min(6, interval_hours))
    return checked_at <= current - timedelta(hours=interval_hours)


def _record_open(job: Any, result: VerificationResult) -> RevalidationOutcome:
    _preserve_url_snapshot(job, result.last_verified_at)
    job.official_status = "open"
    job.verification_status = "verified"
    job.verification_method = result.verification_method
    job.status_reason = result.status_reason
    job.last_verified_at = result.last_verified_at
    job.application_url_last_verified_at = result.last_verified_at
    job.application_url_status = "VERIFIED"
    job.application_url_diagnostic = ""
    job.verification_failures = 0
    if result.official_apply_url:
        # apply_url remains the original discovered link for audit/history.
        job.official_apply_url = result.official_apply_url
        job.application_url = result.official_apply_url
    return RevalidationOutcome("open", result.status_reason)


def _record_terminal(job: Any, result: VerificationResult) -> RevalidationOutcome:
    _preserve_url_snapshot(job, result.last_verified_at)
    job.official_status = result.official_status
    job.verification_status = "verified"
    job.verification_method = result.verification_method
    job.status_reason = result.status_reason
    job.last_verified_at = result.last_verified_at
    job.application_url_last_verified_at = result.last_verified_at
    job.application_url_status = "INACTIVE"
    job.application_url_diagnostic = "APPLICATION_URL_INACTIVE"
    job.verification_failures = 0
    if result.official_apply_url:
        job.official_apply_url = result.official_apply_url
        job.application_url = result.official_apply_url
    if str(getattr(job, "status", "")) in ACTIVE_LIFECYCLE_STATUSES:
        job.status = "expired"
        job.expired_at = result.last_verified_at
        job.is_active = False
    return RevalidationOutcome("expired", result.status_reason)


def _record_unknown(job: Any, result: VerificationResult) -> RevalidationOutcome:
    # Do not turn uncertainty (including a timeout/429/403) into expiration.
    job.official_status = "unknown"
    job.verification_status = result.verification_status
    job.verification_method = result.verification_method
    job.status_reason = f"Needs Verification: {result.status_reason}"
    job.application_url_status = "MISSING" if not official_revalidation_url(job) else "UNKNOWN"
    job.application_url_diagnostic = (
        "APPLICATION_URL_NOT_FOUND"
        if job.application_url_status == "MISSING"
        else "APPLICATION_URL_RECHECK_PENDING"
    )
    job.verification_failures = int(getattr(job, "verification_failures", 0) or 0) + 1
    return RevalidationOutcome("needs_verification", result.status_reason)


def _preserve_url_snapshot(job: Any, checked_at: datetime) -> None:
    """Keep old resolved links auditable when an official portal redirects us."""
    raw_data = dict(getattr(job, "raw_data", None) or {})
    previous_url = str(getattr(job, "application_url", "") or "").strip()
    previous_official = str(getattr(job, "official_apply_url", "") or "").strip()
    if not previous_url and not previous_official:
        return
    history = list(raw_data.get("_radar_revalidation_history") or [])
    snapshot = {
        "checked_at": checked_at.isoformat(),
        "application_url": previous_url,
        "official_apply_url": previous_official,
        "application_url_status": str(getattr(job, "application_url_status", "") or ""),
    }
    if not history or history[-1] != snapshot:
        history.append(snapshot)
    raw_data["_radar_revalidation_history"] = history[-10:]
    job.raw_data = raw_data


async def revalidate_job(
    job: Any,
    verifier: Callable[[str, str, str | None, datetime | None], Awaitable[VerificationResult]],
    *,
    now: datetime | None = None,
) -> RevalidationOutcome:
    """Revalidate one stored job using its official posting/application URL."""
    current = now or utc_now()
    job.last_checked_at = current
    deadline = getattr(job, "application_deadline", None)
    confidence = float(getattr(job, "deadline_confidence", 0) or 0)
    if isinstance(deadline, date) and deadline < current.date() and confidence >= 0.8:
        expired = VerificationResult(
            "expired", "verified", "structured_deadline",
            "The official or structured application deadline has passed.",
            official_revalidation_url(job) or None, current,
        )
        return _record_terminal(job, expired)
    url = official_revalidation_url(job)
    if not url:
        missing = VerificationResult(
            "unknown", "verification_failed", "official_url_missing",
            "No stored official company or ATS URL is available for revalidation.",
            None, current,
        )
        return _record_unknown(job, missing)

    result = await verifier(
        url,
        str(getattr(job, "title", "") or ""),
        getattr(job, "external_id", None),
        getattr(job, "expires_at", None),
    )
    if result.official_status == "open" and result.verification_status == "verified":
        return _record_open(job, result)
    if result.official_status in TERMINAL_OFFICIAL_STATUSES:
        return _record_terminal(job, result)
    return _record_unknown(job, result)
