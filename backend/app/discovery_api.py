"""Private discovery endpoints; no application, resume upload or email actions."""
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlsplit
import json
import re
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from app.db.session import get_db
from sqlalchemy.orm import Session
from app.security.private_api import require_private_api
from app.models import CompanySource, Job, SearchRun, UserProfile
from app.schemas.discovery import RawOpportunity, DiscoverySearchQuery, CompanyBoardInput
from app.services.search_runs import create_search_run
from app.services.unified_discovery import criteria_for, execute_discovery_search, import_external, search_results
from app.services.source_catalog import SOURCE_CATALOG

router = APIRouter(prefix="/api/discovery", tags=["Discovery"])
Owner = Annotated[str, Depends(require_private_api)]
Database = Annotated[Session, Depends(get_db)]


@router.post("/search", status_code=202)
def search(value: DiscoverySearchQuery, background: BackgroundTasks, owner: Owner, db: Database):
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner))
    if profile is None:
        raise HTTPException(409, "Complete your candidate profile before searching.")
    run = create_search_run(db, search_type=f"discovery_{value.mode}", owner_user_id=owner, criteria=criteria_for(profile, value))
    if run is None:
        raise HTTPException(409, "Another search is running; wait for it to finish.")
    background.add_task(execute_discovery_search, run.id)
    return {"runId": run.id, "status": run.status}


@router.post("/import")
async def external_import(value: RawOpportunity, owner: Owner, db: Database):
    try:
        run, summary = await import_external(db, owner, value)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"runId": run.id, "summary": summary, "results": search_results(db, owner, run)}


def run_view(run):
    return {"id": run.id, "mode": run.search_type, "status": run.status, "progress": run.progress_status,
        "startedAt": run.started_at, "finishedAt": run.completed_at, "rawResults": sum(m.get("fetched_count", 0) for m in run.source_metrics or []) or run.jobs_discovered, "normalizedResults": run.jobs_discovered,
        "newJobs": run.jobs_added, "updatedJobs": run.jobs_updated, "errors": run.error_count,
        "finalCandidates": run.result_count, "verifiedJobs": run.verified_count, "eligibleJobs": run.eligible_count,
        "metrics": run.source_metrics, "summary": run.progress_json}


@router.get("/runs")
def history(owner: Owner, db: Database):
    runs = db.scalars(select(SearchRun).where(SearchRun.owner_user_id == owner, SearchRun.history_deleted_at.is_(None)).order_by(SearchRun.id.desc()).limit(30)).all()
    return [run_view(run) for run in runs]


@router.get("/runs/{run_id}")
def run_status(run_id: int, owner: Owner, db: Database):
    run = db.scalar(select(SearchRun).where(SearchRun.id == run_id, SearchRun.owner_user_id == owner))
    if run is None:
        raise HTTPException(404, "Search run not found")
    new_days = (run.criteria_json or {}).get("_discovery_query", {}).get("new_days", 3)
    return run_view(run) | {"results": search_results(db, owner, run, new_days=new_days) if run.status == "completed" else [], "cached": run.status == "completed" and not run.result_count}


@router.get("/results")
def results(owner: Owner, db: Database, new_days: int = Query(default=3, ge=1, le=30)):
    return search_results(db, owner, new_days=new_days)


@router.get("/health")
def health(owner: Owner, db: Database):
    sources = db.scalars(select(CompanySource).where(CompanySource.owner_user_id == owner)).all()
    runs = db.scalars(select(SearchRun).where(SearchRun.owner_user_id == owner).order_by(SearchRun.id.desc()).limit(30)).all()
    rows = []
    for source in sources:
        times = [m.get("duration_ms", 0) for run in runs for m in run.source_metrics or [] if m.get("source_id") == source.id]
        rows.append({"id": source.id, "company": source.company, "source": source.source_type, "enabled": source.enabled and not source.reference_only,
            "boardId": source.source_identifier, "sourceUrl": source.source_url, "type": source.registry_type, "priority": source.priority, "countryCoverage": source.geography_scope,
            "lastRun": source.last_attempt_at, "discoveredAt": source.created_at, "lastVerifiedAt": (source.discovery_checkpoint_json or {}).get("board_verified_at") or source.last_success_at,
            "health": source.source_status if source.last_attempt_at else "Not run", "lastSuccessfulRun": source.last_success_at,
            "errors": source.error_count, "jobsFetched": source.fetched_count, "averageRuntimeMs": round(sum(times) / len(times)) if times else None,
            "nextRun": source.next_run_at, "policy": SOURCE_CATALOG.get(source.source_type, {}), "message": source.safe_error_message})
    return {"sources": rows, "catalog": SOURCE_CATALOG}


@router.post("/{job_id}/save")
def save_result(job_id: int, owner: Owner, db: Database):
    from app.services.opportunity_dashboard import snapshot
    job = db.scalar(select(Job).where(Job.id == job_id, Job.owner_user_id == owner))
    if job is None:
        raise HTTPException(404, "Opportunity not found")
    if job.status == "active":
        job.status = "saved"
    db.commit()
    return snapshot(db, job)


@router.post("/boards", status_code=201)
async def add_board(value: CompanyBoardInput, owner: Owner, db: Database):
    from app.services.safe_job_fetch import fetch_job_page
    from app.sources.registry import create_adapter
    host = (urlsplit(value.source_url).hostname or "").lower()
    domains = {"greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"}, "lever": {"jobs.lever.co"}, "ashby": {"jobs.ashbyhq.com"}, "smartrecruiters": {"jobs.smartrecruiters.com"}}
    valid_host = host in domains.get(value.ats, set()) or (value.ats == "workday" and host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")))
    if not valid_host or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+)?", value.board_id):
        raise HTTPException(422, "The board must use the selected official ATS host and a valid board identifier.")
    parts = [p for p in urlsplit(value.source_url).path.split("/") if p]
    if value.ats == "smartrecruiters" and parts[:1] == ["ni"]:
        parts = parts[1:]
    if value.ats == "workday" and parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts = parts[1:]
    if not parts or parts[0].lower() != value.board_id.split("|")[-1].lower() or (value.ats == "workday" and ("|" not in value.board_id or value.board_id.split("|")[0].lower() != host.split(".")[0])):
        raise HTTPException(422, "Board URL and identifier must describe the same company board.")
    source = CompanySource(owner_user_id=owner, company=value.company, source_type=value.ats, source_identifier=value.board_id, source_url=value.source_url, registry_type="OFFICIAL_ATS", supports_structured_data=True, enabled=True, reference_only=False)
    adapter = create_adapter(source)
    try:
        if value.ats == "workday":
            page = await fetch_job_page(adapter.api_url + "/jobs", method="POST", json_body={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
        else:
            page = await fetch_job_page(adapter.api_url)
        payload = json.loads(page.text)
        key = {"greenhouse": "jobs", "ashby": "jobs", "smartrecruiters": "content", "workday": "jobPostings"}.get(value.ats)
        rows = payload if key is None else payload.get(key) if isinstance(payload, dict) else None
        if page.status_code != 200 or not isinstance(rows, list):
            raise ValueError("Board API validation failed")
    except (ValueError, RuntimeError):
        raise HTTPException(422, "Could not verify this board through its public ATS endpoint.")
    existing = db.scalar(select(CompanySource).where(CompanySource.owner_user_id == owner, CompanySource.source_type == value.ats, CompanySource.source_identifier == value.board_id))
    if existing:
        return {"id": existing.id, "created": False}
    source.notes = f"Manually configured board API verified {datetime.now(timezone.utc).isoformat()}; Workday is experimental."
    source.discovery_checkpoint_json = {"board_verified_at": datetime.now(timezone.utc).isoformat(), "discovered_from": "manual_catalog"}
    db.add(source)
    db.commit()
    return {"id": source.id, "created": True}
