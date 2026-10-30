from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import CompanySource, Job, JobAnalysis, TargetCompany, UserProfile, ResumeProfile
from app.services.classification import (
    detect_recycled_posting,
    location_allowed,
    qualifies_priority_alert,
    urgency_label,
)
from app.services.application_urls import resolve_application_url
from app.services.dedupe import find_duplicate
from app.services.email_service import EmailService
from app.services.eligibility import apply_job_eligibility_signals, discovery_search_plan
from app.services.education_eligibility import apply_job_education_requirements
from app.services.special_program_eligibility import apply_job_special_program_signals
from app.services.scoring import analyze_job
from app.services.search_criteria import (
    is_guadalajara_metro,
    matches_discovery_criteria,
    matches_eligibility_criteria,
    select_sources_for_criteria,
)
from app.services.research_application_status import (
    apply_research_application_status,
    is_research_internship,
)
from app.services.job_revalidation import is_revalidation_due, revalidate_job
from app.services.verification import verify_official_application
from app.services.seed import seed_profile_and_sources
from app.services.target_companies import normalize_company_name, priority_bonus
from app.services.user_priority import is_user_priority_pinned
from app.sources.workday import WorkdayAdapter
from app.services.discovery_orchestration import mark_source_failure, mark_source_success
from app.services.force_apply import apply_requested_santiago_overrides
from app.sources import create_adapter
from app.sources.community import repository_health


logger = logging.getLogger(__name__)

SOURCE_HEALTH_STATES = {
    "HEALTHY", "DEGRADED", "AUTH_REQUIRED", "RATE_LIMITED", "PARSER_BROKEN",
    "PORTAL_CHANGED", "REDIRECT_CHANGED", "BLOCKED", "NOT_FOUND",
    "TEMPORARY_FAILURE", "UNSUPPORTED",
}


def classify_source_failure(exc: Exception) -> tuple[str, int | None, str]:
    """Return a stable, safe health state without exposing response bodies or secrets."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    message = str(exc).lower()
    if status in {401} or "unauthorized" in message:
        return "AUTH_REQUIRED", status, "The source requires authentication."
    if status in {403} or "forbidden" in message or "captcha" in message:
        return "BLOCKED", status, "Automated access was restricted; the source may still work in a browser."
    if status == 429 or "rate limit" in message:
        return "RATE_LIMITED", status, "The source rate limit was reached."
    if status in {404, 410}:
        return "NOT_FOUND", status, "The configured source endpoint was not found."
    if status in {502, 503, 504} or any(term in message for term in ("timeout", "timed out", "temporary")):
        return "TEMPORARY_FAILURE", status, "The source had a temporary network or server failure."
    if "no fetch adapter" in message or "unsupported" in message:
        return "UNSUPPORTED", status, "No supported adapter is configured for this source."
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "PARSER_BROKEN", status, "The source response no longer matches the parser."
    if any(term in message for term in ("no internship links", "require javascript", "exposed no")):
        return "PORTAL_CHANGED", status, "The portal no longer exposes listings in the form expected by this adapter."
    if "redirect" in message:
        return "REDIRECT_CHANGED", status, "The source redirect no longer resolves as expected."
    return "DEGRADED", status, f"Source refresh failed ({type(exc).__name__})."


async def collect_with_retry(adapter: Any, attempts: int = 3) -> list[Any]:
    for attempt in range(attempts):
        try:
            return await adapter.collect()
        except Exception as exc:
            state, status, _ = classify_source_failure(exc)
            # A 429 has an explicit server policy and must be scheduled using
            # Retry-After rather than retried immediately in this worker.
            if state != "TEMPORARY_FAILURE" or attempt == attempts - 1:
                raise
            await asyncio.sleep(0.5 * (2 ** attempt))
    return []


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
    verified_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == profile.owner_user_id))
    result = analyze_job(job, profile, verified_profile).to_dict()
    if job.analysis:
        for key, value in result.items():
            setattr(job.analysis, key, value)
        analysis = job.analysis
    else:
        analysis = JobAnalysis(job=job, **result)
        db.add(analysis)

    # Research application state is independent from fit scoring. It may change
    # only the candidate-facing recommendation and lifecycle state after the
    # normal score has been persisted.
    apply_research_application_status(job, analysis)

    qualifies = qualifies_priority_alert(job, profile, result)
    pinned = is_user_priority_pinned(job) and job.status in {"active", "saved"} and job.is_active and job.official_status == "open" and job.verification_status == "verified"
    job.is_priority_alert = qualifies or pinned
    if qualifies and job.priority_alerted_at is None:
        job.priority_alerted_at = datetime.now(timezone.utc)
    return analysis


async def _revalidate_jobs(
    db: Session,
    *,
    jobs: list[Job],
    owner_user_id: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Revalidate due stored jobs with their official company/ATS URL.

    This runs independently from discovery, so a job may remain historically
    saved even when its old application link has now closed.
    """
    profiles: dict[str, UserProfile] = {}
    summary = {"checked": 0, "open": 0, "expired": 0, "needs_verification": 0, "skipped": 0}

    now = datetime.now(timezone.utc)
    def priority(job: Job) -> tuple[int, int, int, float, float]:
        analysis = getattr(job, "analysis", None)
        recommendation = getattr(analysis, "recommendation", "") if analysis else ""
        apply_now = 0 if recommendation in {"Apply Now", "Apply Today"} else 1
        deadline = getattr(job, "application_deadline", None)
        deadline_days = (deadline - now.date()).days if deadline else 9999
        failed = 0 if getattr(job, "verification_status", "") in {"verification_failed", "partially_verified", "unverified"} else 1
        first_seen = getattr(job, "first_seen_at", None)
        first_seen_timestamp = first_seen.timestamp() if first_seen else 0.0
        checked_at = getattr(job, "last_checked_at", None)
        checked_timestamp = checked_at.timestamp() if checked_at else 0.0
        # More recently discovered roles are rechecked earlier; stale checks
        # still win the final tie-breaker so long-lived jobs are not starved.
        return (apply_now, max(-9999, deadline_days), failed, -first_seen_timestamp, checked_timestamp)

    for job in sorted(jobs, key=priority):
        if summary["checked"] >= settings.job_revalidation_batch_size and not force:
            summary["skipped"] += 1
            continue
        if not is_revalidation_due(
            job,
            now=now,
            interval_hours=settings.verify_jobs_interval_hours,
            retry_minutes=settings.job_revalidation_retry_minutes,
            deadline_window_hours=settings.job_revalidation_deadline_window_hours,
            force=force,
        ):
            summary["skipped"] += 1
            continue
        summary["checked"] += 1
        workday_state = await _refresh_hpe_workday_posting(job)
        if workday_state is not None:
            # An exact Workday requisition response contains the current
            # posting, its active application state, and the authoritative
            # content. Avoid a second page-only request that cannot enrich it.
            outcome_state = workday_state
        else:
            outcome = await revalidate_job(job, verify_official_application, now=now)
            outcome_state = outcome.state
        if outcome_state == "open":
            summary["open"] += 1
        elif outcome_state == "expired":
            summary["expired"] += 1
        else:
            summary["needs_verification"] += 1

        profile = profiles.get(job.owner_user_id)
        if profile is None:
            profile = db.scalar(
                select(UserProfile).where(UserProfile.owner_user_id == job.owner_user_id)
            )
            if profile is not None:
                profiles[job.owner_user_id] = profile
        if profile is None:
            continue
        persist_analysis(db, job, profile)

    db.commit()
    return summary


async def _refresh_hpe_workday_posting(job: Job) -> str | None:
    """Refresh HPE content from its exact official Workday requisition.

    A successful exact-ID response is authoritative for both current status
    and posting content. Existing Job rows are enriched in place through the
    common merge routine, preserving candidate application state and related
    records such as overrides, notes, and generated resume history.
    """
    company = str(getattr(job, "company", "") or "").strip().casefold()
    if company not in {"hewlett packard enterprise", "hpe"}:
        return None
    official_url = str(
        getattr(job, "official_apply_url", "")
        or getattr(job, "canonical_official_url", "")
        or getattr(job, "posting_url", "")
        or ""
    ).casefold()
    if "hpe.wd5.myworkdayjobs.com" not in official_url:
        return None
    requisition_ids = {
        str(value).strip()
        for value in (
            getattr(job, "ats_requisition_id", ""),
            getattr(job, "external_id", ""),
        )
        if str(value or "").strip()
    }
    requisition_ids = {value for value in requisition_ids if value.isdigit()}
    if not requisition_ids:
        return None

    adapter = WorkdayAdapter(
        "Hewlett Packard Enterprise",
        "hpe|Jobsathpe",
        "https://hpe.wd5.myworkdayjobs.com/Jobsathpe",
    )
    try:
        records = await adapter.fetch_exact_public_ids(requisition_ids, require_all=False)
    except Exception as exc:
        logger.info("HPE Workday content refresh failed for job %s: %s", job.id, type(exc).__name__)
        return None
    raw = next(
        (item for item in records if str(item.get("jobReqId") or item.get("jobRequisitionId") or "") in requisition_ids),
        None,
    )
    if raw is None:
        return None
    normalized = adapter.normalize_job(raw)
    if not normalized.external_id or str(normalized.external_id) not in requisition_ids:
        return None

    _merge_duplicate(job, normalized.to_dict())
    if normalized.official_status == "open" and normalized.verification_status == "verified":
        return "open"
    if normalized.official_status in {"closed", "expired", "unavailable"}:
        job.status = "expired"
        job.is_active = False
        job.expired_at = datetime.now(timezone.utc)
        job.application_url_status = "INACTIVE"
        job.application_url_diagnostic = "OFFICIAL_POSTING_CLOSED"
        return "expired"
    return None


async def revalidate_existing_jobs(
    db: Session,
    *,
    owner_user_id: str | None = None,
    force: bool = False,
    job_id: int | None = None,
) -> dict[str, int]:
    """Recheck persisted active/saved jobs; discovery is not required."""
    query = select(Job).where(Job.status.in_(("active", "saved"))).options(joinedload(Job.analysis))
    if owner_user_id:
        query = query.where(Job.owner_user_id == owner_user_id)
    if job_id is not None:
        query = query.where(Job.id == job_id)
    jobs = list(db.scalars(query))
    return await _revalidate_jobs(
        db,
        jobs=jobs,
        owner_user_id=owner_user_id,
        force=force,
    )


async def verify_research_openings(
    db: Session,
    *,
    owner_user_id: str | None = None,
) -> dict[str, int]:
    """Compatibility wrapper for the US-Research verification scheduler pass."""
    query = select(Job).where(Job.status.in_(("active", "saved")))
    if owner_user_id:
        query = query.where(Job.owner_user_id == owner_user_id)
    jobs = [job for job in db.scalars(query) if is_research_internship(job)]
    summary = await _revalidate_jobs(db, jobs=jobs, owner_user_id=owner_user_id)
    return {key: summary[key] for key in ("checked", "open", "expired", "needs_verification")}


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
        if key == "raw_data" and isinstance(new_value, dict) and is_user_priority_pinned(job):
            new_value = {**new_value, "_radar_user_priority": job.raw_data["_radar_user_priority"]}
        if key == "raw_data" and isinstance(new_value, dict):
            revalidation_history = list((job.raw_data or {}).get("_radar_revalidation_history") or [])
            if revalidation_history:
                new_value = {**new_value, "_radar_revalidation_history": revalidation_history}
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
    # Discovery facts may change, but an application is user history, not
    # source metadata. Reimporting an already-applied requisition must update
    # its canonical/source fields without putting it back in the job queue.
    preserve_application_state = str(job.status or "").casefold() == "applied"
    application_state = {
        "status": job.status,
        "is_active": job.is_active,
        "applied_at": job.applied_at,
        "submitted_resume_id": job.submitted_resume_id,
    } if preserve_application_state else None
    original_discovery_source = job.discovered_from_source
    original_discovery_sources = list(job.discovery_sources or [])
    original_markers = list(job.community_markers or [])
    if getattr(job, "status", None) == "applied":
        data = {
            **data,
            "status": "applied",
            "applied_at": getattr(job, "applied_at", None) or data.get("applied_at"),
        }
    _update_job(job, data)
    job.discovered_from_source = original_discovery_source or data.get("discovered_from_source", "")
    job.discovery_sources = original_discovery_sources
    job.community_markers = original_markers
    if application_state is not None:
        for field, value in application_state.items():
            setattr(job, field, value)


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
    criteria: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
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
    sources = select_sources_for_criteria(sources, criteria, targets)
    # Every entry point, including the manual trigger, has a bounded source
    # budget.  Remaining due records keep their checkpoint and run later.
    source_budget = max(1, settings.discovery_source_batch_size)
    queued_sources = sources[source_budget:]
    sources = sources[:source_budget]
    target_company_names = [
        name
        for target in targets
        for name in (target.company_name, *(target.aliases or []))
        if name
    ]
    existing = list(db.scalars(select(Job)))
    summary: dict[str, Any] = {
        "sources_checked": 0,
        "jobs_fetched": 0,
        "jobs_created": 0,
        "jobs_updated": 0,
        "jobs_closed": 0,
        "jobs_ignored": 0,
        "priority_alerts": 0,
        "source_total": len(sources),
        "sources_queued": len(queued_sources),
        "criteria_rejected": 0,
        "eligibility_excluded": 0,
        "duplicates_removed": 0,
        "verified_matches": 0,
        "eligible_matches": 0,
        "guadalajara_metro_matches": 0,
        "mexico_remote_matches": 0,
        "latam_remote_matches": 0,
        "application_urls_verified": 0,
        "application_urls_missing": 0,
        "matched_jobs": {},
        "errors": [],
        "discovery_plan": discovery_search_plan(),
        "source_metrics": [],
        "manual_overrides_enabled": 0,
    }
    logger.info(json.dumps({"event": "discovery_plan", **summary["discovery_plan"]}))
    if progress_callback:
        progress_callback(summary)

    for source in sources:
        source_started = time.perf_counter()
        attempted_at = datetime.now(timezone.utc)
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
        source.last_attempt_at = attempted_at
        try:
            logger.info(json.dumps({
                "event": "source_started",
                "company": source_company,
                "source_type": source.source_type,
            }))
            adapter = create_adapter(source, search_criteria=criteria)
            normalized_jobs = await collect_with_retry(adapter)
            summary["jobs_fetched"] += len(normalized_jobs)
            for normalized in normalized_jobs:
                data = normalized.to_dict()
                from app.services.talent_communities import is_talent_community, store_discovered_community
                if is_talent_community(data["title"], data.get("apply_url", "")):
                    store_discovered_community(db, profile.owner_user_id, data)
                    continue
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
                url_resolution = resolve_application_url(data)
                data.update(
                    posting_url=url_resolution.posting_url,
                    application_url=url_resolution.application_url,
                    application_url_source=url_resolution.source,
                    application_url_status=url_resolution.status,
                    application_url_last_verified_at=url_resolution.verified_at,
                    application_url_diagnostic=url_resolution.diagnostic,
                )
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
                matched, matched_criteria = matches_discovery_criteria(
                    data,
                    criteria,
                    target_company_names,
                )
                if not matched:
                    summary["criteria_rejected"] += 1
                    continue
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
                    data["owner_user_id"] = profile.owner_user_id
                    job = Job(**data)
                    db.add(job)
                    db.flush()
                    existing.append(job)
                    is_new = True
                    summary["jobs_created"] += 1
                seen_job_ids.add(job.id)
                persist_analysis(db, job, profile)
                if matches_eligibility_criteria(job, criteria) and job.status in {"active", "saved"}:
                    first_match = str(job.id) not in summary["matched_jobs"]
                    summary["matched_jobs"][str(job.id)] = {
                        "discovered_during_run": is_new,
                        "matched_criteria": matched_criteria,
                    }
                    eligibility = (
                        job.analysis.eligibility_status if job.analysis else "UNKNOWN"
                    )
                    if first_match and eligibility in {"ELIGIBLE", "LIKELY_ELIGIBLE"}:
                        summary["eligible_matches"] += 1
                    if first_match and job.verification_status in {"verified", "partially_verified"}:
                        summary["verified_matches"] += 1
                    if first_match and is_guadalajara_metro(f"{job.location} {job.city} {job.region}"):
                        summary["guadalajara_metro_matches"] += 1
                    if first_match and job.remote_scope == "MEXICO":
                        summary["mexico_remote_matches"] += 1
                    if first_match and job.remote_scope == "LATAM":
                        summary["latam_remote_matches"] += 1
                    if first_match and job.application_url_status == "VERIFIED":
                        summary["application_urls_verified"] += 1
                    elif first_match and not job.application_url:
                        summary["application_urls_missing"] += 1
                elif criteria is not None:
                    summary["eligibility_excluded"] += 1
                if job.verification_status in {"verified", "partially_verified"}:
                    source_verified += 1
                else:
                    source_unverified += 1
                notification_events.append((job.id, is_new, previous_state))
                if job.is_priority_alert:
                    summary["priority_alerts"] += 1

            source_jobs = (
                list(db.scalars(select(Job).where(Job.source_url == source.source_url)))
                if criteria is None
                else []
            )
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
            source.last_success_at = datetime.now(timezone.utc)
            source.last_error_type = ""
            source.safe_error_message = ""
            source.http_status = None
            source.consecutive_failures = 0
            source.last_successful_fetch = datetime.now(timezone.utc)
            source.last_successful_parse = datetime.now(timezone.utc)
            adapter_repository_update = getattr(adapter, "last_repository_update", None)
            if adapter_repository_update:
                source.last_repository_update = adapter_repository_update
            if summary["jobs_created"] > before_created:
                source.last_new_job_seen = datetime.now(timezone.utc)
            repository_status, source.priority = repository_health(
                source.last_repository_update if source.registry_type in {"COMMUNITY_REPO", "AGGREGATOR"} else None,
                source.base_priority,
                datetime.now(timezone.utc),
                stale_days=settings.community_source_stale_days,
            )
            source.source_status = "HEALTHY" if repository_status == "ACTIVE" else "DEGRADED"
            mark_source_success(source, now=datetime.now(timezone.utc))
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
            failure_state, http_status, safe_message = classify_source_failure(exc)
            # rollback expires ORM state, including the timestamp assigned before
            # the request. Reapply it so failed attempts remain observable.
            source.last_attempt_at = attempted_at
            source.last_status = "Error"
            source.last_error = safe_message
            source.error_count = int(source.error_count or 0) + 1
            source.source_status = failure_state
            source.last_error_at = datetime.now(timezone.utc)
            source.last_error_type = failure_state
            source.safe_error_message = safe_message
            source.http_status = http_status
            source.consecutive_failures = int(source.consecutive_failures or 0) + 1
            mark_source_failure(source, exc, now=datetime.now(timezone.utc))
            summary["errors"].append({"source": source_company, "type": failure_state, "error": safe_message})
            logger.warning(json.dumps({
                "event": "source_failed",
                "company": source_company,
                "source_type": source.source_type,
                "safe_error": type(exc).__name__,
            }))
        source.last_attempt_at = attempted_at
        source.last_refresh_at = datetime.now(timezone.utc)
        duration_ms = round((time.perf_counter() - source_started) * 1000)
        source.fetched_count = int(getattr(adapter, "fetched_count", 0) or len(normalized_jobs))
        source.parsed_count = len(normalized_jobs)
        source.new_jobs_count = summary["jobs_created"] - before_created
        source.updated_jobs_count = summary["jobs_updated"] - before_updated
        source.duplicate_count = source_duplicates
        summary["duplicates_removed"] += source_duplicates
        source.officially_verified_count = source_verified
        source.unverified_count = source_unverified
        source.jobs_discovered = len(normalized_jobs)
        source.jobs_verified = source_verified
        source.duration_ms = duration_ms
        metric = {
            "source_id": source.id,
            "source": source.company,
            "company": source.company,
            "state": source.source_status,
            "last_error_type": source.last_error_type,
            "safe_error_message": source.safe_error_message,
            "http_status": source.http_status,
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
        if progress_callback:
            progress_callback(summary)
        _dispatch_notifications(db, profile, notification_events)
        if settings.source_rate_limit_seconds:
            await asyncio.sleep(settings.source_rate_limit_seconds)

    # The explicit Santiago-only override catalog is not a one-time migration
    # concern: a matching official job can be discovered after deployment.
    # Sync it after normal normalization/verification, never before, so a
    # closed or unavailable posting cannot be revived by the manual action.
    enabled_overrides = apply_requested_santiago_overrides(
        db,
        profile.owner_user_id,
        commit=False,
    )
    summary["manual_overrides_enabled"] = len(enabled_overrides)
    if enabled_overrides:
        db.commit()
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
