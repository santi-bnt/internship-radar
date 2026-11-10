"""Search modes and external ingestion on the existing refresh pipeline."""
from datetime import datetime, timezone, timedelta
import re
from urllib.parse import urlsplit
from sqlalchemy import select, func
from sqlalchemy.orm import contains_eager
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import CompanySource, Job, JobAnalysis, SearchRun, SearchRunJob, UserProfile
from app.schemas.discovery import DiscoverySearchQuery
from app.services.source_catalog import SOURCE_CATALOG
from app.services.discovery_orchestration import source_is_due, _GLOBAL_SEMAPHORE
from app.services.discovery_records import canonical_opportunity


def criteria_for(profile, query):
    areas = query.areas or list(profile.preferred_roles or [])
    if query.query:
        areas = [word for word in re.split(r"[,;]|\s+", query.query) if len(word) >= 3 and word.lower() not in {"intern", "internship", "internships", "research", "united", "states", "canada", "students", "undergraduate"}]
    if not areas:
        areas = [profile.degree_field] if profile.degree_field else ["engineering"]
    countries = query.countries or [c for c in profile.countries_to_search or [] if c in {"United States", "Canada"}] or list(profile.countries_to_search or [])
    return {"include_keywords": areas[:20], "countries": countries, "posted_within_days": query.max_age_days,
        "student_level": profile.degree_level_current, "opportunity_types": query.opportunity_types,
        "only_realistically_eligible": False, "include_unknown_eligibility": True, "allow_unknown_location": True,
        "limit": 100, "_discovery_query": query.model_dump()}


def ensure_optional_sources(db, owner):
    enabled = []
    if settings.freehire_enabled and settings.freehire_use_mode in {"personal", "licensed"}:
        enabled.append(("Freehire discovery", "freehire", "public-search", "https://freehire.me"))
    if settings.opportunity_search_provider == "tavily" and settings.opportunity_search_api_key:
        enabled.extend([("Web X-ray discovery", "web_search", "official-search", "https://api.tavily.com"), ("University research discovery", "research", "research-search", "https://api.tavily.com")])
    for company, kind, identifier, url in enabled:
        found = db.scalar(select(CompanySource).where(CompanySource.owner_user_id == owner, CompanySource.source_type == kind, CompanySource.source_identifier == identifier))
        if found is None:
            db.add(CompanySource(owner_user_id=owner, company=company, source_type=kind, source_identifier=identifier, source_url=url, registry_type="AGGREGATOR", enabled=True, reference_only=False, priority=30, refresh_frequency="daily", notes="Optional bounded discovery; original source attribution is preserved."))
    db.flush()


def official_domains(db, owner):
    sources = db.scalars(select(CompanySource).where(CompanySource.owner_user_id == owner, CompanySource.registry_type == "OFFICIAL_COMPANY", CompanySource.enabled.is_(True))).all()
    return list({urlsplit(s.source_url).hostname.lower() for s in sources if urlsplit(s.source_url).hostname})


def complete_run(db, run, summary):
    from app.services.search_runs import _store_search_results
    run.sources_checked = summary.get("sources_checked", 0)
    run.jobs_discovered = summary.get("jobs_fetched", 0)
    run.jobs_added = summary.get("jobs_created", 0)
    run.jobs_updated = summary.get("jobs_updated", 0)
    run.jobs_expired = summary.get("jobs_closed", 0)
    run.error_count = len(summary.get("errors", []))
    run.source_metrics = summary.get("source_metrics", [])
    run.safe_error_summary = "; ".join(str(e.get("source", "Unknown source")) for e in summary.get("errors", []))[:500]
    run.progress_json = {k: summary.get(k, 0) for k in ("jobs_fetched", "jobs_created", "jobs_updated", "duplicates_removed", "verified_matches", "eligible_matches", "sources_queued")}
    _store_search_results(db, run, summary)
    run.completed_at = datetime.now(timezone.utc)
    run.status = "completed"
    run.progress_status = "Complete" if run.sources_checked else "No sources due; showing cached results is available."
    db.commit()


async def execute_discovery_search(run_id):
    from app.jobs.refresh import refresh_all_sources
    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if not run or run.status != "pending":
            return
        db.info["owner_user_id"] = run.owner_user_id
        profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == run.owner_user_id))
        if profile is None:
            run.status = "failed"
            run.safe_error_summary = "Candidate profile is missing."
            db.commit()
            return
        run.status, run.progress_status = "running", "Searching configured sources"
        db.commit()
        try:
            query = DiscoverySearchQuery.model_validate((run.criteria_json or {}).get("_discovery_query", {}))
            ensure_optional_sources(db, run.owner_user_id)
            now = datetime.now(timezone.utc)
            sources = db.scalars(select(CompanySource).where(CompanySource.owner_user_id == run.owner_user_id, CompanySource.enabled.is_(True), CompanySource.reference_only.is_(False))).all()
            selected = [s for s in sources if source_is_due(s, now) and s.source_type != "manual" and (query.mode == "deep" or SOURCE_CATALOG.get(s.source_type, {}).get("quick"))]
            selected.sort(key=lambda s: (s.last_attempt_at is not None, str(s.next_run_at or ""), -s.priority))
            ids = {s.id for s in selected[:settings.discovery_source_batch_size]}
            for source in selected[:settings.discovery_source_batch_size]:
                source.next_run_at = now + timedelta(minutes=30)
                source.discovery_checkpoint_json = {"state": "running", "trigger": run.trigger}
            db.commit()
            criteria = dict(run.criteria_json or {}) | {"_official_domains": official_domains(db, run.owner_user_id)}
            async with _GLOBAL_SEMAPHORE:
                summary = await refresh_all_sources(db, source_ids=ids, criteria=criteria, send_notifications=False, allow_outside_profile_locations=True)
            summary["sources_queued"] = max(0, len(selected) - len(ids))
            complete_run(db, run, summary)
        except Exception as exc:
            db.rollback()
            run = db.get(SearchRun, run_id)
            run.status, run.progress_status = "failed", "Discovery failed"
            run.safe_error_summary = f"Discovery failed ({type(exc).__name__}); retry or inspect Source Health."
            run.completed_at = datetime.now(timezone.utc)
            db.commit()


async def import_external(db, owner, raw):
    from app.jobs.refresh import refresh_all_sources
    from app.sources.external import ManualSource
    from app.services.official_source_resolver import OfficialSourceResolver
    from app.services.search_runs import create_search_run
    if db.info.get("owner_user_id") not in {None, owner}:
        raise ValueError("Candidate scope mismatch")
    db.info["owner_user_id"] = owner
    source = db.scalar(select(CompanySource).where(CompanySource.owner_user_id == owner, CompanySource.source_type == "manual", CompanySource.source_identifier == "external-import"))
    if source is None:
        source = CompanySource(owner_user_id=owner, company="External import", source_type="manual", source_identifier="external-import", source_url=raw.source_url, registry_type="OTHER", enabled=False, reference_only=False)
        db.add(source)
        db.flush()
    run = create_search_run(db, search_type="external_import", owner_user_id=owner)
    if run is None:
        raise ValueError("Another search is running. Retry when it completes.")
    try:
        adapter = ManualSource(source.company, source.source_identifier, source.source_url)
        normalized = await OfficialSourceResolver(official_domains(db, owner)).resolve(adapter.normalize_job(raw.model_dump(mode="json")))
        async with _GLOBAL_SEMAPHORE:
            summary = await refresh_all_sources(db, source_ids={source.id}, injected_jobs={source.id: [normalized]}, send_notifications=False, allow_outside_profile_locations=True)
        complete_run(db, run, summary)
        return run, summary
    except Exception:
        db.rollback()
        run = db.get(SearchRun, run.id)
        run.status, run.safe_error_summary = "failed", "External import failed; no sensitive details are logged."
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise


def search_results(db, owner, run=None, new_days=3):
    query = select(Job).outerjoin(Job.analysis).options(contains_eager(Job.analysis)).where(Job.owner_user_id == owner)
    if run and run.result_count:
        query = query.where(Job.id.in_(select(SearchRunJob.job_id).where(SearchRunJob.search_run_id == run.id, SearchRunJob.owner_user_id == owner)))
    fit = (func.coalesce(JobAnalysis.technical_score, 0) * .65 + func.coalesce(JobAnalysis.academic_score, 0) * .15 + func.coalesce(JobAnalysis.level_score, 0) * .10 + func.coalesce(JobAnalysis.logistics_score, 0) * .10)
    query = query.order_by(fit.desc(), JobAnalysis.eligibility_score.desc(), Job.first_seen_at.desc())
    from app.services.search_criteria import matches_discovery_criteria
    results = []
    # Stream candidates in fit order. Filter before taking the final 100;
    # newer unrelated rows must not hide older relevant opportunities.
    for job in db.scalars(query.execution_options(yield_per=100)):
        if run and not run.result_count and not matches_discovery_criteria(job, run.criteria_json)[0]:
            continue
        results.append(canonical_opportunity(db, job, new_days=new_days))
        if len(results) >= 100:
            break
    return sorted(results, key=lambda item: (item["fitScore"] or 0, item["eligibilityScore"] or 0), reverse=True)


async def run_due_discovery():
    """Hourly bounded dispatcher; each board retains its own 6/12/24h cadence."""
    from app.services.search_runs import create_search_run
    with SessionLocal() as db:
        db.info["owner_user_id"] = settings.effective_primary_user_id
        profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == settings.effective_primary_user_id))
        if profile is None:
            return
        ensure_optional_sources(db, profile.owner_user_id)
        sources = db.scalars(select(CompanySource).where(CompanySource.owner_user_id == profile.owner_user_id, CompanySource.enabled.is_(True), CompanySource.reference_only.is_(False))).all()
        if not any(source_is_due(source, datetime.now(timezone.utc)) for source in sources):
            db.commit()
            return
        query = DiscoverySearchQuery(mode="deep")
        run = create_search_run(db, search_type="discovery_scheduled", trigger="scheduler", owner_user_id=profile.owner_user_id, criteria=criteria_for(profile, query))
        if run is None:
            return  # An existing candidate search retains the single run lock.
        run_id = run.id
    await execute_discovery_search(run_id)
