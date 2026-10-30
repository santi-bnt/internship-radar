"""Candidate-owned, deliberately manual application-action overrides."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
import unicodedata

from sqlalchemy import select


TERMINAL_OFFICIAL_STATUSES = frozenset({"closed", "expired", "unavailable"})
INACTIVE_APPLICATION_STATUSES = frozenset({"INACTIVE", "UNAVAILABLE", "EXPIRED"})
ACTIVE_JOB_STATUSES = frozenset({"active", "saved"})


@dataclass(frozen=True)
class ForceApplyTarget:
    """A user-requested action override, never a job-discovery substitute."""

    company_names: tuple[str, ...]
    title: str
    location: str
    external_ids: tuple[str, ...] = ()


# These are deliberately explicit user action choices, rather than job
# templates.  A target can only enable an override for an already-discovered,
# officially active job record.  It cannot create a posting, infer an apply URL,
# or change a job analysis.
SANTIAGO_FORCE_APPLY_TARGETS: tuple[ForceApplyTarget, ...] = ()


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    # Normalize ATS punctuation, accents, and previously imported mojibake so
    # an explicit user-selected role is not missed because one source renders
    # "IngenierÃ­a" while another renders "Ingeniería".
    return " ".join("".join(
        char for char in text.casefold()
        if (char.isalnum() or char.isspace()) and not unicodedata.combining(char)
    ).split())


def _company_matches(company: str, names: tuple[str, ...]) -> bool:
    """Accept a safe legal-suffix variant, for example Jabil Inc."""
    company_tokens = set(company.split())
    for name in names:
        target_tokens = set(_normalized(name).split())
        if target_tokens and (
            company_tokens == target_tokens
            or target_tokens.issubset(company_tokens)
            or company_tokens.issubset(target_tokens)
        ):
            return True
    return False


def _title_matches(title: str, target_title: str) -> bool:
    """Match harmless ATS punctuation/encoding variations, not new roles."""
    if title == target_title or title in target_title or target_title in title:
        return True
    # Company and location remain exact-scoped below. This only absorbs a
    # one-character encoding difference such as "Ingenier�a" vs "Ingeniería".
    return SequenceMatcher(None, title, target_title).ratio() >= 0.97


def requested_force_apply_target(job: Any) -> ForceApplyTarget | None:
    """Match an existing job by official ID first, then exact candidate data."""
    job_ids = {
        _normalized(getattr(job, field, ""))
        for field in ("external_id", "ats_requisition_id")
    }
    company = _normalized(getattr(job, "company", ""))
    title = _normalized(getattr(job, "title", ""))
    location = _normalized(getattr(job, "location", ""))
    for target in SANTIAGO_FORCE_APPLY_TARGETS:
        target_ids = {_normalized(value) for value in target.external_ids}
        if target_ids and job_ids.intersection(target_ids):
            return target
        if (
            _company_matches(company, target.company_names)
            and _title_matches(title, _normalized(target.title))
            and _normalized(target.location) in location
        ):
            return target
    return None


def apply_requested_santiago_overrides(
    db: Any,
    owner_user_id: str,
    *,
    commit: bool = True,
) -> list[Any]:
    """Enable matching records with a usable application link for Santiago.

    A low score or temporary verification failure never defeats an explicit
    candidate action. Only confirmed closure/expiration, or the absence of an
    application URL, blocks it.
    """
    from app.models import CandidateJobOverride, Job

    enabled: list[Any] = []
    jobs = db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)).all()
    for job in jobs:
        # An application is a candidate-owned historical state. A later source
        # refresh or manual-override reconciliation may update official facts,
        # but it must never turn an applied opportunity back into Apply Now.
        if str(job.status or "").casefold() == "applied":
            continue
        if not requested_force_apply_target(job) or not can_force_apply_now(job):
            continue
        # This explicit candidate action revives a stale/unknown archive so it
        # is visible in the normal Active list. Confirmed closures were already
        # excluded by can_force_apply_now above.
        if str(job.status or "").lower() not in ACTIVE_JOB_STATUSES or not job.is_active:
            job.status = "active"
            job.is_active = True
            job.archived_at = None
            job.expired_at = None
        override = db.scalar(select(CandidateJobOverride).where(
            CandidateJobOverride.owner_user_id == owner_user_id,
            CandidateJobOverride.job_id == job.id,
        ))
        if override is None:
            override = CandidateJobOverride(owner_user_id=owner_user_id, job_id=job.id)
            db.add(override)
        if not override.force_apply_now:
            set_force_apply_now(override, True)
            enabled.append(job)
    if enabled:
        if commit:
            db.commit()
        else:
            db.flush()
    return enabled


def is_application_confirmed_unavailable(job: Any) -> bool:
    """Return true only for a confirmed terminal posting/application state."""
    return (
        str(getattr(job, "status", "") or "").lower() == "expired"
        or str(getattr(job, "official_status", "") or "").lower() in TERMINAL_OFFICIAL_STATUSES
        or str(getattr(job, "application_url_status", "") or "").upper()
        in INACTIVE_APPLICATION_STATUSES
    )


def can_force_apply_now(job: Any) -> bool:
    """Manual overrides ignore score/verification but never a known dead link."""
    return (
        not is_application_confirmed_unavailable(job)
        and bool(
            getattr(job, "official_apply_url", "")
            or getattr(job, "application_url", "")
            or getattr(job, "apply_url", "")
        )
    )


def force_apply_action_is_active(job: Any) -> bool:
    """An enabled override only changes the displayed action while still safe."""
    return (
        str(getattr(job, "status", "") or "").casefold() != "applied"
        and bool(getattr(job, "force_apply_now", False))
        and can_force_apply_now(job)
    )


def set_force_apply_now(override: Any, enabled: bool) -> None:
    """Update the manual action without touching any eligibility evidence."""
    now = datetime.now(timezone.utc)
    override.force_apply_now = enabled
    if enabled:
        override.enabled_at = now
        override.disabled_at = None
    else:
        override.disabled_at = now
