from __future__ import annotations

import logging
import hmac
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal, get_db
from app.jobs.refresh import persist_analysis, refresh_all_sources
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.models import (
    Application,
    CompanySource,
    Job,
    JobAnalysis,
    Notification,
    UserProfile,
    ResumeProfile,
    GeneratedResume,
    TargetCompany,
    TargetSearchRun,
    SearchRun,
)
from app.schemas.api import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    EmailActionResult,
    JobPage,
    JobRead,
    JobLifecycleActionRead,
    NotificationRead,
    ProfilePayload,
    ProfileRead,
    SourceCreate,
    SourceRead,
    SourceUpdate,
    StatsRead,
    GeneratedResumeRead,
    ResumeProfilePayload,
    ResumeProfileRead,
    VerifiedSkillGroupRead,
    TargetCompanyPayload,
    TargetCompanyRead,
    TargetCompanyUpdate,
    TargetSearchRunRead,
    SearchRunRead,
    UndoAppliedPayload,
)
from app.services.email_service import EmailService
from app.services.job_lifecycle import (
    ACTIVE_JOB_STATUSES,
    JOB_STATUSES,
    configured_timezone,
    expire_past_deadline_jobs,
)
from app.services.normalization import validate_public_url
from app.services.seed import seed_profile_and_sources
from app.services.resume_generation import (
    CANONICAL_DEGREE,
    CANONICAL_NAME,
    compile_latex,
    content_hash,
    generate_resume,
    sanitize_filename,
)
from app.services.resume_skills import grouped_verified_skill_registry
from app.jobs.target_search import search_target_companies
from app.services.search_runs import create_search_run, execute_search_run
from app.security.audit import audit_event
from app.security.identity import (
    AuthenticatedIdentity,
    IdentityValidationError,
    validate_user_identity,
)
from app.security.rate_limit import check_rate_limit, sensitive_operation


logger = logging.getLogger(__name__)


def require_private_api(request: Request) -> str:
    identity = getattr(request.state, "authenticated_identity", None)
    if not isinstance(identity, AuthenticatedIdentity):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return identity.primary_user_id


def resume_read(resume: GeneratedResume) -> GeneratedResumeRead:
    compiled = resume.status == "compiled"
    return GeneratedResumeRead(
        **{
            column.name: getattr(resume, column.name)
            for column in GeneratedResume.__table__.columns
            if column.name not in {"user_id", "content_hash"}
        },
        pdf_url=f"/api/generated-resumes/{resume.id}/pdf" if compiled else None,
        tex_url=f"/api/generated-resumes/{resume.id}/tex",
    )


def _send_follow_up_safely(db: Session, application: Application) -> None:
    try:
        profile = db.scalar(select(UserProfile).limit(1))
        if profile:
            EmailService(db).send_application_follow_up(application, profile)
    except Exception:
        db.rollback()
        logger.error(
            "Application follow-up notification failed; the application update remains saved."
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "server_start environment=%s scheduler_enabled=%s search_scheduler_enabled=%s",
        settings.environment,
        settings.scheduler_enabled,
        settings.search_scheduler_enabled,
    )
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        profile = db.scalar(select(UserProfile).limit(1))
        if profile:
            for existing_job in db.scalars(select(Job).options(joinedload(Job.analysis))):
                persist_analysis(db, existing_job, profile)
            db.commit()
        if db.scalar(select(Job.id).limit(1)) is None:
            await refresh_all_sources(db, source_types={"local_json"})
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Internship Radar API",
    version="1.0.0",
    description="Explainable internship discovery and application tracking.",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def protect_private_api(request: Request, call_next):
    path = request.url.path
    if path == "/health":
        return await call_next(request)
    if not path.startswith("/api/"):
        return JSONResponse({"detail": "Resource not found."}, status_code=404)
    if not settings.app_access_enabled:
        return JSONResponse(
            {"detail": "Internship Radar is temporarily unavailable."},
            status_code=503,
            headers={"Cache-Control": "no-store", "Retry-After": "3600"},
        )

    expected_internal_secret = settings.internal_api_secret.strip()
    supplied_internal_secret = request.headers.get("x-internal-api-secret", "")
    if not expected_internal_secret or not hmac.compare_digest(
        expected_internal_secret, supplied_internal_secret
    ):
        audit_event("backend_access_rejected", resource=path, outcome="invalid_service_auth")
        return JSONResponse(
            {"detail": "Authentication required."},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    try:
        identity = validate_user_identity(request.headers.get("x-user-identity"))
    except IdentityValidationError:
        audit_event("backend_access_rejected", resource=path, outcome="invalid_identity")
        return JSONResponse(
            {"detail": "Authentication required."},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    request.state.authenticated_identity = identity

    rule = sensitive_operation(path, request.method)
    if rule:
        allowed, retry_after = check_rate_limit(identity.primary_user_id, rule)
        if not allowed:
            audit_event(
                "rate_limit_rejected",
                email=identity.authenticated_email,
                resource=rule.key,
                outcome="rate_limited",
            )
            return JSONResponse(
                {"detail": "Too many requests. Try again later."},
                status_code=429,
                headers={"Cache-Control": "no-store", "Retry-After": str(retry_after)},
            )

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if rule and response.status_code < 400:
        audit_event(
            rule.key,
            email=identity.authenticated_email,
            resource=path,
        )
    return response


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str | None]:
    database = "connected"
    try:
        db.execute(select(1))
    except Exception:
        database = "unavailable"
    compiler = shutil.which(settings.tectonic_path)
    latex_compiler = "unavailable"
    if compiler:
        try:
            subprocess.run(
                [compiler, "--version"],
                capture_output=True,
                text=True,
                timeout=min(settings.tectonic_timeout_seconds, 10),
                check=True,
            )
            latex_compiler = "available"
        except (OSError, subprocess.SubprocessError):
            pass
    last_success = db.scalar(
        select(SearchRun)
        .where(SearchRun.status.in_(("completed", "partial")))
        .order_by(SearchRun.completed_at.desc())
        .limit(1)
    ) if database == "connected" else None
    healthy = database == "connected" and latex_compiler == "available"
    return {
        "status": "ok" if healthy else "degraded",
        "database": database,
        "latex_compiler": latex_compiler,
        "scheduler": (
            "configured"
            if settings.scheduler_enabled and settings.search_scheduler_enabled
            else "external_cron"
        ),
        "last_successful_search": (
            last_success.completed_at.isoformat()
            if last_success and last_success.completed_at
            else None
        ),
    }


@app.get("/api/profile", response_model=ProfileRead)
def get_profile(db: Session = Depends(get_db)) -> UserProfile:
    profile = db.scalar(select(UserProfile).limit(1))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.put("/api/profile", response_model=ProfileRead)
def update_profile(payload: ProfilePayload, db: Session = Depends(get_db)) -> UserProfile:
    if "@" not in payload.notification_email or "." not in payload.notification_email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid notification email address.")
    profile = db.scalar(select(UserProfile).limit(1))
    if not profile:
        profile = UserProfile(**payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    db.flush()
    for job in db.scalars(select(Job).options(joinedload(Job.analysis))):
        persist_analysis(db, job, profile)
    db.commit()
    db.refresh(profile)
    return profile


@app.get("/api/resume-profile", response_model=ResumeProfileRead)
def get_resume_profile(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ResumeProfile:
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Resume profile not found.")
    return profile


@app.put("/api/resume-profile", response_model=ResumeProfileRead)
def update_resume_profile(
    payload: ResumeProfilePayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ResumeProfile:
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile:
        profile = ResumeProfile(user_id=user_id, **payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@app.get(
    "/api/resume-profile/verified-skills",
    response_model=list[VerifiedSkillGroupRead],
)
def get_verified_resume_skills(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Resume profile not found.")
    return grouped_verified_skill_registry(profile)


@app.get("/api/jobs", response_model=JobPage)
def list_jobs(
    job_status: list[str] | None = Query(default=None),
    recommendation: list[str] | None = Query(default=None),
    eligibility: list[str] | None = Query(default=None),
    country: list[str] | None = Query(default=None),
    company: str | None = None,
    target_group: str | None = None,
    remote_type: list[str] | None = Query(default=None),
    remote_scope: list[str] | None = Query(default=None),
    sponsorship: list[str] | None = Query(default=None),
    include_ineligible: bool = False,
    employment: list[str] | None = Query(default=None),
    area: list[str] | None = Query(default=None),
    company_importance: list[str] | None = Query(default=None),
    verification: list[str] | None = Query(default=None),
    date: str | None = None,
    source: str | None = None,
    priority: bool | None = None,
    active: bool | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> JobPage:
    expire_past_deadline_jobs(db)
    hidden_statuses = ["ignored"]
    if not settings.demo_feed_enabled:
        hidden_statuses.append("demo")
    requested_statuses = job_status or list(ACTIVE_JOB_STATUSES)
    invalid_statuses = set(requested_statuses) - JOB_STATUSES
    if invalid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported job status: {', '.join(sorted(invalid_statuses))}",
        )
    filters = [
        Job.discovery_status.not_in(hidden_statuses),
        Job.status.in_(requested_statuses),
    ]
    if recommendation:
        filters.append(JobAnalysis.recommendation.in_(recommendation))
    explicitly_requests_ineligible = bool(
        (recommendation and "Not Eligible" in recommendation)
        or (eligibility and "NOT_ELIGIBLE" in eligibility)
    )
    if not include_ineligible and not explicitly_requests_ineligible:
        filters.append(
            or_(
                Job.status.not_in(ACTIVE_JOB_STATUSES),
                JobAnalysis.id.is_(None),
                JobAnalysis.eligibility_status.not_in(["NOT_ELIGIBLE", "Not Eligible"]),
            )
        )
    if eligibility:
        filters.append(JobAnalysis.eligibility_status.in_(eligibility))
    if country:
        include_remote_outside = "Remote outside selected countries" in country
        selected_countries = [item for item in country if item != "Remote outside selected countries"]
        country_filters = []
        if selected_countries:
            country_filters.append(Job.country.in_(selected_countries))
        if include_remote_outside:
            outside_clause = Job.remote_from_mexico_allowed.is_(True)
            if selected_countries:
                outside_clause = and_(outside_clause, Job.country.not_in(selected_countries))
            country_filters.append(outside_clause)
        if country_filters:
            filters.append(or_(*country_filters))
    if company:
        filters.append(Job.company.ilike(f"%{company}%"))
    if target_group:
        if target_group == "Target companies":
            filters.append(Job.is_target_company.is_(True))
        elif target_group == "Other companies":
            filters.append(Job.is_target_company.is_(False))
        elif target_group == "Oracle":
            filters.append(Job.company == "Oracle")
        else:
            filters.append(Job.target_company_category == target_group)
    if remote_type:
        arrangement_filters = []
        for arrangement in remote_type:
            if arrangement == "Remote":
                arrangement_filters.append(Job.remote_type.like("Remote%"))
            elif arrangement == "Remote from Mexico":
                arrangement_filters.append(Job.remote_from_mexico_allowed.is_(True))
            else:
                arrangement_filters.append(Job.remote_type == arrangement)
        filters.append(or_(*arrangement_filters))
    if remote_scope:
        filters.append(Job.remote_scope.in_(remote_scope))
    if sponsorship:
        filters.append(Job.sponsorship_status.in_(sponsorship))
    if employment:
        employment_filters = []
        for employment_type in employment:
            if employment_type == "Student program":
                employment_filters.append(
                    or_(
                        Job.employment_type.ilike("%student%"),
                        Job.title.ilike("%student%"),
                    )
                )
            elif employment_type == "Co-op":
                employment_filters.append(
                    or_(Job.employment_type.ilike("%co-op%"), Job.title.ilike("%co-op%"))
                )
            else:
                employment_filters.append(Job.employment_type.ilike("%intern%"))
        filters.append(or_(*employment_filters))
    if area:
        filters.append(Job.area.in_(area))
    if company_importance:
        filters.append(Job.company_importance.in_(company_importance))
    if verification:
        verification_filters = []
        for verification_filter in verification:
            if verification_filter == "Officially verified":
                verification_filters.append(
                    and_(Job.official_status == "open", Job.verification_status == "verified")
                )
            elif verification_filter == "Partially verified":
                verification_filters.append(Job.verification_status == "partially_verified")
            else:
                verification_filters.append(
                    Job.verification_status.in_(["unverified", "verification_failed"])
                )
        filters.append(or_(*verification_filters))
    if date and date != "Any date":
        days_by_filter = {
            "Last 24 hours": 1,
            "Last 3 days": 3,
            "Last 7 days": 7,
            "Last 14 days": 14,
            "Last 30 days": 30,
        }
        if date in days_by_filter:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_by_filter[date])
            filters.append(
                func.coalesce(
                    Job.official_posted_at,
                    Job.source_posted_at,
                    Job.first_seen_at,
                )
                >= cutoff
            )
    if source:
        filters.append(Job.source_name == source)
    if priority is not None:
        filters.append(Job.is_priority_alert.is_(priority))
    if active is not None:
        filters.append(Job.is_active.is_(active))
    if min_score is not None:
        filters.append(JobAnalysis.effective_score >= min_score)
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Job.title.ilike(term),
                Job.company.ilike(term),
                Job.location.ilike(term),
                Job.description.ilike(term),
                Job.requirements.ilike(term),
            )
        )

    count_stmt = select(func.count(Job.id)).outerjoin(JobAnalysis).where(*filters)
    total = db.scalar(count_stmt) or 0
    query = (
        select(Job)
        .options(joinedload(Job.analysis), selectinload(Job.applications))
        .outerjoin(JobAnalysis)
        .where(*filters)
        .order_by(
            case(
                (
                    and_(
                        JobAnalysis.eligibility_status == "ELIGIBLE",
                        JobAnalysis.effective_score >= 70,
                        or_(Job.country == "Mexico", Job.can_work_from_mexico == "YES"),
                    ),
                    5,
                ),
                (JobAnalysis.eligibility_status == "ELIGIBLE", 4),
                (JobAnalysis.eligibility_status == "UNKNOWN", 3),
                (
                    and_(
                        JobAnalysis.eligibility_status == "LIKELY_ELIGIBLE",
                        Job.sponsorship_status == "AVAILABLE",
                    ),
                    2,
                ),
                (JobAnalysis.eligibility_status == "LIKELY_ELIGIBLE", 3),
                else_=1,
            ).desc(),
            Job.is_priority_alert.desc(),
            Job.company_priority_bonus.desc(),
            case(
                (
                    and_(Job.official_status == "open", Job.verification_status == "verified"),
                    1,
                ),
                else_=0,
            ).desc(),
            case((JobAnalysis.recommendation == "Not Eligible", 0), else_=1).desc(),
            JobAnalysis.effective_score.desc().nullslast(),
            JobAnalysis.freshness_score.desc().nullslast(),
            Job.expires_at.asc().nullslast(),
            Job.posted_at.desc().nullslast(),
            case((Job.company_importance == "Major company", 1), else_=0).desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(query).unique())
    return JobPage(items=items, total=total, page=page, page_size=page_size)


@app.post("/api/jobs/search", response_model=SearchRunRead, status_code=202)
async def search_jobs(
    background_tasks: BackgroundTasks,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    run = create_search_run(db, search_type="general", trigger="manual")
    if run is None:
        active = db.scalar(
            select(SearchRun)
            .where(SearchRun.status.in_(("pending", "running")))
            .order_by(SearchRun.started_at.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=409,
            detail=f"Search #{active.id if active else ''} is already running.",
        )
    background_tasks.add_task(execute_search_run, run.id)
    return run


@app.get("/api/search-runs/latest", response_model=SearchRunRead)
def latest_search_run(
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    run = db.scalar(select(SearchRun).order_by(SearchRun.started_at.desc()).limit(1))
    if not run:
        raise HTTPException(status_code=404, detail="No search has run yet.")
    return run


@app.get("/api/search-runs/{run_id}", response_model=SearchRunRead)
def get_search_run(
    run_id: int,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    run = db.get(SearchRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found.")
    return run


@app.post("/api/jobs/analyze-all")
def analyze_all_jobs(db: Session = Depends(get_db)) -> dict[str, int]:
    expire_past_deadline_jobs(db)
    profile = db.scalar(select(UserProfile).limit(1))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.status.in_(ACTIVE_JOB_STATUSES))
            .options(joinedload(Job.analysis))
        )
    )
    for job in jobs:
        persist_analysis(db, job, profile)
    db.commit()
    return {"analyzed": len(jobs)}


@app.get("/api/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    expire_past_deadline_jobs(db)
    job = db.scalar(select(Job).where(Job.id == job_id).options(joinedload(Job.analysis)))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/resume/generate", response_model=GeneratedResumeRead)
def generate_job_resume(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    expire_past_deadline_jobs(db)
    db.refresh(job)
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot generate a new resume for a {job.status} job.",
        )
    if not (job.description or job.requirements):
        raise HTTPException(status_code=422, detail="This job has no description to analyze.")
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile or not profile.full_name or not profile.education_json:
        raise HTTPException(status_code=422, detail="Complete Resume Profile before generating a resume.")
    latest_version = db.scalar(
        select(func.max(GeneratedResume.version)).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
        )
    ) or 0
    record = GeneratedResume(
        user_id=user_id,
        job_id=job_id,
        version=latest_version + 1,
        status="generating",
        target_role=job.title,
        content_hash="pending",
        generation_model=(
            settings.openai_resume_model
            if settings.resume_generation_provider.strip().lower() == "openai"
            else "local"
        ),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        content, latex_source, _ = generate_resume(job, profile, record.id)
        record.status = "compiled"
        record.target_role = content.target_role
        record.tailored_content_json = content.model_dump()
        record.latex_source = latex_source
        record.match_score = content.match_score
        record.keywords_json = {
            "included": content.keywords_used,
            "supported_not_included": [],
            "missing": content.keywords_missing,
            "refused": content.unsupported_requirements,
        }
        record.changes_json = [item.model_dump() for item in content.changes]
        record.warnings_json = content.warnings + content.unsupported_requirements
        record.selected_skills = content.selected_skills
        record.skill_categories = [
            group.model_dump() for group in content.skill_categories
        ]
        record.job_skill_matches = [
            item.model_dump() for item in content.job_skill_matches
        ]
        record.skill_verification = content.skill_verification.model_dump()
        record.content_hash = content_hash(content, latex_source)
        record.generation_error = None
        db.commit()
        db.refresh(record)
        return resume_read(record)
    except Exception as exc:
        record.status = "failed"
        record.generation_error = str(exc)[:1200]
        db.commit()
        if isinstance(exc, (RuntimeError, ValueError)):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail="Resume generation failed.") from exc


@app.get("/api/jobs/{job_id}/resume/latest", response_model=GeneratedResumeRead)
def latest_job_resume(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    resume = db.scalar(
        select(GeneratedResume)
        .where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
            GeneratedResume.status == "compiled",
        )
        .order_by(GeneratedResume.version.desc())
        .limit(1)
    )
    if not resume:
        raise HTTPException(status_code=404, detail="No generated resume exists for this job.")
    return resume_read(resume)


@app.get("/api/jobs/{job_id}/resumes", response_model=list[GeneratedResumeRead])
def job_resume_history(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[GeneratedResumeRead]:
    resumes = db.scalars(
        select(GeneratedResume)
        .where(GeneratedResume.user_id == user_id, GeneratedResume.job_id == job_id)
        .order_by(GeneratedResume.version.desc())
    )
    return [resume_read(item) for item in resumes]


@app.get("/api/generated-resumes/{resume_id}/pdf")
def generated_resume_pdf(
    resume_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Response:
    resume = db.scalar(
        select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == user_id,
            GeneratedResume.status == "compiled",
        )
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Generated resume not found.")
    job = db.get(Job, resume.job_id)
    try:
        pdf = compile_latex(resume.latex_source)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = sanitize_filename(
        f"{CANONICAL_NAME}_{CANONICAL_DEGREE}_{job.company if job else ''}_{resume.target_role}_Resume"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}.pdf"'},
    )


@app.get("/api/generated-resumes/{resume_id}/tex")
def generated_resume_tex(
    resume_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Response:
    resume = db.scalar(
        select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == user_id,
        )
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Generated resume not found.")
    filename = sanitize_filename(
        f"{CANONICAL_NAME}_{CANONICAL_DEGREE}_{resume.target_role}_Resume"
    )
    return Response(
        content=resume.latex_source,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}.tex"'},
    )


@app.post("/api/jobs/{job_id}/analyze", response_model=JobRead)
def analyze_one_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).options(joinedload(Job.analysis)))
    profile = db.scalar(select(UserProfile).limit(1))
    if not job or not profile:
        raise HTTPException(status_code=404, detail="Job or profile not found")
    persist_analysis(db, job, profile)
    db.commit()
    db.refresh(job)
    return job


@app.get("/api/applications", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    return list(
        db.scalars(
            select(Application)
            .options(joinedload(Application.job))
            .order_by(Application.updated_at.desc())
        ).unique()
    )


@app.post("/api/applications", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> Application:
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    data = payload.model_dump()
    if data["status"] == "Applied" and not data["applied_at"]:
        data["applied_at"] = datetime.now(timezone.utc)
    if data["status"] == "Applied":
        job.status = "applied"
        job.applied_at = data["applied_at"]
    elif data["status"] == "Saved" and job.status == "active":
        job.status = "saved"
    elif data["status"] == "Not interested":
        job.status = "not_interested"
    application = Application(**data)
    db.add(application)
    db.commit()
    saved_application = db.scalar(
        select(Application).where(Application.id == application.id).options(joinedload(Application.job))
    )
    if saved_application:
        _send_follow_up_safely(db, saved_application)
    return saved_application


@app.put("/api/applications/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
) -> Application:
    application = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(joinedload(Application.job))
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == "Applied" and not application.applied_at and "applied_at" not in changes:
        changes["applied_at"] = datetime.now(timezone.utc)
    for key, value in changes.items():
        setattr(application, key, value)
    if changes.get("status") == "Applied":
        application.job.status = "applied"
        application.job.applied_at = changes.get("applied_at") or application.applied_at
    elif changes.get("status") == "Saved" and application.job.status == "active":
        application.job.status = "saved"
    elif changes.get("status") == "Not interested":
        application.job.status = "not_interested"
    db.commit()
    db.refresh(application)
    if "next_action_at" in changes:
        _send_follow_up_safely(db, application)
    return application


@app.post("/api/jobs/{job_id}/mark-applied", response_model=JobLifecycleActionRead)
def mark_job_applied(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> JobLifecycleActionRead:
    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "applied":
        application = db.scalar(
            select(Application)
            .where(Application.job_id == job.id)
            .order_by(Application.updated_at.desc())
            .options(joinedload(Application.job))
            .limit(1)
        )
        return JobLifecycleActionRead(
            job=JobRead.model_validate(job),
            application=ApplicationRead.model_validate(application) if application else None,
            previous_status="saved" if application else "active",
            message="Application marked as submitted and moved to Applied.",
        )
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Only active or saved jobs can be marked as applied; this job is {job.status}.",
        )

    previous_status = job.status
    now = datetime.now(timezone.utc)
    latest_resume = db.scalar(
        select(GeneratedResume)
        .where(
            GeneratedResume.job_id == job.id,
            GeneratedResume.user_id == user_id,
            GeneratedResume.status == "compiled",
        )
        .order_by(GeneratedResume.version.desc())
        .limit(1)
    )
    application = db.scalar(
        select(Application)
        .where(Application.job_id == job.id)
        .order_by(Application.updated_at.desc())
        .limit(1)
    )
    if application is None:
        application = Application(
            job_id=job.id,
            status="Applied",
            applied_at=now,
            resume_type=job.analysis.recommended_resume_type if job.analysis else "General Engineering",
            submitted_resume_id=latest_resume.id if latest_resume else None,
        )
        db.add(application)
    else:
        application.status = "Applied"
        application.applied_at = now
        if application.submitted_resume_id is None and latest_resume:
            application.submitted_resume_id = latest_resume.id
    job.status = "applied"
    job.applied_at = now
    if job.submitted_resume_id is None and latest_resume:
        job.submitted_resume_id = latest_resume.id
    db.commit()

    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    application = db.scalar(
        select(Application)
        .where(Application.id == application.id)
        .options(joinedload(Application.job))
    )
    return JobLifecycleActionRead(
        job=JobRead.model_validate(job),
        application=ApplicationRead.model_validate(application),
        previous_status=previous_status,
        message="Application marked as submitted and moved to Applied.",
    )


@app.post("/api/jobs/{job_id}/undo-applied", response_model=JobLifecycleActionRead)
def undo_job_applied(
    job_id: int,
    payload: UndoAppliedPayload,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> JobLifecycleActionRead:
    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "applied":
        raise HTTPException(status_code=409, detail="This job is not marked as applied.")

    job.status = payload.previous_status
    job.applied_at = None
    application = db.scalar(
        select(Application)
        .where(Application.job_id == job.id, Application.status == "Applied")
        .order_by(Application.updated_at.desc())
        .limit(1)
    )
    if application:
        application.status = "Saved" if payload.previous_status == "saved" else "Draft"
        application.applied_at = None
    db.commit()

    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if application:
        application = db.scalar(
            select(Application)
            .where(Application.id == application.id)
            .options(joinedload(Application.job))
        )
    return JobLifecycleActionRead(
        job=JobRead.model_validate(job),
        application=ApplicationRead.model_validate(application) if application else None,
        previous_status=payload.previous_status,
        message="Application status restored.",
    )


@app.post("/api/jobs/{job_id}/restore", response_model=JobRead)
def restore_job(
    job_id: int,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {"expired", "archived", "not_interested"}:
        raise HTTPException(status_code=409, detail="This job cannot be restored.")
    today = datetime.now(timezone.utc).astimezone(configured_timezone()).date()
    if (
        job.status == "expired"
        and job.application_deadline is not None
        and job.application_deadline < today
    ):
        raise HTTPException(
            status_code=409,
            detail="Correct or remove the past application deadline before restoring this job.",
        )
    job.status = "active"
    job.expired_at = None
    job.archived_at = None
    db.commit()
    db.refresh(job)
    return job


@app.post("/api/jobs/{job_id}/archive", response_model=JobRead)
def archive_job(
    job_id: int,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "archived":
        job.status = "archived"
        job.archived_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
    return job


@app.delete("/api/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: int, db: Session = Depends(get_db)) -> Response:
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(application)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/sources", response_model=list[SourceRead])
def list_sources(db: Session = Depends(get_db)) -> list[CompanySource]:
    return list(db.scalars(select(CompanySource).order_by(
        CompanySource.enabled.desc(), CompanySource.priority.desc(), CompanySource.company
    )))


@app.get("/api/target-companies", response_model=list[TargetCompanyRead])
def list_target_companies(db: Session = Depends(get_db)) -> list[TargetCompany]:
    return list(
        db.scalars(
            select(TargetCompany).order_by(
                case(
                    (TargetCompany.priority == "high", 0),
                    (TargetCompany.priority == "medium", 1),
                    else_=2,
                ),
                TargetCompany.category,
                TargetCompany.company_name,
            )
        )
    )


@app.post(
    "/api/target-companies",
    response_model=TargetCompanyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_target_company(
    payload: TargetCompanyPayload,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> TargetCompany:
    if db.scalar(
        select(TargetCompany.id).where(
            func.lower(TargetCompany.company_name) == payload.company_name.strip().lower()
        )
    ):
        raise HTTPException(status_code=409, detail="Target company already exists.")
    company = TargetCompany(**payload.model_dump(), custom=True)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@app.put("/api/target-companies/{company_id}", response_model=TargetCompanyRead)
def update_target_company(
    company_id: int,
    payload: TargetCompanyUpdate,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> TargetCompany:
    company = db.get(TargetCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Target company not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return company


@app.delete("/api/target-companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target_company(
    company_id: int,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Response:
    company = db.get(TargetCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Target company not found.")
    if not company.custom:
        raise HTTPException(
            status_code=409,
            detail="Seeded companies can be disabled but not deleted.",
        )
    db.delete(company)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/target-companies/search", response_model=TargetSearchRunRead)
async def search_all_target_companies(
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> TargetSearchRun:
    return await search_target_companies(db, force=True, trigger="manual")


@app.post("/api/target-companies/{company_id}/search", response_model=TargetSearchRunRead)
async def search_one_target_company(
    company_id: int,
    _: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> TargetSearchRun:
    if not db.get(TargetCompany, company_id):
        raise HTTPException(status_code=404, detail="Target company not found.")
    return await search_target_companies(
        db,
        force=True,
        company_id=company_id,
        trigger="manual",
    )


@app.get("/api/target-search-runs", response_model=list[TargetSearchRunRead])
def list_target_search_runs(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[TargetSearchRun]:
    return list(
        db.scalars(
            select(TargetSearchRun)
            .order_by(TargetSearchRun.started_at.desc())
            .limit(limit)
        )
    )


@app.post("/api/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> CompanySource:
    if payload.source_type in {
        "greenhouse", "lever", "workday", "smartrecruiters", "embedded_jobs",
        "amazon_jobs", "official_careers", "oracle_recruiting", "community_repo",
    }:
        validate_public_url(payload.source_url)
    source = CompanySource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@app.put("/api/sources/{source_id}", response_model=SourceRead)
def update_source(
    source_id: int,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
) -> CompanySource:
    source = db.get(CompanySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    changes = payload.model_dump(exclude_unset=True)
    new_url = changes.get("source_url")
    source_type = changes.get("source_type", source.source_type)
    if new_url and source_type in {
        "greenhouse", "lever", "workday", "smartrecruiters", "embedded_jobs",
        "amazon_jobs", "official_careers", "oracle_recruiting", "community_repo",
    }:
        validate_public_url(new_url)
    for key, value in changes.items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@app.delete("/api/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> Response:
    source = db.get(CompanySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/notifications", response_model=list[NotificationRead])
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    )


@app.post("/api/notifications/test-connection", response_model=EmailActionResult)
def test_email_connection(db: Session = Depends(get_db)) -> EmailActionResult:
    profile = db.scalar(select(UserProfile).limit(1))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        result = EmailService(db).test_email_connection(profile)
    except Exception:
        return EmailActionResult(
            success=False,
            message="The configured email provider is not supported.",
            provider=settings.email_provider,
        )
    return EmailActionResult(
        success=result.success,
        message=result.message,
        provider=result.provider,
    )


@app.post("/api/notifications/test-email", response_model=EmailActionResult)
def send_test_email(db: Session = Depends(get_db)) -> EmailActionResult:
    profile = db.scalar(select(UserProfile).limit(1))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        result = EmailService(db).send_test_email(profile)
    except Exception:
        db.rollback()
        return EmailActionResult(
            success=False,
            message="The test email could not be prepared. Check the provider configuration.",
            provider=settings.email_provider,
        )
    return EmailActionResult(
        success=result.success,
        message=result.message,
        provider=result.provider,
    )


@app.post("/api/sources/refresh")
async def refresh_sources(db: Session = Depends(get_db)) -> dict:
    return await refresh_all_sources(db)


@app.get("/api/stats", response_model=StatsRead)
def get_stats(db: Session = Depends(get_db)) -> StatsRead:
    expire_past_deadline_jobs(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    hidden_statuses = ["ignored"]
    if not settings.demo_feed_enabled:
        hidden_statuses.append("demo")
    visible_jobs = and_(
        Job.discovery_status.not_in(hidden_statuses),
        Job.status.in_(ACTIVE_JOB_STATUSES),
    )
    recommendation_counts = dict(
        db.execute(
            select(JobAnalysis.recommendation, func.count(JobAnalysis.id))
            .join(Job, JobAnalysis.job_id == Job.id)
            .where(visible_jobs)
            .group_by(JobAnalysis.recommendation)
        ).all()
    )
    latest_run = db.scalar(
        select(SearchRun).order_by(SearchRun.started_at.desc()).limit(1)
    )
    last_completed_run = db.scalar(
        select(SearchRun)
        .where(SearchRun.status.in_(("completed", "partial")))
        .order_by(SearchRun.completed_at.desc())
        .limit(1)
    )
    return StatsRead(
        total_jobs=db.scalar(select(func.count(Job.id)).where(visible_jobs)) or 0,
        new_jobs=db.scalar(
            select(func.count(Job.id)).where(visible_jobs, Job.first_seen_at >= cutoff)
        )
        or 0,
        apply_today=recommendation_counts.get("Apply Today", 0),
        review=recommendation_counts.get("Review", 0),
        needs_verification=recommendation_counts.get("Needs Verification", 0),
        not_eligible=recommendation_counts.get("Not Eligible", 0),
        low_match=recommendation_counts.get("Low Match", 0),
        closed=recommendation_counts.get("Closed", 0),
        priority_alerts=db.scalar(
            select(func.count(Job.id)).where(
                visible_jobs,
                Job.is_priority_alert.is_(True),
                Job.is_active.is_(True),
            )
        )
        or 0,
        urgent=db.scalar(
            select(func.count(Job.id)).where(
                visible_jobs,
                Job.urgency.in_(["Urgent", "Closing Today"]),
                Job.is_active.is_(True),
            )
        )
        or 0,
        applications=db.scalar(select(func.count(Application.id))) or 0,
        last_update=last_completed_run.completed_at if last_completed_run else None,
        latest_search_id=latest_run.id if latest_run else None,
        latest_search_status=latest_run.status if latest_run else None,
        latest_search_progress=latest_run.progress_status if latest_run else None,
        latest_search_errors=latest_run.safe_error_summary if latest_run else "",
    )
