"""Scoped, idempotent Google import. No profile seeding or email dispatch."""
from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import AuthorizedAccount, Job, ResumeProfile, UserProfile
from app.security.identity import JOSHUA_USER_ID
from app.services.dedupe import find_duplicate
from app.sources.google_careers import GOOGLE_SEARCH_URL, REQUESTED_GOOGLE_IDS
from app.sources.official_careers import OfficialCareersAdapter


def resolve_import_owner(db, configured_owner: str, configured_email: str) -> str:
    owner = configured_owner.strip()
    if not owner:
        email = configured_email.strip().casefold()
        if not email or "@" not in email:
            raise RuntimeError("Configure PRIMARY_USER_ID or the candidate's canonical RESUME_EMAIL before importing.")
        owners = set(db.scalars(select(ResumeProfile.user_id).where(func.lower(ResumeProfile.email) == email)))
        if len(owners) != 1:
            raise RuntimeError("The configured CV email does not identify exactly one stored candidate. No account was selected.")
        owner = next(iter(owners))
    if not owner or owner == JOSHUA_USER_ID or db.scalar(select(UserProfile.id).where(UserProfile.owner_user_id == owner)) is None:
        raise RuntimeError("The primary candidate's stored identity could not be verified. No account was selected.")
    if db.scalar(select(AuthorizedAccount.id).where(AuthorizedAccount.user_id == owner, AuthorizedAccount.provider == "google", AuthorizedAccount.is_active.is_(True))) is None:
        raise RuntimeError("The stored candidate has no active authorized login. No account was selected.")
    return owner


def resolve_authorized_import_owners(db) -> list[str]:
    """Import only for existing profiles with an active Google login."""
    active_ids = set(db.scalars(select(AuthorizedAccount.user_id).where(
        AuthorizedAccount.provider == "google",
        AuthorizedAccount.is_active.is_(True),
    ).execution_options(skip_owner_scope=True)))
    if not active_ids:
        raise RuntimeError("No active authorized Google accounts were found. No jobs were imported.")
    return sorted(set(db.scalars(select(UserProfile.owner_user_id).where(
        UserProfile.owner_user_id.in_(active_ids),
    ).execution_options(skip_owner_scope=True))))


def import_google_opportunities(db, jobs, owner_user_id: str, *, pin_requested: bool = True, commit: bool = True):
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise RuntimeError("The requested user's profile does not exist; refusing to seed or modify another account.")
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id, Job.company == "Google")))
    records = []
    for normalized in jobs:
        if normalized.company != "Google" or normalized.verification_status != "verified" or normalized.official_status != "open":
            continue
        data = normalized.to_dict()
        data["owner_user_id"] = owner_user_id
        if pin_requested and str(normalized.external_id) in REQUESTED_GOOGLE_IDS:
            data["raw_data"] = {**data["raw_data"], "_radar_user_priority": {
                "owner_user_id": owner_user_id, "reason": "Requested by candidate for Google Summer 2027 CV preparation",
            }}
        job = find_duplicate(existing, data)
        if job:
            _merge_duplicate(job, data)
        else:
            job = Job(**data)
            db.add(job)
            db.flush()
            existing.append(job)
        persist_analysis(db, job, profile)
        records.append(job)
    if commit:
        db.commit()
    return records


def import_google_for_authorized_users(db, jobs, primary_user_id: str) -> dict[str, list[Job]]:
    """Give every authorized profile independent Google jobs and analysis."""
    owners = resolve_authorized_import_owners(db)
    if primary_user_id not in owners:
        raise RuntimeError("The verified primary candidate is not an active import owner. No jobs were imported.")
    previous_scope = db.info.get("owner_user_id")
    imported: dict[str, list[Job]] = {}
    try:
        for owner in owners:
            db.info["owner_user_id"] = owner
            imported[owner] = import_google_opportunities(
                db, jobs, owner, pin_requested=owner == primary_user_id, commit=False,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if previous_scope is None:
            db.info.pop("owner_user_id", None)
        else:
            db.info["owner_user_id"] = previous_scope
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist verified Google jobs")
    parser.add_argument("--all-users", action="store_true", help="Import separately for every active authorized Google account with a stored profile")
    args = parser.parse_args()
    adapter = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL)
    jobs = asyncio.run(adapter.collect())
    if not args.all_users and not REQUESTED_GOOGLE_IDS <= {job.external_id for job in jobs}:
        raise RuntimeError("Both requested active Google postings were not verified. No changes were saved.")
    if args.apply:
        with SessionLocal() as db:
            owner = resolve_import_owner(db, os.environ.get("PRIMARY_USER_ID", ""), os.environ.get("RESUME_EMAIL", ""))
            if args.all_users:
                imported = import_google_for_authorized_users(db, jobs, owner)
                for user_id, records in imported.items():
                    research = sum("research" in job.title.casefold() for job in records)
                    print(f"Owner {user_id[:8]}: {len(records)} Google internships, {research} Research roles.")
                print(f"Saved independent Google catalogs for {len(imported)} authorized profiles. No emails sent.")
            else:
                records = import_google_opportunities(db, jobs, owner)
                print(f"Saved {len(records)} Google internships for the primary candidate. No emails sent.")
    else:
        print(f"Dry run: {len(jobs)} current Google technical internships. No emails sent.")


if __name__ == "__main__":
    main()
