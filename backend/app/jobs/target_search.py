from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.jobs.refresh import refresh_all_sources
from app.models import CompanySource, Job, TargetCompany, TargetSearchRun
from app.services.job_lifecycle import expire_past_deadline_jobs
from app.services.normalization import normalized_token
from app.services.target_companies import search_is_due


def _source_matches_target(source: CompanySource, target: TargetCompany) -> bool:
    source_name = normalized_token(source.company)
    aliases = [target.company_name, *(target.aliases or [])]
    return any(normalized_token(alias) == source_name for alias in aliases)


async def search_target_companies(
    db: Session,
    *,
    force: bool = False,
    company_id: int | None = None,
    trigger: str = "manual",
) -> TargetSearchRun:
    run = TargetSearchRun(trigger=trigger)
    db.add(run)
    db.commit()
    db.refresh(run)
    targets = list(
        db.scalars(
            select(TargetCompany).where(
                TargetCompany.enabled.is_(True),
                *([TargetCompany.id == company_id] if company_id is not None else []),
            )
        )
    )
    selected = [target for target in targets if force or search_is_due(target)]
    source_ids: set[int] | None = None
    if company_id is not None:
        sources = list(
            db.scalars(select(CompanySource).where(CompanySource.enabled.is_(True)))
        )
        source_ids = {
            source.id
            for source in sources
            if any(_source_matches_target(source, target) for target in selected)
        }
    try:
        should_refresh = bool(selected) and (company_id is None or bool(source_ids))
        summary = await refresh_all_sources(db, source_ids=source_ids) if should_refresh else {
            "jobs_fetched": 0,
            "jobs_created": 0,
            "jobs_updated": 0,
            "errors": [],
        }
        now = datetime.now(timezone.utc)
        for target in selected:
            target.last_checked_at = now
            target.open_jobs_count = (
                db.scalar(
                    select(func.count(Job.id)).where(
                        Job.is_target_company.is_(True),
                        Job.company == target.company_name,
                        Job.status.in_(("active", "saved")),
                    )
                )
                or 0
            )
            if target.open_jobs_count:
                target.last_successful_result_at = now
        run.companies_checked = len(selected)
        run.jobs_discovered = summary["jobs_fetched"]
        run.jobs_added = summary["jobs_created"]
        run.jobs_updated = summary["jobs_updated"]
        run.jobs_expired = expire_past_deadline_jobs(db)
        run.errors = summary["errors"]
    except Exception as exc:
        db.rollback()
        run = db.get(TargetSearchRun, run.id)
        run.errors = [{"source": "target_search", "error": str(exc)[:1000]}]
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
