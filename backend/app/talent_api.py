from datetime import datetime, timezone
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CompanyTalentProfile, GeneratedResume, ResumeProfile
from app.schemas.api import ApplicationSessionCreate, ApplicationSessionLaunch, GeneratedResumeRead
from app.services.normalization import validate_public_url
from app.services.resume_generation import generate_local_content, generate_resume, content_hash, validate_master_profile
from app.services.talent_communities import BOSTON_DYNAMICS, company_snapshot, talent_context
from app.main import require_private_api, resume_read, _create_application_session

router = APIRouter(prefix="/api/talent-communities", tags=["Talent Communities"])
Owner = Annotated[str, Depends(require_private_api)]
Database = Annotated[Session, Depends(get_db)]


class CompanyPayload(BaseModel):
    company_id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    company_name: str = Field(min_length=1, max_length=180)
    company_summary: str = Field(default="", max_length=4000)
    technical_areas: list[str] = Field(default_factory=list, max_length=20)
    common_role_categories: list[str] = Field(default_factory=list, max_length=20)
    preferred_project_categories: list[str] = Field(default_factory=list, max_length=20)
    preferred_skill_categories: list[str] = Field(default_factory=list, max_length=20)
    source_url: str = Field(default="", max_length=2000)
    last_verified_at: datetime | None = None
    talent_community_url: str = Field(min_length=1, max_length=2000)
    talent_community_description: str = Field(default="", max_length=8000)

    @field_validator("source_url", "talent_community_url")
    @classmethod
    def safe_url(cls, value):
        if value:
            validate_public_url(value)
            if not value.startswith("https://"):
                raise ValueError("Use an HTTPS company URL.")
        return value

    @field_validator("technical_areas", "common_role_categories", "preferred_project_categories", "preferred_skill_categories")
    @classmethod
    def bounded_categories(cls, values):
        if any(len(value) > 100 for value in values):
            raise ValueError("Keep each technical category under 100 characters.")
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class Strategy(BaseModel):
    target_role_categories: list[str] = Field(min_length=1, max_length=12)

    @field_validator("target_role_categories")
    @classmethod
    def clean_targets(cls, values):
        values = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not values or any(len(value) > 100 for value in values):
            raise ValueError("Select at least one target area (up to 100 characters each).")
        return values


def find_company(db, owner, company_id):
    company = db.get(CompanyTalentProfile, (company_id, owner))
    if company:
        return company_snapshot(company)
    if company_id == BOSTON_DYNAMICS["company_id"]:
        return CompanyPayload(**BOSTON_DYNAMICS).model_dump(mode="json")
    raise HTTPException(404, "Talent Community not found.")


def get_profile(db, owner):
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == owner))
    if not profile:
        raise HTTPException(422, "Complete your Resume Profile first.")
    return profile


@router.get("")
def list_companies(owner: Owner, db: Database):
    profiles = [company_snapshot(item) for item in db.scalars(select(CompanyTalentProfile).where(CompanyTalentProfile.owner_user_id == owner))]
    if not any(item["company_id"] == BOSTON_DYNAMICS["company_id"] for item in profiles):
        profiles.insert(0, BOSTON_DYNAMICS)
    return profiles


@router.put("/{company_id}")
def save_company(company_id: str, payload: CompanyPayload, owner: Owner, db: Database):
    if payload.company_id != company_id:
        raise HTTPException(422, "Company identifier does not match.")
    row = db.get(CompanyTalentProfile, (company_id, owner))
    if row is None:
        row = CompanyTalentProfile(owner_user_id=owner, **payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return company_snapshot(row)


@router.post("/{company_id}/preview")
def preview(company_id: str, payload: Strategy, owner: Owner, db: Database):
    company = find_company(db, owner, company_id)
    try:
        profile = get_profile(db, owner)
        validate_master_profile(profile)
        content = generate_local_content(talent_context(company, payload.target_role_categories), profile, project_limit=4)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "company": company,
        "strategy": payload.target_role_categories,
        "projects": [p.model_dump() for p in content.projects],
        "skills": content.selected_skills,
        "courses": [course.model_dump() for course in content.coursework],
        "headline": content.headline,
    }


@router.post("/{company_id}/resumes", response_model=GeneratedResumeRead)
def generate_company_resume(company_id: str, payload: Strategy, owner: Owner, db: Database):
    company = find_company(db, owner, company_id)
    profile = get_profile(db, owner)
    version = db.scalar(select(func.max(GeneratedResume.version)).where(GeneratedResume.user_id == owner, GeneratedResume.company_id == company_id)) or 0
    row = GeneratedResume(user_id=owner, job_id=None, application_type="TALENT_COMMUNITY", company_id=company_id, company=company["company_name"], company_profile=company, talent_community_url=company["talent_community_url"], target_role_categories=payload.target_role_categories, version=version + 1, resume_target="talent_community", status="generating", content_hash="pending", generation_model="local")
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Another company resume is being created. Refresh the version history.") from exc
    try:
        content, latex, pdf_bytes = generate_resume(talent_context(company, payload.target_role_categories), profile, row.id)
        row.tailored_content_json = content.model_dump()
        row.latex_source = latex
        row.compiled_pdf = pdf_bytes
        row.compiled_pdf_at = datetime.now(timezone.utc)
        row.target_role = " + ".join(payload.target_role_categories[:3])
        row.selected_skills = content.selected_skills
        row.skill_categories = [g.model_dump() for g in content.skill_categories]
        row.job_skill_matches = [m.model_dump() for m in content.job_skill_matches]
        row.skill_verification = content.skill_verification.model_dump()
        row.changes_json = [{"section": "Projects", "description": "Selected by company focus and candidate target areas", "reason": "Company targeting without a specific requisition"}]
        row.warnings_json = content.warnings
        row.content_hash = content_hash(content, latex)
        row.status = "compiled"
        db.commit()
        return resume_read(row)
    except (ValueError, RuntimeError) as exc:
        row.status = "failed"
        row.generation_error = str(exc)[:1200]
        db.commit()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        logging.getLogger(__name__).exception("Company resume compilation failed")
        db.rollback()
        row.status = "failed"
        row.generation_error = "Compilation failed. Please try again."
        db.commit()
        raise HTTPException(503, "Company resume compilation failed. Please try again.")


@router.get("/{company_id}/resumes", response_model=list[GeneratedResumeRead])
def company_resumes(company_id: str, owner: Owner, db: Database):
    return [resume_read(row) for row in db.scalars(select(GeneratedResume).where(GeneratedResume.user_id == owner, GeneratedResume.company_id == company_id, GeneratedResume.application_type == "TALENT_COMMUNITY").order_by(GeneratedResume.version.desc()))]


@router.post("/{company_id}/application-sessions", response_model=ApplicationSessionLaunch, status_code=201)
def company_session(company_id: str, payload: ApplicationSessionCreate, owner: Owner, db: Database):
    resume = db.scalar(select(GeneratedResume).where(GeneratedResume.id == payload.resume_version_id, GeneratedResume.company_id == company_id, GeneratedResume.user_id == owner, GeneratedResume.application_type == "TALENT_COMMUNITY", GeneratedResume.status == "compiled"))
    if not resume:
        raise HTTPException(422, "Select one of your compiled company resume versions first.")
    if payload.portfolio_version_id:
        raise HTTPException(422, "Company sessions use the selected company resume.")
    context = talent_context(resume.company_profile, resume.target_role_categories)
    return _create_application_session(None, payload, owner, db, talent_context=context)
