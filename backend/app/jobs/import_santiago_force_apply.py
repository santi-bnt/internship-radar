"""Import only Santiago's explicitly requested, officially verified postings."""
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs.import_google import resolve_import_owner
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import Job, UserProfile
from app.services.normalization import clean_text, validate_public_url
from app.services.dedupe import find_duplicate
from app.services.force_apply import apply_requested_santiago_overrides, requested_force_apply_target
from app.sources.amazon_jobs import AmazonJobsAdapter
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.smartrecruiters import SmartRecruitersAdapter
from app.sources.workday import WorkdayAdapter


AMAZON_IDS = set()
INTEL_IDS = set()
MICRON_IDS = set()
HP_IDS = set()
HPE_IDS = set()


@dataclass(frozen=True)
class DirectOfficialPosting:
    """An exact candidate-selected posting, normally from an official source."""

    company: str
    title: str
    location: str
    url: str
    external_id: str
    allow_pending_verification: bool = True
    official_source: bool = True


DIRECT_OFFICIAL_POSTINGS = ()

# Google Careers no longer exposes the BS Summer 2027 SWE posting; its stated
# application window ended September 25, 2026. Keep it discoverable as history
# when desired, but never create/retain an Apply Now override for this posting.
CONFIRMED_CLOSED_DIRECT_POSTINGS = ()


def build_pending_direct_posting(posting: DirectOfficialPosting):
    """Normalize a candidate-supplied posting without claiming it is open.

    Some ATSs deny automated reads even though the applicant can open the
    supplied page in a browser. Keeping the exact URL is useful, but it stays
    unverified until a source can confirm it. Santiago's manual action is a
    separate, candidate-owned decision.
    """
    adapter = OfficialCareersAdapter(
        posting.company, "candidate_requested", posting.url,
    )
    marker = (
        "_candidate_requested_official_url"
        if posting.official_source else "_candidate_requested_url"
    )
    job = adapter.build_job(
        {"external_id": posting.external_id, "title": posting.title, marker: True},
        external_id=posting.external_id,
        title=posting.title,
        location=posting.location,
        description="Candidate-selected posting pending automated verification.",
        requirements="",
        apply_url=posting.url,
        employment_type="Internship",
        original_source_url=posting.url,
        official_apply_url=posting.url if posting.official_source else None,
        official_status="unknown",
        verification_status="unverified",
        verification_method=(
            "candidate_official_url_pending" if posting.official_source
            else "candidate_reference_url_pending"
        ),
        status_reason=(
            "Official URL is pending automated verification; candidate selected Apply Now manually."
            if posting.official_source else
            "Candidate-selected reference is pending official-portal verification; manual action remains visible."
        ),
    )
    if not posting.official_source:
        job.source_name = "LinkedIn candidate reference"
        job.discovered_from_source = "linkedin_candidate_reference"
    return job


def _has_confirmed_closure(page_text: str) -> bool:
    text = clean_text(page_text).casefold()
    return any(marker in text for marker in (
        "job is no longer available", "no longer accepting applications",
        "position has been filled", "position is closed", "job has expired",
    ))


def _matches_direct_posting(posting: DirectOfficialPosting, url: str, page_text: str) -> bool:
    """Accept normal ATS punctuation/title variants without accepting a generic page."""
    identity = clean_text(f"{url} {page_text}").casefold()
    if posting.external_id.casefold() in identity:
        return True
    title_tokens = [
        token for token in clean_text(posting.title).casefold().split()
        if len(token) >= 3
    ]
    # E.g. "Intern - Soporte IT" is the same role as "Intern Soporte IT".
    return bool(title_tokens) and sum(token in identity for token in title_tokens) >= max(
        2, (len(title_tokens) + 1) // 2,
    )


async def collect_direct_official_postings():
    """Verify an exact official URL, then normalize it through the usual model."""
    from app.sources.official_careers import OfficialCareersAdapter

    normalized = []

    def pending_job(adapter, posting: DirectOfficialPosting, url: str):
        """Keep an exact candidate link without asserting unavailable facts."""
        marker = (
            "_candidate_requested_official_url"
            if posting.official_source else "_candidate_requested_url"
        )
        job = adapter.build_job(
            {"external_id": posting.external_id, "title": posting.title, marker: True},
            external_id=posting.external_id,
            title=posting.title,
            location=posting.location,
            description="Candidate-selected posting pending automated verification.",
            requirements="",
            apply_url=url,
            employment_type="Internship",
            original_source_url=url,
            official_apply_url=url if posting.official_source else None,
            official_status="unknown",
            verification_status="unverified",
            verification_method=(
                "candidate_official_url_pending" if posting.official_source
                else "candidate_reference_url_pending"
            ),
            status_reason=(
                "Official URL is pending automated verification; candidate selected Apply Now manually."
                if posting.official_source else
                "Candidate-selected reference is pending official-portal verification; manual action remains visible."
            ),
        )
        if not posting.official_source:
            job.source_name = "LinkedIn candidate reference"
            job.discovered_from_source = "linkedin_candidate_reference"
        return job

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    ) as client:
        for posting in DIRECT_OFFICIAL_POSTINGS:
            validate_public_url(posting.url)
            adapter = OfficialCareersAdapter(posting.company, "google", posting.url)
            try:
                response = await client.get(posting.url)
                response.raise_for_status()
            except httpx.HTTPError:
                # The candidate supplied this exact official URL. Some career
                # portals deny server-side reads while still working in a
                # browser. Preserve the real pending verification state rather
                # than inventing a success result or dropping their manual
                # action solely because automation is blocked.
                if posting.allow_pending_verification:
                    normalized.append(pending_job(adapter, posting, posting.url))
                continue
            page_text = clean_text(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True))
            # An official page must still identify the requested role and not
            # carry an explicit terminal message. This avoids creating a job
            # from an old redirect, a generic careers page, or a dead URL.
            if _has_confirmed_closure(page_text):
                continue
            if not _matches_direct_posting(posting, str(response.url), page_text):
                if not posting.allow_pending_verification:
                    continue
                normalized.append(pending_job(adapter, posting, str(response.url)))
                continue
            job = adapter.build_job(
                {"external_id": posting.external_id, "title": posting.title},
                external_id=posting.external_id,
                title=posting.title,
                location=posting.location,
                description=page_text,
                requirements=page_text,
                apply_url=str(response.url),
                employment_type="Internship",
                original_source_url=str(response.url),
                official_apply_url=str(response.url),
                official_status="open",
                verification_status="verified",
                verification_method="official_direct_posting",
                status_reason="Exact candidate-requested posting remains available on the official careers site.",
                last_verified_at=datetime.now(timezone.utc),
            )
            if not posting.official_source:
                # A LinkedIn reference can be live but remains a reference;
                # it must not masquerade as official verification.
                job.source_name = "LinkedIn candidate reference"
                job.discovered_from_source = "linkedin_candidate_reference"
                job.official_status = "unknown"
                job.verification_status = "unverified"
                job.verification_method = "candidate_reference_url_pending"
                job.status_reason = "Candidate-selected reference is live; official portal verification is still pending."
                job.raw_data["_candidate_requested_url"] = True
            normalized.append(job)
    return normalized


async def collect_verified_jobs():
    """Use official APIs; unavailable requisitions are intentionally omitted."""
    amazon = AmazonJobsAdapter("Amazon", "internships", AmazonJobsAdapter.API_URL)
    intel = WorkdayAdapter("Intel", "intel|External", "https://intel.wd1.myworkdayjobs.com/External")
    micron = WorkdayAdapter("Micron", "micron|External", "https://micron.wd1.myworkdayjobs.com/External")
    hp = WorkdayAdapter("HP", "hp|ExternalCareerSite", "https://hp.wd5.myworkdayjobs.com/ExternalCareerSite")
    hpe = WorkdayAdapter("Hewlett Packard Enterprise", "hpe|Jobsathpe", "https://hpe.wd5.myworkdayjobs.com/Jobsathpe")
    solidigm = SmartRecruitersAdapter(
        "Solidigm", "Solidigm", "https://jobs.smartrecruiters.com/Solidigm",
    )
    amazon_raw, intel_raw, micron_raw, hp_raw, hpe_raw, solidigm_raw, direct = await asyncio.gather(
        amazon.fetch_exact_public_ids(AMAZON_IDS),
        intel.fetch_exact_public_ids(INTEL_IDS, require_all=False),
        micron.fetch_exact_public_ids(MICRON_IDS, require_all=False),
        hp.fetch_exact_public_ids(HP_IDS, require_all=False),
        hpe.fetch_exact_public_ids(HPE_IDS, require_all=False),
        solidigm.fetch_jobs(),
        collect_direct_official_postings(),
    )
    normalized = [
        *(amazon.normalize_job(raw) for raw in amazon_raw),
        *(intel.normalize_job(raw) for raw in intel_raw),
        *(micron.normalize_job(raw) for raw in micron_raw),
        *(hp.normalize_job(raw) for raw in hp_raw),
        *(hpe.normalize_job(raw) for raw in hpe_raw),
        *(solidigm.normalize_job(raw) for raw in solidigm_raw),
        *direct,
    ]
    # The Solidigm ATS query can return other internships; importing a
    # candidate-requested batch must remain narrow and never widen discovery.
    return [job for job in normalized if requested_force_apply_target(job)]


def import_verified_jobs(db, jobs, owner_user_id: str):
    """Persist normalized jobs through the standard dedupe and analysis flow."""
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise RuntimeError("Santiago's candidate profile is required before importing jobs.")
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    records = []
    for normalized in jobs:
        pending_candidate_url = bool(
            normalized.raw_data.get("_candidate_requested_official_url")
            or normalized.raw_data.get("_candidate_requested_url")
        )
        if (normalized.official_status != "open" or normalized.verification_status != "verified") and not pending_candidate_url:
            continue
        data = normalized.to_dict()
        data["owner_user_id"] = owner_user_id
        job = next((item for item in existing if (
            str(item.external_id or "") == str(normalized.external_id or "")
            and item.company.casefold() == normalized.company.casefold()
        )), None)
        # Exact candidate-supplied requisition IDs are authoritative. Two
        # Jabil postings can have nearly identical titles but must not be
        # collapsed by title/location fuzzy dedupe.
        # Workday can publish a new requisition with the same title and city.
        # Its exact public ID must not overwrite an older Applied record.
        if job is None and not normalized.external_id:
            job = find_duplicate(existing, data)
        if job is None:
            job = Job(**data)
            db.add(job)
            db.flush()
            existing.append(job)
        else:
            _merge_duplicate(job, data)
        # A direct lookup in the employer's ATS is stronger, newer evidence
        # than a previous "missing from a broad scan" archive.  Restore that
        # candidate-owned record before considering its manual action.  This
        # intentionally does not touch user choices such as Not Interested or
        # an explicit application history.
        if job.status in {"archived", "expired"}:
            job.status = "active"
            job.is_active = True
            job.archived_at = None
            job.expired_at = None
        persist_analysis(db, job, profile)
        records.append(job)
    db.commit()
    apply_requested_santiago_overrides(db, owner_user_id)
    return records


def ensure_santiago_requested_opportunities(db, owner_user_id: str | None = None):
    """No operator-curated candidate imports are bundled in the showcase."""
    return {"created": 0, "updated": 0, "skipped": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    jobs = asyncio.run(collect_verified_jobs())
    if not args.apply:
        for job in jobs:
            print(f"{job.company} | {job.external_id} | {job.title} | {job.location}")
        print(f"Dry run: {len(jobs)} official active jobs verified.")
        return
    with SessionLocal() as db:
        owner = resolve_import_owner(
            db, os.environ.get("PRIMARY_USER_ID", ""), os.environ.get("RESUME_EMAIL", ""),
        )
        records = import_verified_jobs(db, jobs, owner)
    print(f"Saved {len(records)} official active jobs and reconciled Santiago overrides.")


if __name__ == "__main__":
    main()
