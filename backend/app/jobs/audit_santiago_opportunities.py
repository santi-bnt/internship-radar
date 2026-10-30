"""Auditable, evidence-first reconciliation for Santiago's requested jobs.

The manifest records what Santiago asked us to investigate; it is not a job
feed and never creates a posting merely because it appears here.  A caller can
only persist a ``NormalizedJob`` after its official source has verified that it
is open.  This module provides the common canonical lookup used before that
write so rediscovery from LinkedIn, an ATS, or an employer page reuses the same
candidate-owned record and preserves application history.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select

from app.core.config import settings
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import Job, UserProfile
from app.services.dedupe import find_duplicate
from app.services.target_companies import canonicalize_url
from app.sources.google_careers import GOOGLE_SEARCH_URL
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.smartrecruiters import SmartRecruitersAdapter
from app.sources.workday import WorkdayAdapter


@dataclass(frozen=True)
class AuditTarget:
    company: str
    title: str
    location: str
    external_id: str = ""
    official_url: str = ""
    category: str = ""


# These are audit references, not permission to invent records.  Entries with
# no official URL/ID deliberately remain report-only until an official source
# provides a concrete, currently open requisition.
SANTIAGO_AUDIT_TARGETS: tuple[AuditTarget, ...] = ()


@dataclass(frozen=True)
class AuditFinding:
    target: AuditTarget
    result: str
    job_id: int | None
    match_key: str = ""


@dataclass(frozen=True)
class OfficialCollectionResult:
    """Officially verified audit records plus non-destructive source failures."""

    jobs: tuple[Any, ...]
    source_failures: tuple[str, ...]


def _official_target_ids(company: str) -> set[str]:
    return {
        target.external_id
        for target in SANTIAGO_AUDIT_TARGETS
        if target.company.casefold() == company.casefold() and target.external_id
    }


def select_official_audit_jobs(jobs: Iterable[Any]) -> list[Any]:
    """Keep only exact, currently-open requisitions from official collectors.

    The manifest has intentionally broad references (for example, a Microsoft
    research program without an exact requisition).  Those references must not
    turn a broad search result into an invented candidate job.  An exact
    company + requisition ID is required for the automatic import path.
    """
    selected: list[Any] = []
    for job in jobs:
        if (
            str(getattr(job, "official_status", "")).casefold() != "open"
            or str(getattr(job, "verification_status", "")).casefold() != "verified"
        ):
            continue
        if str(getattr(job, "external_id", "") or "") not in _official_target_ids(
            str(getattr(job, "company", "")),
        ):
            continue
        selected.append(job)
    return selected


async def collect_official_audit_jobs() -> OfficialCollectionResult:
    """Collect the exact audit IDs through their existing official adapters.

    A temporary source/network failure is returned as a report item rather
    than being treated as a closed vacancy.  Callers may persist only the
    returned open + verified records through :func:`upsert_verified_audit_jobs`.
    """
    google = OfficialCareersAdapter(
        "Google", "google", GOOGLE_SEARCH_URL,
        search_criteria={"required_external_ids": sorted(_official_target_ids("Google"))},
    )
    solidigm = SmartRecruitersAdapter(
        "Solidigm", "Solidigm", "https://jobs.smartrecruiters.com/Solidigm",
    )
    micron = WorkdayAdapter(
        "Micron", "micron|External", "https://micron.wd1.myworkdayjobs.com/External",
    )
    collectors = {
        "Google": google.collect(),
        "Solidigm": solidigm.fetch_exact_ids(_official_target_ids("Solidigm"), require_all=False),
        "Micron": micron.fetch_exact_public_ids(_official_target_ids("Micron"), require_all=False),
    }
    results = await asyncio.gather(*collectors.values(), return_exceptions=True)
    normalized: list[Any] = []
    failures: list[str] = []
    for source_name, result in zip(collectors, results):
        if isinstance(result, Exception):
            failures.append(f"{source_name}: {type(result).__name__}: {result}")
            continue
        if source_name == "Micron":
            normalized.extend(micron.normalize_job(raw) for raw in result)
        elif source_name == "Solidigm":
            normalized.extend(solidigm.normalize_job(raw) for raw in result)
        else:
            normalized.extend(result)
    return OfficialCollectionResult(
        jobs=tuple(select_official_audit_jobs(normalized)),
        source_failures=tuple(failures),
    )


def _urls(job: Job) -> set[str]:
    return {
        canonicalize_url(str(getattr(job, field, "") or ""))
        for field in (
            "canonical_official_url", "official_apply_url", "application_url",
            "apply_url", "posting_url", "original_source_url", "source_url",
        )
        if str(getattr(job, field, "") or "")
    }


def locate_canonical_job(db: Any, owner_user_id: str, target: AuditTarget) -> tuple[Job | None, str]:
    """Find an existing candidate record using the requested identity order."""
    jobs = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    external_id = target.external_id.strip()
    if external_id:
        for job in jobs:
            if str(job.external_id or "") == external_id or str(job.ats_requisition_id or "") == external_id:
                if job.company.casefold() == target.company.casefold():
                    return job, "official_job_id"
    official_url = canonicalize_url(target.official_url)
    if official_url:
        for job in jobs:
            if official_url in _urls(job):
                return job, "canonical_url"
    candidate = {
        "company": target.company,
        "title": target.title,
        "location": target.location,
        "external_id": external_id,
    }
    duplicate = find_duplicate(jobs, candidate)
    return (duplicate, "company_title_location") if duplicate else (None, "")


def audit_existing_targets(db: Any, owner_user_id: str) -> list[AuditFinding]:
    """Read-only audit: report existing canonical records without creating jobs."""
    findings: list[AuditFinding] = []
    for target in SANTIAGO_AUDIT_TARGETS:
        job, match_key = locate_canonical_job(db, owner_user_id, target)
        if job is None:
            findings.append(AuditFinding(target, "NOT_IMPORTED_UNVERIFIABLE", None))
            continue
        if str(job.official_status or "").casefold() in {"closed", "expired", "unavailable"}:
            result = "CLOSED_OR_EXPIRED"
        elif str(job.verification_status or "").casefold() == "verified":
            result = "ALREADY_EXISTS_VERIFIED"
        else:
            result = "ALREADY_EXISTS_NEEDS_VERIFICATION"
        findings.append(AuditFinding(target, result, job.id, match_key))
    return findings


def upsert_verified_audit_jobs(db: Any, owner_user_id: str, jobs: Iterable[Any]) -> list[Job]:
    """Safely persist only official, currently open audit results.

    The function deliberately has no Force Apply behavior.  It preserves an
    existing Applied state, resume versions, notes, and overrides through the
    shared duplicate merge path.
    """
    if owner_user_id != settings.effective_primary_user_id:
        raise PermissionError("This requested-opportunity audit is restricted to Santiago's profile.")
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise RuntimeError("Santiago's candidate profile is required before auditing jobs.")
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    persisted: list[Job] = []
    for normalized in jobs:
        if normalized.official_status != "open" or normalized.verification_status != "verified":
            continue
        data = normalized.to_dict()
        data["owner_user_id"] = owner_user_id
        job = next((item for item in existing if (
            item.company.casefold() == normalized.company.casefold()
            and str(item.external_id or "") == str(normalized.external_id or "")
            and str(normalized.external_id or "")
        )), None)
        if job is None:
            job = find_duplicate(existing, data)
        if job is None:
            job = Job(**data)
            db.add(job)
            db.flush()
            existing.append(job)
        else:
            _merge_duplicate(job, data)
        persist_analysis(db, job, profile)
        persisted.append(job)
    db.commit()
    return persisted
