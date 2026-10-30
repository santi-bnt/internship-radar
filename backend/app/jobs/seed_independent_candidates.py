"""Idempotently provision registry candidates and their isolated job catalogs."""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.jobs.refresh import persist_analysis
from app.models import Job, JobAnalysis, UserProfile
from app.services.candidate_registry import INDEPENDENT_CANDIDATE_SEEDS
from app.services.multi_user_seed import (
    ensure_candidate_job_catalog,
    seed_independent_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write the candidate records and isolated catalog")
    args = parser.parse_args()
    if not args.apply:
        for candidate in INDEPENDENT_CANDIDATE_SEEDS:
            print(f"Dry run: {candidate.user_id} | {candidate.email}")
        return
    with SessionLocal() as db:
        for candidate in INDEPENDENT_CANDIDATE_SEEDS:
            seed_independent_candidate(db, candidate)
            ensure_candidate_job_catalog(db, candidate.user_id)
            profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == candidate.user_id))
            if profile:
                for job in db.scalars(select(Job).outerjoin(JobAnalysis).where(
                    Job.owner_user_id == candidate.user_id, JobAnalysis.id.is_(None),
                )):
                    persist_analysis(db, job, profile)
            print(f"Provisioned {candidate.user_id} ({candidate.email})")
        db.commit()


if __name__ == "__main__":
    main()
