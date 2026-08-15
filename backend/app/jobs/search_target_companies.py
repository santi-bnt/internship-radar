import asyncio
import argparse

from sqlalchemy import func, select

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.jobs.target_search import search_target_companies
from app.services.seed import seed_profile_and_sources
from app.models import TargetCompany


async def run(company: str | None = None, force: bool = False) -> int:
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        company_id = None
        if company:
            company_id = db.scalar(
                select(TargetCompany.id).where(
                    func.lower(TargetCompany.company_name) == company.lower()
                )
            )
            if company_id is None:
                raise SystemExit(f"Unknown target company: {company}")
        result = await search_target_companies(
            db,
            force=force or bool(company),
            company_id=company_id,
            trigger="manual" if force or company else "cron",
        )
        print(
            f"Target search complete: {result.companies_checked} companies, "
            f"{result.jobs_discovered} discovered, {result.jobs_added} added, "
            f"{result.jobs_updated} updated, {len(result.errors)} errors."
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search configured target companies.")
    parser.add_argument("--company", help="Search one canonical target company name.")
    parser.add_argument("--force", action="store_true", help="Ignore priority cadence.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(company=args.company, force=args.force)))
