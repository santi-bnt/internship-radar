from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.jobs.refresh import refresh_all_sources, revalidate_existing_jobs
from app.models import Job, SearchRun, SearchRunJob, TargetCompany
from app.services.job_lifecycle import expire_past_deadline_jobs
from app.services.search_criteria import search_result_sort_key, selected_company_names


logger = logging.getLogger(__name__)
RUNNING_STATUSES = ("pending", "running")
ABANDONED_SEARCH_AFTER = timedelta(minutes=30)


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=True))


def _lock_search_registry(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7312026)"))


def fail_abandoned_search_runs(db: Session, *, owner_user_id: str | None = None) -> int:
    stale_before = datetime.now(timezone.utc) - ABANDONED_SEARCH_AFTER
    query = select(SearchRun).where(
        SearchRun.status.in_(RUNNING_STATUSES),
        SearchRun.started_at < stale_before,
    )
    if owner_user_id is not None:
        query = query.where(SearchRun.owner_user_id == owner_user_id)
    stale = list(db.scalars(query))
    for item in stale:
        item.status = "failed"
        item.progress_status = "Failed"
        item.completed_at = datetime.now(timezone.utc)
        item.error_count = 1
        item.safe_error_summary = "Search stopped after the safe 30-minute execution window."
    return len(stale)


def create_search_run(
    db: Session,
    *,
    search_type: str,
    trigger: str = "manual",
    criteria: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
) -> SearchRun | None:
    _lock_search_registry(db)
    fail_abandoned_search_runs(db)
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
        criteria_json=criteria or {},
        progress_json={
            "sources_checked": 0,
            "sources_total": 0,
            "jobs_discovered": 0,
            "verified": 0,
            "eligible": 0,
            "duplicates_removed": 0,
        },
    )
    if owner_user_id:
        run.owner_user_id = owner_user_id
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


def _store_search_results(
    db: Session,
    run: SearchRun,
    summary: dict[str, Any],
) -> None:
    db.execute(delete(SearchRunJob).where(SearchRunJob.search_run_id == run.id))
    matched = summary.get("matched_jobs") or {}
    job_ids = [int(job_id) for job_id in matched]
    if not job_ids:
        run.result_count = 0
        run.eligible_count = 0
        run.verified_count = 0
        return
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.id.in_(job_ids))
            .options(joinedload(Job.analysis))
        ).unique()
    )
    jobs.sort(key=search_result_sort_key, reverse=True)
    limit = int((run.criteria_json or {}).get("limit") or 50)
    jobs = jobs[:limit]
    eligible_count = 0
    verified_count = 0
    for rank, job in enumerate(jobs, start=1):
        analysis = job.analysis
        eligibility = analysis.eligibility_status if analysis else "UNKNOWN"
        if eligibility in {"ELIGIBLE", "LIKELY_ELIGIBLE"}:
            eligible_count += 1
        if job.verification_status in {"verified", "partially_verified"}:
            verified_count += 1
        match = matched.get(str(job.id), {})
        db.add(
            SearchRunJob(
                owner_user_id=run.owner_user_id,
                search_run_id=run.id,
                job_id=job.id,
                discovered_during_run=bool(match.get("discovered_during_run")),
                matched_criteria=match.get("matched_criteria") or {},
                rank=rank,
                technical_score_snapshot=float(
                    analysis.technical_score if analysis else 0
                ),
                eligibility_snapshot=eligibility,
            )
        )
    run.result_count = len(jobs)
    run.eligible_count = eligible_count
    run.verified_count = verified_count


async def execute_search_run(run_id: int) -> None:
    init_db()
    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if not run or run.status not in RUNNING_STATUSES:
            return
        db.info["owner_user_id"] = run.owner_user_id
        run.status = "running"
        run.progress_status = "Searching official sources"
        db.commit()
        _log("search_started", run_id=run.id, search_type=run.search_type, trigger=run.trigger)
        try:
            if run.search_type == "high_priority":
                run.companies_checked = _high_priority_target_count(db)
                db.commit()

            if run.search_type in {"expire_deadlines", "verification"}:
                summary: dict[str, Any] = {
                    "sources_checked": 0,
                    "jobs_fetched": 0,
                    "jobs_created": 0,
                    "jobs_updated": 0,
                    "errors": [],
                }
            else:
                criteria = dict(run.criteria_json or {}) or None
                if criteria is not None:
                    targets = list(
                        db.scalars(
                            select(TargetCompany).where(TargetCompany.enabled.is_(True))
                        )
                    )
                    run.companies_checked = len(
                        selected_company_names(criteria, targets)
                    )
                    db.commit()

                def report_progress(progress: dict[str, Any]) -> None:
                    current = db.get(SearchRun, run_id)
                    if not current:
                        return
                    current.sources_checked = int(progress.get("sources_checked", 0))
                    current.jobs_discovered = int(progress.get("jobs_fetched", 0))
                    current.jobs_added = int(progress.get("jobs_created", 0))
                    current.jobs_updated = int(progress.get("jobs_updated", 0))
                    current.progress_status = (
                        f"Searching sources {current.sources_checked} / "
                        f"{int(progress.get('source_total', 0))}"
                    )
                    current.progress_json = {
                        "sources_checked": current.sources_checked,
                        "sources_total": int(progress.get("source_total", 0)),
                        "jobs_discovered": current.jobs_discovered,
                        "verified": int(progress.get("verified_matches", 0)),
                        "eligible": int(progress.get("eligible_matches", 0)),
                        "duplicates_removed": int(progress.get("duplicates_removed", 0)),
                        "guadalajara_metro": int(progress.get("guadalajara_metro_matches", 0)),
                        "mexico_remote": int(progress.get("mexico_remote_matches", 0)),
                        "latam_remote": int(progress.get("latam_remote_matches", 0)),
                        "application_urls_verified": int(progress.get("application_urls_verified", 0)),
                        "application_urls_missing": int(progress.get("application_urls_missing", 0)),
                    }
                    db.commit()

                summary = (
                    await refresh_all_sources(
                        db,
                        criteria=criteria,
                        progress_callback=report_progress,
                    )
                    if criteria is not None
                    else await refresh_all_sources(db)
                )

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
            revalidation = (
                await revalidate_existing_jobs(db, owner_user_id=run.owner_user_id)
                if run.search_type == "verification"
                else {"checked": 0, "open": 0, "expired": 0, "needs_verification": 0, "skipped": 0}
            )
            run.jobs_expired = expire_past_deadline_jobs(db)
            errors = summary.get("errors", [])
            run.error_count = len(errors)
            source_names = [str(item.get("source", "source"))[:80] for item in errors[:10]]
            run.safe_error_summary = (
                f"Sources with errors: {', '.join(source_names)}" if source_names else ""
            )
            run.source_metrics = summary.get("source_metrics", [])
            if run.criteria_json and not run.companies_checked:
                run.companies_checked = len(
                    {
                        str(metric.get("company"))
                        for metric in run.source_metrics
                        if metric.get("company")
                    }
                )
            run.progress_json = {
                "sources_checked": run.sources_checked,
                "sources_total": int(summary.get("source_total", run.sources_checked)),
                "jobs_discovered": run.jobs_discovered,
                "verified": int(summary.get("verified_matches", 0)),
                "eligible": int(summary.get("eligible_matches", 0)),
                "duplicates_removed": int(summary.get("duplicates_removed", 0)),
                "guadalajara_metro": int(summary.get("guadalajara_metro_matches", 0)),
                "mexico_remote": int(summary.get("mexico_remote_matches", 0)),
                "latam_remote": int(summary.get("latam_remote_matches", 0)),
                "application_urls_verified": int(summary.get("application_urls_verified", 0)),
                "application_urls_missing": int(summary.get("application_urls_missing", 0)),
                "job_revalidation": revalidation,
            }
            if run.criteria_json:
                _store_search_results(db, run, summary)
                run.progress_json["verified"] = run.verified_count
                run.progress_json["eligible"] = run.eligible_count
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
        run = create_search_run(
            db, search_type=search_type, trigger=trigger,
            owner_user_id=settings.effective_primary_user_id,
        )
        run_id = run.id if run else None
    if run_id is None:
        _log("search_skipped_concurrent", search_type=search_type, trigger=trigger)
        return None
    await execute_search_run(run_id)
    with SessionLocal() as db:
        return db.get(SearchRun, run_id)
