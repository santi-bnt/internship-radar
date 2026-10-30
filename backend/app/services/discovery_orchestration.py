"""Staggered, budgeted orchestration over the existing discovery pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import CompanySource, Job


DISCOVERY_GROUPS = (
    "DIRECT", "GREENHOUSE", "LEVER", "WORKDAY", "SMARTRECRUITERS",
    "SEMICONDUCTOR", "SOFTWARE_CLOUD", "ROBOTICS_AUTOMOTIVE", "CANADA",
)
# Each group receives a different daily window.  The hour is configurable at
# deployment by changing the scheduler, while this map keeps the default plan
# inspectable and deterministic.
GROUP_HOURS = {group: index for index, group in enumerate(DISCOVERY_GROUPS)}
CANADA_CITIES = ("Toronto", "Vancouver", "Montreal", "Ottawa", "Waterloo", "Calgary", "Edmonton")
_GLOBAL_SEMAPHORE = asyncio.Semaphore(max(1, settings.discovery_global_concurrency))


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def source_domain(source: Any) -> str:
    return urlsplit(str(getattr(source, "source_url", ""))).netloc.lower() or str(
        getattr(source, "source_type", "unknown")
    ).lower()


def configured_group_hour(group: str) -> int:
    """Read optional `GROUP=HOUR` scheduler overrides from configuration."""
    for item in settings.discovery_group_hour_offsets.split(","):
        name, separator, raw_hour = item.strip().partition("=")
        if separator and name.strip().upper() == group:
            try:
                return max(0, min(23, int(raw_hour.strip())))
            except ValueError:
                break
    return GROUP_HOURS[group]


def source_group(source: Any) -> str:
    kind = str(getattr(source, "source_type", "")).lower()
    company = str(getattr(source, "company", "")).casefold()
    if "canada" in company:
        return "CANADA"
    if kind == "greenhouse":
        return "GREENHOUSE"
    if kind == "lever":
        return "LEVER"
    if kind == "workday":
        return "WORKDAY"
    if kind == "smartrecruiters":
        return "SMARTRECRUITERS"
    if any(term in company for term in ("intel", "micron", "amd", "nvidia", "qualcomm", "arm", "cadence", "synopsys", "nxp", "broadcom", "marvell")):
        return "SEMICONDUCTOR"
    if any(term in company for term in ("tesla", "rivian", "automotive", "bosch", "zoox", "spacex", "anduril", "zipline")):
        return "ROBOTICS_AUTOMOTIVE"
    if any(term in company for term in ("amazon", "google", "meta", "microsoft", "oracle", "cloudflare", "mongodb", "roblox", "duolingo")):
        return "SOFTWARE_CLOUD"
    return "DIRECT"


def stable_jitter_seconds(source: Any, *, max_seconds: int | None = None) -> int:
    """Stable per-source jitter avoids synchronized requests and test flakiness."""
    maximum = settings.discovery_jitter_seconds if max_seconds is None else max_seconds
    if maximum <= 0:
        return 0
    key = f"{getattr(source, 'id', '')}:{getattr(source, 'source_identifier', '')}".encode()
    return int(hashlib.sha256(key).hexdigest()[:8], 16) % (maximum + 1)


def refresh_interval_hours(source: Any) -> int:
    frequency = str(getattr(source, "refresh_frequency", "daily")).casefold()
    if frequency in {"hourly", "fast", "high"}:
        return 4
    if frequency in {"weekly", "slow"}:
        return 24 * 3
    return max(1, settings.discovery_group_interval_hours)


def source_is_due(source: Any, now: datetime) -> bool:
    for field in ("rate_limited_until", "backoff_until", "next_run_at"):
        value = _aware(getattr(source, field, None))
        if value and value > now:
            return False
    return bool(getattr(source, "enabled", False)) and not bool(getattr(source, "reference_only", False))


def select_group_sources(
    sources: list[Any],
    group: str,
    *,
    now: datetime,
    budget: int | None = None,
) -> list[Any]:
    """Pick a bounded, due queue; Canada gets its own non-starvable slice."""
    limit = budget if budget is not None else settings.discovery_source_batch_size
    matching = [
        source for source in sources
        if source_is_due(source, now)
        and (source_group(source) == group or (group == "CANADA" and "canada" in str(getattr(source, "geography_scope", "")).casefold()))
    ]
    matching.sort(key=lambda source: (
        _aware(getattr(source, "last_success_at", None)) or datetime.min.replace(tzinfo=timezone.utc),
        -int(getattr(source, "priority", 0) or 0),
        str(getattr(source, "company", "")),
    ))
    # refresh_all_sources is intentionally serial within a group.  The domain
    # cap additionally protects boards when a Canada coverage pass overlaps a
    # regular group window.
    selected: list[Any] = []
    domain_counts: dict[str, int] = {}
    per_domain_cap = max(1, settings.discovery_per_domain_concurrency)
    for source in matching:
        domain = source_domain(source)
        if domain_counts.get(domain, 0) >= per_domain_cap:
            continue
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        selected.append(source)
        if len(selected) >= max(0, limit):
            break
    return selected


def mark_source_success(source: Any, *, now: datetime) -> None:
    source.consecutive_failures = 0
    source.backoff_until = None
    source.rate_limited_until = None
    source.retry_after_seconds = None
    source.source_domain = source_domain(source)
    source.discovery_group = source_group(source)
    source.next_run_at = now + timedelta(
        hours=refresh_interval_hours(source), seconds=stable_jitter_seconds(source)
    )
    source.discovery_checkpoint_json = {"state": "complete", "updated_at": now.isoformat()}


def retry_after_seconds(exc: Exception, *, now: datetime) -> int | None:
    response = getattr(exc, "response", None)
    raw = getattr(response, "headers", {}).get("Retry-After") if response else None
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


def mark_source_failure(source: Any, exc: Exception, *, now: datetime) -> None:
    failures = max(1, int(getattr(source, "consecutive_failures", 0) or 0))
    source.source_domain = source_domain(source)
    source.discovery_group = source_group(source)
    wait = retry_after_seconds(exc, now=now)
    if wait is not None:
        source.retry_after_seconds = wait
        source.rate_limited_until = now + timedelta(seconds=wait)
        source.next_run_at = source.rate_limited_until
    else:
        delay = min(settings.discovery_retry_max_seconds, settings.discovery_retry_base_seconds * (2 ** (failures - 1)))
        source.backoff_until = now + timedelta(seconds=delay)
        source.next_run_at = source.backoff_until
    source.discovery_checkpoint_json = {"state": "retry", "updated_at": now.isoformat()}


async def run_discovery_group(group: str, trigger: str = "scheduler") -> dict[str, Any]:
    """Run one due group through refresh_all_sources; never all sources at once."""
    if group not in DISCOVERY_GROUPS:
        raise ValueError(f"Unknown discovery group: {group}")
    from app.jobs.refresh import refresh_all_sources

    init_db()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.info["owner_user_id"] = settings.effective_primary_user_id
        sources = list(db.scalars(select(CompanySource).where(CompanySource.enabled.is_(True))))
        selected = select_group_sources(sources, group, now=now)
        # Reserve selected records so overlapping scheduler invocations cannot
        # enqueue the same source before this group completes.
        for source in selected:
            source.discovery_group = source_group(source)
            source.source_domain = source_domain(source)
            source.next_run_at = now + timedelta(minutes=30)
            source.discovery_checkpoint_json = {"state": "running", "group": group, "trigger": trigger}
        db.commit()
        source_ids = {source.id for source in selected}
    if not source_ids:
        return {"group": group, "sources_checked": 0, "jobs_fetched": 0, "queued": 0}

    # The existing refresh function processes each selected source serially;
    # the global semaphore prevents concurrent group jobs from exceeding the
    # configurable small worker pool.
    async with _GLOBAL_SEMAPHORE:
        with SessionLocal() as db:
            db.info["owner_user_id"] = settings.effective_primary_user_id
            summary = await refresh_all_sources(db, source_ids=source_ids)
    return {"group": group, "queued": len(source_ids), **summary}


def discovery_status(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    sources = list(db.scalars(select(CompanySource)))
    by_group = {group: 0 for group in DISCOVERY_GROUPS}
    health = {"healthy": 0, "failing": 0, "rate_limited": 0}
    for source in sources:
        if not source.reference_only:
            by_group[source_group(source)] = by_group.get(source_group(source), 0) + 1
        state = str(getattr(source, "source_status", "")).upper()
        if state == "RATE_LIMITED": health["rate_limited"] += 1
        elif state in {"FAILING", "TEMPORARY_FAILURE", "PARSER_BROKEN", "BLOCKED"}: health["failing"] += 1
        else: health["healthy"] += 1
    today = now.date()
    jobs = list(db.scalars(select(Job).where(Job.first_seen_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc))))
    return {
        "groups": by_group,
        "health": health,
        "us_jobs_found_today": sum(1 for job in jobs if str(job.country).casefold() in {"united states", "usa", "us", "u.s."}),
        "canada_jobs_found_today": sum(1 for job in jobs if str(job.country).casefold() in {"canada", "can"}),
        "new_jobs_today": len(jobs),
        "next_group": min(DISCOVERY_GROUPS, key=lambda item: GROUP_HOURS[item]),
    }
