import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.services.email_service import run_daily_digest, run_email_maintenance
from app.services.search_runs import run_managed_search
from app.services.discovery_orchestration import DISCOVERY_GROUPS, configured_group_hour, run_discovery_group


scheduler = AsyncIOScheduler(timezone=settings.user_timezone)
def start_scheduler() -> None:
    if not settings.scheduler_enabled or scheduler.running:
        return
    if settings.search_scheduler_enabled:
        for search_type, hours in (
            ("high_priority", settings.high_priority_search_interval_hours),
            ("verification", settings.verify_jobs_interval_hours),
            ("expire_deadlines", settings.expire_jobs_interval_hours),
        ):
            scheduler.add_job(
                run_managed_search,
                "interval",
                hours=hours,
                args=[search_type, "scheduler"],
                id=f"{search_type}-search",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        # A group scheduler replaces the previous all-source general sweep.
        # This stays one scheduler process while spreading source adapters over
        # different windows through the day.
        for group in DISCOVERY_GROUPS:
            scheduler.add_job(
                run_discovery_group,
                "cron",
                hour=configured_group_hour(group),
                minute=0,
                args=[group, "scheduler"],
                id=f"discovery-group-{group.lower()}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                jitter=max(0, settings.discovery_jitter_seconds),
            )
    scheduler.add_job(
        run_email_maintenance,
        "cron",
        minute=15,
        id="email-deadlines-and-follow-ups",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_daily_digest,
        "cron",
        hour=settings.email_digest_hour,
        minute=0,
        id="daily-email-digest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
