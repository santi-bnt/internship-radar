from __future__ import annotations

from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Job


JOB_STATUSES = frozenset(
    {"active", "saved", "applied", "expired", "not_interested", "archived"}
)
ACTIVE_JOB_STATUSES = ("active", "saved")
AUTOMATIC_DEADLINE_CONFIDENCE = 0.8
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def configured_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.user_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def expire_past_deadline_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Expire active jobs only after their deadline's local calendar day has ended."""
    current_utc = now or utc_now()
    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)
    local_date = current_utc.astimezone(configured_timezone()).date()
    jobs = list(
        db.scalars(
            select(Job).where(
                Job.status.in_(ACTIVE_JOB_STATUSES),
                Job.application_deadline.is_not(None),
                Job.deadline_confidence.is_not(None),
                Job.deadline_confidence >= AUTOMATIC_DEADLINE_CONFIDENCE,
                Job.application_deadline < local_date,
            )
        )
    )
    if not jobs:
        logger.info("Expired 0 past-deadline jobs.")
        return 0
    for job in jobs:
        job.status = "expired"
        job.expired_at = current_utc
    db.commit()
    logger.info("Expired %d past-deadline jobs.", len(jobs))
    return len(jobs)


def expire_due_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Backward-compatible alias."""
    return expire_past_deadline_jobs(db, now=now)
