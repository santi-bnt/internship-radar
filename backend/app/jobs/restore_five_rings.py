"""Re-import one candidate-requested official Greenhouse requisition, in place."""
from __future__ import annotations

import argparse
import asyncio
import os

import httpx
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs.import_google import resolve_import_owner
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import Application, Job, UserProfile
from app.services.application_urls import resolve_application_url
from app.sources.greenhouse import GreenhouseAdapter


BOARD = "fiveringsllc"
EXTERNAL_ID = "5394515008"
OFFICIAL_URL = f"https://job-boards.greenhouse.io/{BOARD}/jobs/{EXTERNAL_ID}"
API_URL = f"https://boards-api.greenhouse.io/v1/boards/{BOARD}/jobs/{EXTERNAL_ID}"


async def fetch_official_job():
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = await client.get(API_URL, headers={"User-Agent": settings.user_agent})
        response.raise_for_status()
        raw = response.json()
    if str(raw.get("id")) != EXTERNAL_ID or not raw.get("title") or not raw.get("content"):
        raise RuntimeError("The official Greenhouse API did not return the requested full posting.")
    if raw.get("absolute_url", "").rstrip("/") != OFFICIAL_URL:
        raise RuntimeError("The official Greenhouse API returned a different posting URL.")
    adapter = GreenhouseAdapter("Five Rings", BOARD, f"https://job-boards.greenhouse.io/{BOARD}")
    return adapter.normalize_job(raw)


def restore_official_job(db, normalized, owner_user_id: str) -> tuple[Job, bool]:
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise RuntimeError("The requested owner's profile is missing; no other account will be modified.")
    if normalized.verification_status != "verified" or normalized.official_status != "open":
        raise RuntimeError("Official posting is not verified open; refusing to restore it as active.")
    data = normalized.to_dict()
    resolution = resolve_application_url(data)
    data.update(
        posting_url=resolution.posting_url,
        application_url=resolution.application_url,
        application_url_source=resolution.source,
        application_url_status=resolution.status,
        application_url_last_verified_at=resolution.verified_at,
        application_url_diagnostic=resolution.diagnostic,
    )
    if not data["application_url"] or data["application_url_status"] != "VERIFIED":
        raise RuntimeError("The official application URL could not be verified; no record was changed.")
    # Exact requisition/URL identity only. Never merge another Five Rings job
    # because its title happens to be similar.
    matches = list(db.scalars(select(Job).where(
        Job.owner_user_id == owner_user_id,
        or_(
            Job.original_source_url == OFFICIAL_URL,
            Job.posting_url == OFFICIAL_URL,
            (Job.external_id == EXTERNAL_ID) & Job.source_url.contains(BOARD),
        ),
    )))
    if len(matches) > 1:
        raise RuntimeError("Multiple exact existing records found; refusing to create or merge another.")
    job = matches[0] if matches else None
    restored_existing = job is not None
    if job is None:
        job = Job(owner_user_id=owner_user_id, **data)
        db.add(job)
        db.flush()
    else:
        _merge_duplicate(job, data)
        if job.status in {"archived", "not_interested", "expired"}:
            latest = db.scalar(select(Application).where(Application.job_id == job.id).order_by(Application.updated_at.desc()).limit(1))
            job.status = "applied" if latest and latest.status in {"Applied", "Interview", "Rejected", "Offer"} else "saved" if latest and latest.status == "Saved" else "active"
            job.archived_at = None
            job.expired_at = None
    persist_analysis(db, job, profile)
    db.commit()
    return job, restored_existing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    normalized = asyncio.run(fetch_official_job())
    if not args.apply:
        print(f"Dry run: official {normalized.title} | {normalized.official_status} | {normalized.original_source_url}")
        return
    with SessionLocal() as db:
        owner = resolve_import_owner(db, os.environ.get("PRIMARY_USER_ID", ""), os.environ.get("RESUME_EMAIL", ""))
        job, reused = restore_official_job(db, normalized, owner)
        print(f"job_id={job.id} reused_existing={reused} status={job.status} official_status={job.official_status} url={job.original_source_url}")


if __name__ == "__main__":
    main()
