from typing import Annotated
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.private_api import require_private_api
from app.models import Job, OpportunityTracking
from app.schemas.opportunities import OpportunityInput
from app.services import opportunity_dashboard as dashboard
from app.services.opportunity_seeds import bootstrap
from app.services.opportunity_discovery import DiscoveryQuery, provider

router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])
Owner = Annotated[str, Depends(require_private_api)]
Database = Annotated[Session, Depends(get_db)]


def owned(db, owner, job_id):
    job = dashboard.get_job(db, owner, job_id)
    if job is None:
        raise HTTPException(404, "Opportunity not found")
    return job


@router.post("/bootstrap")
def initial_collection(owner: Owner, db: Database):
    return bootstrap(db, owner)


@router.get("")
def opportunities(owner: Owner, db: Database):
    return dashboard.list_opportunities(db, owner)


@router.post("")
def create_opportunity(value: OpportunityInput, owner: Owner, db: Database):
    job, created = dashboard.save(db, owner, value)
    db.commit()
    return {"created": created, "opportunity": dashboard.snapshot(db, job)}


@router.post("/discover")
async def discover(value: DiscoveryQuery, owner: Owner, db: Database):
    search = provider()
    if search is None:
        return {"enabled": False, "message": "Live discovery is not configured. Set OPPORTUNITY_SEARCH_PROVIDER=tavily and OPPORTUNITY_SEARCH_API_KEY on the backend, then restart it. Saved opportunity search remains available.", "results": []}
    try:
        results = await search.search(value)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        raise HTTPException(502, "Search provider unavailable. Check backend configuration or retry later.")
    jobs = db.scalars(select(Job).where(Job.owner_user_id == owner)).all()
    unique = []
    seen = set()
    for result in results:
        key = dashboard.canonical_url(result.official_url)
        if key in seen or dashboard.duplicate(jobs, result):
            continue
        seen.add(key)
        unique.append(result.model_dump(mode="json") | {"why_match": "Returned by your research query from an official-domain page. Eligibility, funding and dates require source review."})
    return {"enabled": True, "message": "New official-domain results. Search snippets are not eligibility verification; confirm details before applying.", "results": unique}


@router.get("/{job_id}")
def opportunity(job_id: int, owner: Owner, db: Database):
    return dashboard.snapshot(db, owned(db, owner, job_id))


@router.put("/{job_id}")
def edit_opportunity(job_id: int, value: OpportunityInput, owner: Owner, db: Database):
    original = owned(db, owner, job_id)
    job, _ = dashboard.save(db, owner, value, original)
    if job.id != job_id:
        raise HTTPException(409, "Another saved opportunity already has this URL or program/university identity")
    db.commit()
    return dashboard.snapshot(db, job)


class Favorite(BaseModel):
    favorite: bool


def update_metadata(db, job, changes):
    record = dashboard.tracking(db, job)
    if record is None:
        record = OpportunityTracking(job_id=job.id, owner_user_id=job.owner_user_id, details={})
        db.add(record)
    if "status" in changes:
        changes = changes | {"status_updated_at": datetime.now(timezone.utc).isoformat()}
    record.details = (record.details or {}) | changes
    record.updated_at = datetime.now(timezone.utc)


@router.post("/{job_id}/favorite")
def favorite(job_id: int, value: Favorite, owner: Owner, db: Database):
    job = owned(db, owner, job_id)
    update_metadata(db, job, {"favorite": value.favorite})
    db.commit()
    return dashboard.snapshot(db, job)


@router.post("/{job_id}/applied")
def applied(job_id: int, owner: Owner, db: Database):
    job = owned(db, owner, job_id)
    update_metadata(db, job, {"status": "Applied"})
    dashboard.sync_application(db, job, owner, "Applied")
    db.commit()
    return dashboard.snapshot(db, job)
