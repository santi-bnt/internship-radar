"""Manual discovery smoke test. Dry-run is the default; no applications/emails.

python -m app.jobs.discover_opportunities --query robotics --countries "United States" Canada --days 30
"""
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import CompanySource, Job, UserProfile
from app.services.dedupe import find_duplicate
from app.services.search_criteria import matches_discovery_criteria
from app.sources.registry import create_adapter


async def execute(args):
    report = {"dryRun": True, "rawResults": 0, "duplicates": 0, "newJobs": 0, "verifiedJobs": 0, "eligibleJobs": 0, "unknownEligibility": 0, "unknownPostedDate": 0, "sourceErrors": [], "sources": []}
    with SessionLocal() as db:
        db.info["owner_user_id"] = settings.effective_primary_user_id
        try:
            profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == settings.effective_primary_user_id))
            existing = list(db.scalars(select(Job).where(Job.owner_user_id == settings.effective_primary_user_id)))
            sources = list(db.scalars(select(CompanySource).where(CompanySource.owner_user_id == settings.effective_primary_user_id, CompanySource.enabled.is_(True), CompanySource.reference_only.is_(False), CompanySource.source_type.in_(["greenhouse", "lever", "ashby"]))).all())
        except SQLAlchemyError:
            db.rollback()
            profile, existing, sources = None, [], []
        if args.board:
            sources = []
            hosts = {"greenhouse": "boards.greenhouse.io", "lever": "jobs.lever.co", "ashby": "jobs.ashbyhq.com"}
            for spec in args.board:
                kind, sep, slug = spec.partition(":")
                if not sep or kind not in hosts:
                    raise ValueError("Boards use greenhouse:slug, lever:slug, or ashby:slug")
                sources.append(SimpleNamespace(company=slug, source_type=kind, source_identifier=slug, source_url=f"https://{hosts[kind]}/{slug}"))
        criteria = {"include_keywords": [args.query], "countries": args.countries, "only_realistically_eligible": False, "allow_unknown_location": True}
        seen = list(existing)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=args.days)
        for source in sources[:args.max_sources]:
            try:
                adapter = create_adapter(source, search_criteria=criteria)
                rows = await adapter.collect()
                report["rawResults"] += getattr(adapter, "fetched_count", len(rows))
                report["sources"].append({"source": source.source_type, "board": source.source_identifier, "normalized": len(rows)})
                for row in rows:
                    if not row.posted_at:
                        report["unknownPostedDate"] += 1
                        continue  # Cannot honestly label this as published in the last 30 days.
                    if not cutoff <= row.posted_at <= now or not matches_discovery_criteria(row, criteria)[0]:
                        continue
                    if find_duplicate(seen, row):
                        report["duplicates"] += 1
                        continue
                    seen.append(row)
                    report["newJobs"] += 1
                    report["verifiedJobs"] += row.verification_status == "verified"
                    if profile:
                        from app.services.scoring import analyze_job
                        result = analyze_job(row, profile)
                        report["eligibleJobs"] += result.eligibility_status in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
                        report["unknownEligibility"] += result.eligibility_status == "UNKNOWN"
                    else:
                        report["unknownEligibility"] += 1
            except Exception as exc:
                report["sourceErrors"].append({"source": source.source_type, "error": type(exc).__name__})
    report["note"] = "No jobs were stored, no application was performed and no email was sent. Undated postings are excluded from the strict published-date window."
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="robotics")
    parser.add_argument("--countries", nargs="+", default=["United States", "Canada"])
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-sources", type=int, choices=range(1, 9), default=3)
    parser.add_argument("--board", action="append", help="Optional explicit ATS board; dry-run only")
    asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    main()
