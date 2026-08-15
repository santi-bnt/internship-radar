from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import CompanySource, Job, JobAnalysis, TargetCompany, UserProfile
from app.services.classification import (
    detect_recycled_posting,
    location_allowed,
    qualifies_priority_alert,
    urgency_label,
)
from app.services.dedupe import find_duplicate
from app.services.email_service import EmailService
from app.services.eligibility import apply_job_eligibility_signals, discovery_search_plan
from app.services.education_eligibility import apply_job_education_requirements
from app.services.special_program_eligibility import apply_job_special_program_signals
from app.services.scoring import analyze_job
from app.services.seed import seed_profile_and_sources
from app.services.target_companies import normalize_company_name, priority_bonus
from app.sources import create_adapter
from app.sources.community import repository_health


logger = logging.getLogger(__name__)


def _job_state(job: Job | None) -> dict[str, str | None]:
    if job is None:
        return {
            "official_status": None,
            "verification_status": None,
            "recommendation": None,
        }
    return {
        "official_status": job.official_status,
        "verification_status": job.verification_status,
        "recommendation": job.analysis.recommendation if job.analysis else None,
    }


def _dispatch_notifications(
    db: Session,
    profile: UserProfile,
    events: list[tuple[int, bool, dict[str, str | None]]],
) -> None:
    if not events:
        return
    try:
        service = EmailService(db)
    except Exception:
        logger.error("Email provider initialization failed; job refresh remains complete.")
        return
    for job_id, is_new, previous_state in events:
        try:
            job = db.scalar(
                select(Job)
                .where(Job.id == job_id)
                .options(joinedload(Job.analysis))
            )
            if job:
                service.dispatch_job_notifications(
                    job,
                    profile,
                    is_new=is_new,
                    previous_state=previous_state,
                )
        except Exception:
            db.rollback()
            logger.error(
                "Notification processing failed for job %s; job refresh remains complete.",
                job_id,
            )


def persist_analysis(db: Session, job: Job, profile: UserProfile) -> JobAnalysis:
    apply_job_eligibility_signals(job)
    apply_job_education_requirements(job)
    apply_job_special_program_signals(job)
    recycled, recycled_reason = detect_recycled_posting(job)
    job.recycled_posting = recycled
    if recycled and recycled_reason and recycled_reason not in job.status_reason:
        job.status_reason = f"{job.status_reason} {recycled_reason}".strip()
    job.urgency = urgency_label(job)
    result = analyze_job(job, profile).to_dict()
    if job.analysis:
        for key, value in result.items():
            setattr(job.analysis, key, value)
        analysis = job.analysis
    else:
        analysis = JobAnalysis(job=job, **result)
        db.add(analysis)

    qualifies = qualifies_priority_alert(job, profile, result)
    job.is_priority_alert = qualifies
    if qualifies and job.priority_alerted_at is None:
        job.priority_alerted_at = datetime.now(timezone.utc)
    return analysis


def _update_job(job: Job, data: dict[str, Any]) -> None:
    derived_fields = {
        "is_priority_alert",
        "priority_alerted_at",
        "urgency",
        "recycled_posting",
        "verification_failures",
    }
    for key, new_value in data.items():
        if key in derived_fields:
            continue
        if key in {
            "raw_data",
            "raw_data_hash",
            "posted_at",
            "is_active",
            "official_apply_url",
        } or new_value not in (None, ""):
            setattr(job, key, new_value)
    job.last_seen_at = datetime.now(timezone.utc)
    job.last_checked_at = datetime.now(timezone.utc)
    job.missing_refreshes = 0


def _official_candidate(data: dict[str, Any]) -> bool:
    return bool(
        data.get("official_apply_url")
        or (
            data.get("official_status") == "open"
            and data.get("verification_status") == "verified"
        )
    )


def _merge_duplicate(job: Job, data: dict[str, Any]) -> None:
    alternate = {
        "source_name": data.get("source_name", ""),
        "source_url": data.get("source_url", ""),
        "apply_url": data.get("apply_url", ""),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }
    alternatives = list(job.alternate_sources or [])
    if alternate["apply_url"] and not any(
        item.get("apply_url") == alternate["apply_url"] for item in alternatives
    ):
        alternatives.append(alternate)
        job.alternate_sources = alternatives
    source_names = list(job.discovery_sources or [])
    for source_name in data.get("discovery_sources") or [data.get("discovered_from_source")]:
        if source_name and source_name not in source_names:
            source_names.append(source_name)
    job.discovery_sources = source_names
    markers = list(job.community_markers or [])
    for marker in data.get("community_markers") or []:
        if marker not in markers:
            markers.append(marker)
    job.community_markers = markers
    if not job.discovered_from_source:
        job.discovered_from_source = data.get("discovered_from_source", "")
    existing_official = bool(
        job.official_apply_url
        or (job.official_status == "open" and job.verification_status == "verified")
    )
    if existing_official and not _official_candidate(data):
        job.last_seen_at = datetime.now(timezone.utc)
        job.last_checked_at = datetime.now(timezone.utc)
        job.missing_refreshes = 0
        return
    original_discovery_source = job.discovered_from_source
    original_discovery_sources = list(job.discovery_sources or [])
    original_markers = list(job.community_markers or [])
    _update_job(job, data)
    job.discovered_from_source = original_discovery_source or data.get("discovered_from_source", "")
    job.discovery_sources = original_discovery_sources
    job.community_markers = original_markers


def _apply_verification_failures(existing: Job | None, data: dict[str, Any]) -> None:
    status = data.get("verification_status", "unverified")
    official_status = data.get("official_status", "unknown")
    if official_status in {"closed", "expired", "unavailable"}:
        data["is_active"] = False
        data["verification_failures"] = 0
        return
    if status == "verified" and official_status == "open":
        data["verification_failures"] = 0
        return

    failures = (existing.verification_failures if existing else 0) + 1
    data["verification_failures"] = failures
    base_reason = data.get("status_reason") or "The official application could not be confirmed."
    if failures == 1:
        data["status_reason"] = f"Needs Verification: {base_reason}"
    elif failures == 2:
        data["status_reason"] = f"Probably Closed: {base_reason}"
    else:
        data["official_status"] = "unavailable"
        data["verification_status"] = "verification_failed"
        data["is_active"] = False
        data["status_reason"] = "Closed after three consecutive official verification failures."


async def refresh_all_sources(
    db: Session,
    source_types: set[str] | None = None,
    source_ids: set[int] | None = None,
) -> dict[str, Any]:
    profile = db.scalar(select(UserProfile).limit(1))
    if profile is None:
        raise RuntimeError("Profile must be seeded before refreshing jobs")

    sources = list(db.scalars(select(CompanySource).where(
        CompanySource.enabled.is_(True),
        CompanySource.reference_only.is_(False),
    )))
    registry_order = {
        "OFFICIAL_COMPANY": 6, "OFFICIAL_ATS": 5, "COMMUNITY_REPO": 3,
        "AGGREGATOR": 2, "JOB_BOARD": 1, "UNIVERSITY_BOARD": 1, "OTHER": 0,
    }
    sources.sort(key=lambda item: (registry_order.get(item.registry_type, 0), item.priority), reverse=True)
    if source_types is not None:
        sources = [source for source in sources if source.source_type in source_types]
    if source_ids is not None:
        sources = [source for source in sources if source.id in source_ids]
    targets = list(db.scalars(select(TargetCompany).where(TargetCompany.enabled.is_(True))))
    existing = list(db.scalars(select(Job)))
    summary: dict[str, Any] = {
        "sources_checked": 0,
        "jobs_fetched": 0,
        "jobs_created": 0,
        "jobs_updated": 0,
        "jobs_closed": 0,
        "jobs_ignored": 0,
        "priority_alerts": 0,
        "errors": [],
        "discovery_plan": discovery_search_plan(),
        "source_metrics": [],
    }
    logger.info(json.dumps({"event": "discovery_plan", **summary["discovery_plan"]}))

    for source in sources:
        source_started = time.perf_counter()
        adapter = None
        normalized_jobs: list[Any] = []
        source_company = source.company
        before_created = summary["jobs_created"]
        before_updated = summary["jobs_updated"]
        before_ignored = summary["jobs_ignored"]
        source_duplicates = 0
        source_verified = 0
        source_unverified = 0
        summary["sources_checked"] += 1
        seen_job_ids: set[int] = set()
        notification_events: list[tuple[int, bool, dict[str, str | None]]] = []
        try:
            logger.info(json.dumps({
                "event": "source_started",
                "company": source_company,
                "source_type": source.source_type,
            }))
            adapter = create_adapter(source)
            normalized_jobs = await adapter.collect()
            summary["jobs_fetched"] += len(normalized_jobs)
            for normalized in normalized_jobs:
                data = normalized.to_dict()
                data["source_confidence_score"] = max(
                    float(data.get("source_confidence_score") or 0),
                    float(source.source_confidence_score or 0),
                )
                data["discovered_from_source"] = data.get("discovered_from_source") or normalized.source_name
                data["discovery_sources"] = list(dict.fromkeys(
                    [*(data.get("discovery_sources") or []), normalized.source_name]
                ))
                if (
                    source.registry_type in {"OFFICIAL_COMPANY", "OFFICIAL_ATS"}
                    and data.get("verification_status") in {"verified", "partially_verified"}
                ):
                    data["verified_from_source"] = data.get("verified_from_source") or normalized.source_name
                if data.get("expires_at"):
                    data["application_deadline"] = data["expires_at"].date()
                    data["deadline_source"] = "structured_source"
                    data["deadline_confidence"] = 1.0
                if normalized.company in {"", "MVP test feed"}:
                    raw_company = normalized.raw_data.get("company")
                    if raw_company:
                        data["company"] = raw_company
                canonical_company, target = normalize_company_name(data["company"], targets)
                data["company"] = canonical_company
                data["discovered_from"] = source.source_type
                application_url = data.get("official_apply_url") or data.get("apply_url") or ""
                data["official_domain"] = (
                    urlsplit(application_url).netloc.lower()
                    if _official_candidate(data)
                    else ""
                )
                if target:
                    data["is_target_company"] = True
                    data["target_company_category"] = target.category
                    data["company_priority"] = target.priority
                    data["company_priority_bonus"] = priority_bonus(
                        target.priority,
                        _official_candidate(data),
                        data.get("verification_status") == "verified",
                    )
                duplicate = find_duplicate(existing, data)
                allowed, _ = location_allowed(data, profile)
                if not allowed:
                    summary["jobs_ignored"] += 1
                    continue
                previous_state = _job_state(duplicate)
                _apply_verification_failures(duplicate, data)
                official_status = data.get("official_status")
                if duplicate is None and official_status == "expired":
                    data["status"] = "expired"
                    data["expired_at"] = datetime.now(timezone.utc)
                elif duplicate is None and official_status in {"closed", "unavailable"}:
                    data["status"] = "archived"
                    data["archived_at"] = datetime.now(timezone.utc)
                elif duplicate is None and data.get("discovery_status") == "community_closed":
                    data["status"] = "archived"
                    data["archived_at"] = datetime.now(timezone.utc)
                if duplicate and duplicate.status in {"active", "saved"}:
                    if official_status == "expired":
                        duplicate.status = "expired"
                        duplicate.expired_at = datetime.now(timezone.utc)
                    elif official_status in {"closed", "unavailable"}:
                        duplicate.status = "archived"
                        duplicate.archived_at = datetime.now(timezone.utc)
                if duplicate:
                    source_duplicates += 1
                    _merge_duplicate(duplicate, data)
                    job = duplicate
                    is_new = False
                    summary["jobs_updated"] += 1
                else:
                    job = Job(**data)
                    db.add(job)
                    db.flush()
                    existing.append(job)
                    is_new = True
                    summary["jobs_created"] += 1
                seen_job_ids.add(job.id)
                persist_analysis(db, job, profile)
                if job.verification_status in {"verified", "partially_verified"}:
                    source_verified += 1
                else:
                    source_unverified += 1
                notification_events.append((job.id, is_new, previous_state))
                if job.is_priority_alert:
                    summary["priority_alerts"] += 1

            source_jobs = list(db.scalars(select(Job).where(Job.source_url == source.source_url)))
            for job in source_jobs:
                if job.id not in seen_job_ids and job.is_active:
                    previous_state = _job_state(job)
                    job.missing_refreshes += 1
                    job.last_checked_at = datetime.now(timezone.utc)
                    job.official_status = "unknown"
                    job.verification_status = "unverified"
                    if job.missing_refreshes == 1:
                        job.status_reason = "Needs Verification: the job disappeared from its official board once."
                    elif job.missing_refreshes == 2:
                        job.status_reason = "Probably Closed: the job disappeared from its official board twice."
                    if job.missing_refreshes >= settings.missing_refreshes_before_close:
                        job.is_active = False
                        if job.status in {"active", "saved"}:
                            job.status = "archived"
                            job.archived_at = datetime.now(timezone.utc)
                        job.official_status = "unavailable"
                        job.verification_status = "verification_failed"
                        job.status_reason = "Closed after disappearing from the official board three times."
                        persist_analysis(db, job, profile)
                        notification_events.append((job.id, False, previous_state))
                        summary["jobs_closed"] += 1
                    else:
                        persist_analysis(db, job, profile)
                        notification_events.append((job.id, False, previous_state))

            source.last_status = "OK"
            source.last_error = None
            source.error_count = 0
            source.last_successful_fetch = datetime.now(timezone.utc)
            source.last_successful_parse = datetime.now(timezone.utc)
            adapter_repository_update = getattr(adapter, "last_repository_update", None)
            if adapter_repository_update:
                source.last_repository_update = adapter_repository_update
            if summary["jobs_created"] > before_created:
                source.last_new_job_seen = datetime.now(timezone.utc)
            source.source_status, source.priority = repository_health(
                source.last_repository_update if source.registry_type in {"COMMUNITY_REPO", "AGGREGATOR"} else None,
                source.base_priority,
                datetime.now(timezone.utc),
                stale_days=settings.community_source_stale_days,
            )
            logger.info(json.dumps({
                "event": "source_completed",
                "company": source_company,
                "source_type": source.source_type,
                "jobs_found": len(normalized_jobs),
                "jobs_added": summary["jobs_created"] - before_created,
                "jobs_updated": summary["jobs_updated"] - before_updated,
            }))
        except Exception as exc:
            db.rollback()
            source.last_status = "Error"
            source.last_error = str(exc)[:1000]
            source.error_count = int(source.error_count or 0) + 1
            source.source_status = "RATE_LIMITED" if "rate limit" in str(exc).lower() else "ERROR"
            summary["errors"].append({"source": source_company, "error": str(exc)})
            logger.warning(json.dumps({
                "event": "source_failed",
                "company": source_company,
                "source_type": source.source_type,
                "safe_error": type(exc).__name__,
            }))
        source.last_refresh_at = datetime.now(timezone.utc)
        duration_ms = round((time.perf_counter() - source_started) * 1000)
        source.fetched_count = int(getattr(adapter, "fetched_count", 0) or len(normalized_jobs))
        source.parsed_count = len(normalized_jobs)
        source.new_jobs_count = summary["jobs_created"] - before_created
        source.updated_jobs_count = summary["jobs_updated"] - before_updated
        source.duplicate_count = source_duplicates
        source.officially_verified_count = source_verified
        source.unverified_count = source_unverified
        source.duration_ms = duration_ms
        metric = {
            "source_id": source.id,
            "source": source.company,
            "fetched_count": source.fetched_count,
            "parsed_count": source.parsed_count,
            "new_jobs": source.new_jobs_count,
            "updated_jobs": source.updated_jobs_count,
            "duplicates": source.duplicate_count,
            "officially_verified": source.officially_verified_count,
            "unverified": source.unverified_count,
            "errors": 1 if source.last_status == "Error" else 0,
            "duration_ms": duration_ms,
            "ignored": summary["jobs_ignored"] - before_ignored,
        }
        summary["source_metrics"].append(metric)
        db.commit()
        _dispatch_notifications(db, profile, notification_events)
        if settings.source_rate_limit_seconds:
            await asyncio.sleep(settings.source_rate_limit_seconds)

    return summary


async def run_refresh(source_types: set[str] | None = None) -> dict[str, Any]:
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        return await refresh_all_sources(db, source_types=source_types)


def main() -> None:
    summary = asyncio.run(run_refresh())
    print(
        "Refresh complete: "
        f"{summary['sources_checked']} sources, "
        f"{summary['jobs_fetched']} fetched, "
        f"{summary['jobs_created']} created, "
        f"{summary['jobs_updated']} updated, "
        f"{summary['jobs_ignored']} ignored by location, "
        f"{summary['jobs_closed']} closed, "
        f"{summary['priority_alerts']} priority alerts, "
        f"{len(summary['errors'])} errors."
    )


if __name__ == "__main__":
    main()
