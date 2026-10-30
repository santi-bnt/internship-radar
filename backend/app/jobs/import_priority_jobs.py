"""Import a small, candidate-requested set of official postings atomically."""
from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs.import_google import resolve_import_owner
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import Job, UserProfile
from app.services.dedupe import find_duplicate
from app.sources.amazon_jobs import AmazonJobsAdapter
from app.sources.google_careers import GOOGLE_SEARCH_URL
from app.sources.official_careers import OfficialCareersAdapter


GOOGLE_PRIORITY_IDS = {
    "100648618540573382", "122803627516404422", "114405557703451334",
    "136826798817059526", "139129176165622470",
}
AMAZON_PRIORITY_IDS = {"10529525", "10552937"}
PRIORITY_IDS = GOOGLE_PRIORITY_IDS | AMAZON_PRIORITY_IDS


def import_priority_opportunities(db, jobs, owner_user_id: str):
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise RuntimeError("The requested user's profile does not exist; refusing to modify another account.")
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    requested = [job for job in jobs if str(job.external_id) in PRIORITY_IDS]
    if {str(job.external_id) for job in requested} != PRIORITY_IDS:
        raise RuntimeError("Not every requested official posting was prepared; no changes were saved.")
    records = []
    for normalized in requested:
        if normalized.verification_status != "verified" or normalized.official_status != "open":
            raise RuntimeError(f"Requested posting {normalized.external_id} is not officially verified and open.")
        data = normalized.to_dict()
        data["owner_user_id"] = owner_user_id
        data["raw_data"] = {
            **data["raw_data"],
            "_radar_user_priority": {
                "owner_user_id": owner_user_id,
                "reason": "Requested by candidate for CV preparation",
            },
        }
        # These are explicit, public requisitions.  Do not let a fuzzy title
        # match collapse two different Google or Amazon postings into one.
        job = next(
            (
                item for item in existing
                if str(item.external_id) == str(normalized.external_id)
                and item.company.casefold() == normalized.company.casefold()
            ),
            None,
        )
        if job is None:
            duplicate = find_duplicate(existing, data)
            if duplicate is not None and str(duplicate.external_id) == str(normalized.external_id):
                job = duplicate
        if job:
            _merge_duplicate(job, data)
        else:
            job = Job(**data)
            db.add(job)
            db.flush()
            existing.append(job)
        persist_analysis(db, job, profile)
        records.append(job)
    if {str(job.external_id) for job in records} != PRIORITY_IDS:
        raise RuntimeError("Not every requested official posting was prepared; no changes were saved.")
    db.commit()
    return records


async def collect_requested_jobs():
    google = OfficialCareersAdapter(
        "Google", "google", GOOGLE_SEARCH_URL,
        search_criteria={"required_external_ids": sorted(GOOGLE_PRIORITY_IDS)},
    )
    amazon = AmazonJobsAdapter("Amazon", "amazon", AmazonJobsAdapter.API_URL)
    google_jobs, amazon_raw = await asyncio.gather(
        google.collect(), amazon.fetch_exact_public_ids(AMAZON_PRIORITY_IDS),
    )
    amazon_jobs = [amazon.normalize_job(raw) for raw in amazon_raw]
    jobs = [*google_jobs, *amazon_jobs]
    if {str(job.external_id) for job in jobs} != PRIORITY_IDS:
        raise RuntimeError("One or more requested official postings could not be verified; no changes were saved.")
    return jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist only to the verified primary candidate account")
    args = parser.parse_args()
    jobs = asyncio.run(collect_requested_jobs())
    if args.apply:
        with SessionLocal() as db:
            owner = resolve_import_owner(db, os.environ.get("PRIMARY_USER_ID", ""), os.environ.get("RESUME_EMAIL", ""))
            jobs = import_priority_opportunities(db, jobs, owner)
    for job in jobs:
        print(f"{getattr(job, 'id', '-')}: {job.company} | {job.external_id} | {job.title} | priority=True")
    print(f"{'Saved' if args.apply else 'Dry run:'} {len(jobs)} requested official postings. No emails sent.")


if __name__ == "__main__":
    main()
