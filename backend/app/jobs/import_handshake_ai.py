"""Import Santiago's requested Handshake AI Fellowship opportunity safely.

This is intentionally an exact, candidate-scoped importer rather than a new
general-purpose job source.  It verifies the supplied official application
URL before writing an open state and leaves every other candidate untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs.import_google import resolve_import_owner
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import CandidateJobOverride, Job, ResumeProfile, UserProfile
from app.services.dedupe import find_duplicate
from app.services.force_apply import set_force_apply_now
from app.services.normalization import clean_text, validate_public_url
from app.services.santiago_certifications import (
    SANTIAGO_VERIFIED_CERTIFICATIONS,
    ensure_santiago_verified_certifications,
)
from app.sources.official_careers import OfficialCareersAdapter


HANDSHAKE_JOB_ID = "11467525"
HANDSHAKE_URL = (
    "https://app.joinhandshake.com/signup?destination_hai_path=%2Fauth&hai_job_id=11467525"
)
HANDSHAKE_TITLE = "Spanish AI Evaluation Specialist (Mexico)"
HANDSHAKE_COMPANY = "Handshake AI"
HANDSHAKE_CERTIFICATION = SANTIAGO_VERIFIED_CERTIFICATIONS[0]

_CLOSED_MARKERS = (
    "job is no longer available", "no longer accepting applications",
    "position has been filled", "position is closed", "job has expired",
)


def build_handshake_ai_opportunity(
    *, verified_at: datetime | None = None, application_verified: bool = True,
    verification_reason: str = "",
):
    """Build the real role with its actual fellowship/contractor context."""
    verified_at = verified_at or datetime.now(timezone.utc)
    adapter = OfficialCareersAdapter(HANDSHAKE_COMPANY, "handshake_ai", HANDSHAKE_URL)
    job = adapter.build_job(
        {"external_id": HANDSHAKE_JOB_ID, "title": HANDSHAKE_TITLE},
        external_id=HANDSHAKE_JOB_ID,
        title=HANDSHAKE_TITLE,
        location="Remote, Mexico",
        country="Mexico",
        remote_type="Remote",
        employment_type="Part-time / Independent Contractor / Fellowship project",
        description=(
            "Handshake AI Fellowship project for Spanish-language AI response evaluation "
            "and annotation. The work is fully remote from Mexico, flexible, and "
            "project-based; English comprehension is used for instructions and training. "
            "No coding is required. This is contractor/fellowship work, not a traditional "
            "software engineering or embedded engineering internship and not full-time employment."
        ),
        requirements=(
            "Required: authorization to perform remote project work from Mexico; Spanish "
            "language proficiency; English comprehension for instructions and training; "
            "ability to evaluate and annotate AI responses. No coding requirement."
        ),
        preferred_qualifications="Experience evaluating language or AI responses is helpful but not required.",
        apply_url=HANDSHAKE_URL,
        original_source_url=HANDSHAKE_URL,
        official_apply_url=HANDSHAKE_URL,
        official_status="open" if application_verified else "unknown",
        verification_status="verified" if application_verified else "unverified",
        verification_method=("official_handshake_application" if application_verified else "official_handshake_application_pending"),
        status_reason=verification_reason or (
            "Official Handshake application entry point responded without a closure signal."
            if application_verified else
            "Official Handshake application availability could not be verified yet."
        ),
        last_verified_at=verified_at if application_verified else None,
        remote_from_mexico_allowed=True,
        discovered_from_source="handshake_ai_official",
        verified_from_source="handshake_ai_official",
        discovery_sources=["handshake_ai_official"],
        source_confidence_score=1.0,
        ats_requisition_id=HANDSHAKE_JOB_ID,
    )
    job.opportunity_type = "ai_fellowship"
    job.area = "AI Evaluation / Language Operations"
    job.raw_data.update({
        "handshake_job_id": HANDSHAKE_JOB_ID,
        "program": "Handshake AI Fellowship",
        "compensation": "Up to $25 USD/hour; may vary by project",
        "work_kind": "Part-time / Independent Contractor / Fellowship project",
        "no_coding_required": True,
    })
    return job


async def verify_handshake_application() -> tuple[bool, str]:
    """Verify a live official entry point without treating a login page as a job offer."""
    validate_public_url(HANDSHAKE_URL)
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(HANDSHAKE_URL)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return False, f"Official Handshake endpoint returned HTTP {exc.response.status_code}; application status needs verification."
    except httpx.HTTPError as exc:
        return False, f"Official Handshake endpoint could not be verified: {type(exc).__name__}."
    page_text = clean_text(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)).casefold()
    if any(marker in page_text for marker in _CLOSED_MARKERS):
        return False, "Official Handshake page indicates that the application is closed."
    # The URL is an enrollment handoff, so the job's title may not be exposed
    # until after login.  Keep this check limited to a successful Handshake
    # destination that still preserves the requested job id.
    final_url = str(response.url)
    if "joinhandshake.com" not in final_url or HANDSHAKE_JOB_ID not in final_url:
        return False, "Official Handshake page did not preserve the requested fellowship job identifier."
    return True, "Official Handshake application entry point is active."


def import_handshake_ai_opportunity(
    db, owner_user_id: str, *, verified_at: datetime | None = None,
    application_verified: bool = True, verification_reason: str = "",
) -> tuple[Job, bool]:
    """Upsert the opportunity and its evidence for the sole primary candidate."""
    if owner_user_id != settings.effective_primary_user_id:
        raise PermissionError("The Handshake AI import is restricted to Santiago's profile.")
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    resume_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == owner_user_id))
    if profile is None or resume_profile is None:
        raise RuntimeError("Santiago's candidate and resume profiles are required before import.")

    normalized = build_handshake_ai_opportunity(
        verified_at=verified_at, application_verified=application_verified,
        verification_reason=verification_reason,
    )
    data = normalized.to_dict()
    data["owner_user_id"] = owner_user_id
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    job = next((item for item in existing if (
        item.company.casefold() == HANDSHAKE_COMPANY.casefold()
        and str(item.external_id or "") == HANDSHAKE_JOB_ID
    )), None)
    if job is None:
        job = find_duplicate(existing, data)
    created = job is None
    if created:
        job = Job(**data)
        db.add(job)
        db.flush()
    else:
        _merge_duplicate(job, data)
    job.opportunity_type = "ai_fellowship"
    job.area = "AI Evaluation / Language Operations"
    job.status = "active"
    job.is_active = True
    job.archived_at = None
    job.expired_at = None
    persist_analysis(db, job, profile)
    ensure_santiago_verified_certifications(resume_profile)
    db.flush()
    # This candidate-specific action is only enabled after an official active
    # check.  It changes neither analysis nor eligibility; when verification
    # is pending, the normal Needs Verification state remains visible.
    override = db.scalar(select(CandidateJobOverride).where(
        CandidateJobOverride.owner_user_id == owner_user_id,
        CandidateJobOverride.job_id == job.id,
    ))
    if application_verified:
        if override is None:
            override = CandidateJobOverride(owner_user_id=owner_user_id, job_id=job.id)
            db.add(override)
        set_force_apply_now(override, True)
    elif override is not None:
        set_force_apply_now(override, False)
    db.commit()
    return job, created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    active, reason = asyncio.run(verify_handshake_application())
    print(reason)
    if not args.apply:
        print("No database changes were made.")
        return
    with SessionLocal() as db:
        owner = resolve_import_owner(
            db, os.environ.get("PRIMARY_USER_ID", ""), os.environ.get("RESUME_EMAIL", ""),
        )
        job, created = import_handshake_ai_opportunity(
            db, owner, application_verified=active, verification_reason=reason,
        )
    print(
        f"{'Created' if created else 'Updated'} Handshake job {job.id} ({job.external_id}); "
        f"official status: {job.official_status}."
    )


if __name__ == "__main__":
    main()
