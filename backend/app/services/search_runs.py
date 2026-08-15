from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.jobs.refresh import refresh_all_sources
from app.models import SearchRun, TargetCompany
from app.services.job_lifecycle import expire_past_deadline_jobs


logger = logging.getLogger(__name__)
RUNNING_STATUSES = ("pending", "running")


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=True))


def _lock_search_registry(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7312026)"))


def create_search_run(
    db: Session,
    *,
    search_type: str,
    trigger: str = "manual",
) -> SearchRun | None:
    _lock_search_registry(db)
    stale_before = datetime.now(timezone.utc) - timedelta(hours=2)
    stale = list(
        db.scalars(
            select(SearchRun).where(
                SearchRun.status.in_(RUNNING_STATUSES),
                SearchRun.started_at < stale_before,
            )
        )
    )
    for item in stale:
        item.status = "failed"
        item.progress_status = "Failed"
        item.completed_at = datetime.now(timezone.utc)
        item.error_count = 1
        item.safe_error_summary = "Search exceeded the safe two-hour execution window."
    active = db.scalar(
        select(SearchRun)
        .where(SearchRun.status.in_(RUNNING_STATUSES))
        .order_by(SearchRun.started_at.desc())
        .limit(1)
    )
    if active:
        db.commit()
        return None
    run = SearchRun(
        search_type=search_type,
        trigger=trigger,
        status="pending",
        progress_status="Starting",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _high_priority_target_count(db: Session) -> int:
    return len(
        list(
            db.scalars(
                select(TargetCompany).where(
                    TargetCompany.enabled.is_(True),
                    TargetCompany.priority == "high",
                )
            )
        )
    )


async def execute_search_run(run_id: int) -> None:
    init_db()
    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if not run or run.status not in RUNNING_STATUSES:
            return
        run.status = "running"
        run.progress_status = "Searching official sources"
        db.commit()
        _log("search_started", run_id=run.id, search_type=run.search_type, trigger=run.trigger)
        try:
            if run.search_type == "high_priority":
                run.companies_checked = _high_priority_target_count(db)
                db.commit()

            if run.search_type == "expire_deadlines":
                summary: dict[str, Any] = {
                    "sources_checked": 0,
                    "jobs_fetched": 0,
                    "jobs_created": 0,
                    "jobs_updated": 0,
                    "errors": [],
                }
            else:
                # Every managed search refreshes every enabled automatic source.
                # Priority still affects ranking and cadence, never source coverage.
                summary = await refresh_all_sources(db)

            run = db.get(SearchRun, run_id)
            run.progress_status = "Normalizing jobs"
            db.commit()
            run.progress_status = "Deduplicating jobs"
            db.commit()
            run.progress_status = "Scoring matches"
            db.commit()
            run.progress_status = "Verifying openings"
            db.commit()

            run.sources_checked = summary.get("sources_checked", 0)
            run.jobs_discovered = summary.get("jobs_fetched", 0)
            run.jobs_added = summary.get("jobs_created", 0)
            run.jobs_updated = summary.get("jobs_updated", 0)
            run.jobs_expired = expire_past_deadline_jobs(db)
            errors = summary.get("errors", [])
            run.error_count = len(errors)
            source_names = [str(item.get("source", "source"))[:80] for item in errors[:10]]
            run.safe_error_summary = (
                f"Sources with errors: {', '.join(source_names)}" if source_names else ""
            )
            run.source_metrics = summary.get("source_metrics", [])
            run.status = "partial" if errors else "completed"
            run.progress_status = "Completed"
        except Exception:
            db.rollback()
            run = db.get(SearchRun, run_id)
            if not run:
                return
            run.status = "failed"
            run.progress_status = "Failed"
            run.error_count = 1
            run.safe_error_summary = "Search failed. Review server logs for the safe diagnostic."
            logger.exception("search_failed run_id=%s type=%s", run.id, run.search_type)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        _log(
            "search_finished",
            run_id=run.id,
            search_type=run.search_type,
            status=run.status,
            sources_checked=run.sources_checked,
            jobs_discovered=run.jobs_discovered,
            jobs_added=run.jobs_added,
            jobs_updated=run.jobs_updated,
            jobs_expired=run.jobs_expired,
            error_count=run.error_count,
        )


async def run_managed_search(search_type: str, trigger: str = "cron") -> SearchRun | None:
    init_db()
    with SessionLocal() as db:
        run = create_search_run(db, search_type=search_type, trigger=trigger)
        run_id = run.id if run else None
    if run_id is None:
        _log("search_skipped_concurrent", search_type=search_type, trigger=trigger)
        return None
    await execute_search_run(run_id)
    with SessionLocal() as db:
        return db.get(SearchRun, run_id)
