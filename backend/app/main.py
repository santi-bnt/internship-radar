from __future__ import annotations

import asyncio
import logging
import hmac
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal, get_db
from app.jobs.refresh import persist_analysis, refresh_all_sources, revalidate_existing_jobs
from app.jobs.audit_santiago_opportunities import (
    collect_official_audit_jobs,
    upsert_verified_audit_jobs,
)
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.models import (
    Application,
    AuthorizedAccount,
    ApplicationAnswerRegistry,
    ApplicationProfile,
    ApplicationSession,
    AIUserSettings,
    CandidateCorrectionMemory,
    CandidateJobOverride,
    CompanySource,
    ExternalAIAudit,
    Job,
    JobAnalysis,
    KospieProfile,
    Notification,
    UserProfile,
    ResumeProfile,
    GeneratedResume,
    GeneratedPortfolio,
    TargetCompany,
    TargetSearchRun,
    SearchRun,
    SearchRunJob,
    UserApprovedMapping,
)
from app.schemas.api import (
    AISettingsPayload,
    AISettingsRead,
    ApplicationAgentRequest,
    ApplicationAgentResponse,
    ApplicationAnswerConfirmation,
    ApplicationAnswerRead,
    ApplicationCreate,
    ApplicationProfilePayload,
    ApplicationProfileRead,
    ApplicationRead,
    ApplicationReadinessRead,
    ApplicationSessionCreate,
    ApplicationSessionLaunch,
    ApplicationSessionProgress,
    ApplicationSessionRead,
    ApplicationSessionRevokeResult,
    ApplicationSubmittedConfirmation,
    ApplicationUpdate,
    CandidateCorrectionPayload,
    CandidateCorrectionRead,
    EmailActionResult,
    ExtensionApplicationPayload,
    ExternalAIAuditRead,
    JobPage,
    JobRead,
    JobURLImportRequest,
    JobURLImportResponse,
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
    ResumeGenerateRequest,
    ManualJobCreate,
    ResearchOpportunityCreate,
    ResearchOpportunityAnalysisRead,
    KospieAnalysisRead,
    KospieProfilePayload,
    KospieProfileRead,
    VerifiedSkillGroupRead,
    TargetCompanyPayload,
    TargetCompanyRead,
    TargetCompanyUpdate,
    TargetSearchRunRead,
    SearchRunRead,
    SearchRunDeleteResult,
    SearchCriteria,
    UndoAppliedPayload,
    UserApprovedMappingPayload,
    UserApprovedMappingRead,
)
from app.services.email_service import EmailService
from app.services.job_lifecycle import (
    ACTIVE_JOB_STATUSES,
    JOB_STATUSES,
    configured_timezone,
    expire_past_deadline_jobs,
)
from app.services.normalization import validate_public_url
from app.services.job_url_import import (
    JobExtractionError,
    extract_job_url,
    persist_imported_job_for_all_profiles,
)
from app.services.safe_job_fetch import JobFetchError, UnsafeJobURL
from app.services.application_assistant import (
    FIELD_POLICIES,
    AUTO_FILL_REVIEW_QUESTION_KEYS,
    SENSITIVE_QUESTION_KEYS,
    application_readiness,
    classify_question,
    detect_portal,
    get_or_create_application_profile,
    get_or_create_role_specific_portfolio,
    profile_snapshot,
    validate_application_consistency,
)
from app.services.company_portal_registry import PORTAL_SUPPORT, company_policy, direct_application_url
from app.services.application_selection import build_application_selection
from app.services.application_agent import ApplicationAgent
from app.services.seed import ensure_santiago_resume_projects, seed_profile_and_sources
from app.services.santiago_certifications import ensure_santiago_verified_certifications
from app.services.candidate_registry import INDEPENDENT_CANDIDATE_SEEDS
from app.services.multi_user_seed import (
    ensure_candidate_job_catalog, ensure_independent_candidate_job_catalogs,
    ensure_joshua_job_catalog,
    seed_authorized_accounts_and_candidates, seed_independent_candidate,
)
from app.services.force_apply import (
    apply_requested_santiago_overrides,
    can_force_apply_now,
    force_apply_action_is_active,
    is_application_confirmed_unavailable,
    set_force_apply_now,
)
from app.services.discovery_orchestration import discovery_status
from app.services.resume_generation import (
    CANONICAL_DEGREE,
    CANONICAL_LINKEDIN,
    CANONICAL_NAME,
    compile_latex,
    content_hash,
    generate_resume,
    resume_generation_input_hash,
    resume_filename,
    sanitize_filename,
    sanitize_resume_text,
)
from app.services.resume_skills import grouped_verified_skill_registry
from app.services.tailoring_plan import job_content_hash
from app.services.resume_generation_queue import resume_generation_queue
from app.services.research_opportunities import analyze_research_opportunity
from app.services.resume_studio import (
    STUDIO_PROFILES, analyze_studio_profile, build_studio_job, studio_config,
)
from app.services.best_resume import (
    BestResumePlan,
    best_resume_profile_version,
    best_resume_profile_snapshot,
    build_best_resume_job,
    build_best_resume_plan,
)
from app.services.kospie import (
    DEFAULT_INTERESTS,
    DEFAULT_UNIVERSITIES,
    analyze_kospie_profile,
    build_kospie_job,
)
from app.services.language_evidence import (
    canonical_language_credentials,
    language_certifications,
    resume_language_lines,
)
from app.jobs.target_search import search_target_companies
from app.jobs.import_santiago_force_apply import ensure_santiago_requested_opportunities
from app.services.search_runs import create_search_run, execute_search_run, fail_abandoned_search_runs
from app.security.audit import audit_event
from app.security.identity import (
    AuthenticatedIdentity,
    IdentityValidationError,
    JOSHUA_USER_ID,
    ALONSO_USER_ID,
    validate_user_identity,
)
from app.security.application_session_token import (
    ApplicationSessionClaims,
    ApplicationTokenError,
    create_application_session_token,
    validate_application_session_token,
)
from app.security.rate_limit import check_rate_limit, sensitive_operation


logger = logging.getLogger(__name__)


def _job_with_candidate_override(job_statement, user_id: str):
    """Eager-load only the requesting candidate's action override."""
    return job_statement.options(
        joinedload(Job.analysis),
        joinedload(Job.candidate_job_override.and_(
            CandidateJobOverride.owner_user_id == user_id
        )),
    )


def _force_apply_active_clause(user_id: str):
    # SQL's ``NULL NOT IN (...)`` is unknown rather than true.  Candidate
    # supplied official URLs can legitimately be pending verification, which
    # means these two status fields are null/unknown.  A manual action must
    # remain visible in that state unless the source has affirmatively reported
    # a terminal state.
    official_not_confirmed_closed = or_(
        Job.official_status.is_(None),
        Job.official_status.not_in({"closed", "expired", "unavailable"}),
    )
    application_not_confirmed_dead = or_(
        Job.application_url_status.is_(None),
        Job.application_url_status.not_in({"INACTIVE", "UNAVAILABLE", "EXPIRED"}),
    )
    return (
        official_not_confirmed_closed
        & application_not_confirmed_dead
        & or_(
            Job.official_apply_url.is_not(None),
            Job.application_url != "",
            Job.apply_url != "",
        )
        & Job.candidate_job_override.has(
            and_(
                CandidateJobOverride.owner_user_id == user_id,
                CandidateJobOverride.force_apply_now.is_(True),
            )
        )
    )


def _require_santiago_force_apply_access(user_id: str) -> None:
    if user_id != settings.effective_primary_user_id:
        raise HTTPException(status_code=403, detail="Force Apply Now is available only to Santiago.")


def require_private_api(request: Request) -> str:
    identity = getattr(request.state, "authenticated_identity", None)
    if not isinstance(identity, AuthenticatedIdentity):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return identity.primary_user_id


def require_extension_session(
    request: Request,
    db: Session = Depends(get_db),
) -> ApplicationSession:
    claims = getattr(request.state, "application_session_claims", None)
    if not isinstance(claims, ApplicationSessionClaims):
        raise HTTPException(status_code=401, detail="Application session authentication required.")
    session = db.scalar(
        select(ApplicationSession).where(
            ApplicationSession.id == claims.session_id,
            ApplicationSession.owner_user_id == claims.owner_user_id,
        )
    )
    if not session or not session.token_nonce or not hmac.compare_digest(
        session.token_nonce, claims.nonce
    ):
        raise HTTPException(status_code=401, detail="Application session token was revoked.")
    if session.status in {"ABANDONED", "ERROR"}:
        raise HTTPException(status_code=409, detail="Application session is not active.")
    return session


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


def _retryable_generation_failure(exc: Exception) -> bool:
    message = str(exc).casefold()
    return isinstance(exc, (ConnectionError, TimeoutError)) or any(
        token in message for token in ("timed out", "temporar", "connection", "503", "502")
    )


def _run_job_resume_generation(record_id: int) -> None:
    """Worker entry point. It owns its DB session, never a request session."""
    with SessionLocal() as worker_db:
        record = worker_db.get(GeneratedResume, record_id)
        if not record or record.status not in {"queued", "generating", "failed_retryable"}:
            return
        job = worker_db.scalar(select(Job).where(Job.id == record.job_id, Job.owner_user_id == record.user_id))
        profile = worker_db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == record.user_id))
        if not job or not profile:
            record.status, record.active_generation_owner = "failed", None
            record.generation_error = "The job or candidate profile is no longer available."
            worker_db.commit()
            return
        record.status, record.active_generation_owner = "generating", record.user_id
        worker_db.commit()
        try:
            if settings.resume_generation_provider.strip().lower() == "openai":
                worker_db.add(ExternalAIAudit(
                    owner_user_id=record.user_id,
                    provider="openai",
                    purpose="job_specific_resume_tailoring",
                    privacy_classification="NORMAL",
                    fields_included_json=[
                        "education_summary", "verified_skills", "verified_projects",
                        "verified_work_experience", "languages", "forbidden_claims",
                        "job_title", "company", "job_description", "job_requirements",
                    ],
                    fields_redacted_json=[
                        "full_name", "email", "phone", "location", "linkedin_url", "github_url",
                    ],
                ))
                worker_db.commit()
            content, latex_source, pdf_bytes = generate_resume(job, profile, record.id)
            plan_snapshot = content.tailoring_plan or {}
            if plan_snapshot and (
                plan_snapshot.get("job_id") != job.id
                or plan_snapshot.get("owner_user_id") != record.user_id
                or plan_snapshot.get("job_content_hash") != job_content_hash(job)
            ):
                raise ValueError("Generated TailoringPlan does not match the current resume context.")
            record.status, record.active_generation_owner = "compiled", None
            record.target_role = content.target_role
            record.tailored_content_json, record.latex_source = content.model_dump(), latex_source
            record.compiled_pdf, record.compiled_pdf_at = pdf_bytes, datetime.now(timezone.utc)
            record.match_score = content.match_score
            record.keywords_json = {"included": content.keywords_used, "supported_not_included": [], "missing": content.keywords_missing, "refused": content.unsupported_requirements}
            record.changes_json = [item.model_dump() for item in content.changes]
            record.warnings_json = content.warnings + content.unsupported_requirements
            record.selected_skills = content.selected_skills
            record.skill_categories = [group.model_dump() for group in content.skill_categories]
            record.job_skill_matches = [item.model_dump() for item in content.job_skill_matches]
            record.skill_verification = content.skill_verification.model_dump()
            record.content_hash, record.generation_error = content_hash(content, latex_source), None
            worker_db.commit()
        except Exception as exc:
            worker_db.rollback()
            record = worker_db.get(GeneratedResume, record_id)
            if record:
                record.status = "failed_retryable" if _retryable_generation_failure(exc) else "failed"
                record.active_generation_owner, record.generation_error = None, str(exc)[:1200]
                worker_db.commit()
            logger.exception("Queued resume generation %s failed", record_id)


def _run_best_resume_generation(record_id: int) -> None:
    """Generate a Best Resume off-request from its immutable candidate snapshot."""
    with SessionLocal() as worker_db:
        record = worker_db.get(GeneratedResume, record_id)
        if not record or record.application_type != "BEST_RESUME" or record.status not in {
            "queued", "generating", "failed_retryable",
        }:
            return
        company_profile = record.company_profile or {}
        profile_snapshot = company_profile.get("profile_snapshot")
        try:
            profile = SimpleNamespace(**profile_snapshot)
            plan = BestResumePlan.model_validate(company_profile.get("best_resume_plan"))
            if (
                company_profile.get("candidate_id") != record.user_id
                or plan.candidate_id != record.user_id
                or plan.profile_version != best_resume_profile_version(profile)
                or plan.profile_version != record.source_input_hash
            ):
                raise ValueError("Best Resume snapshot does not match its candidate or source profile.")
            job = build_best_resume_job(profile, record.user_id, plan)
        except Exception as exc:
            record.status, record.active_generation_owner = "failed", None
            record.generation_error = str(exc)[:1200]
            worker_db.commit()
            logger.exception("Queued Best Resume %s has an invalid snapshot", record_id)
            return

        record.status = "generating"
        record.active_generation_owner = record.user_id
        worker_db.commit()
        try:
            content, latex_source, pdf_bytes = generate_resume(job, profile, record.id)
            record.status, record.active_generation_owner = "compiled", None
            record.tailored_content_json = content.model_dump()
            record.latex_source = latex_source
            record.compiled_pdf = pdf_bytes
            record.compiled_pdf_at = datetime.now(timezone.utc)
            record.match_score = content.match_score
            record.selected_skills = content.selected_skills
            record.skill_categories = [group.model_dump() for group in content.skill_categories]
            record.job_skill_matches = [item.model_dump() for item in content.job_skill_matches]
            record.skill_verification = content.skill_verification.model_dump()
            record.changes_json = [item.model_dump() for item in content.changes]
            record.warnings_json = content.warnings
            record.keywords_json = {"included": content.selected_skills, "missing": []}
            record.content_hash = content_hash(content, latex_source)
            record.generation_error = None
            worker_db.commit()
        except Exception as exc:
            worker_db.rollback()
            record = worker_db.get(GeneratedResume, record_id)
            if record:
                record.status = "failed_retryable" if _retryable_generation_failure(exc) else "failed"
                record.active_generation_owner = None
                record.generation_error = str(exc)[:1200]
                worker_db.commit()
            logger.exception("Queued Best Resume generation %s failed", record_id)


def portfolio_read(portfolio: GeneratedPortfolio) -> dict[str, object]:
    return {
        "id": portfolio.id,
        "version": portfolio.version,
        "status": portfolio.status,
        "filename": portfolio.filename,
        "target_role": portfolio.target_role,
        "selected_projects": portfolio.selected_projects_json,
        "pdf_url": f"/api/extension/application-session/portfolio.pdf",
    }


def application_session_read(session: ApplicationSession) -> ApplicationSessionRead:
    return ApplicationSessionRead.model_validate(session)


def require_extension_scope(request: Request, scope: str) -> ApplicationSessionClaims:
    claims = getattr(request.state, "application_session_claims", None)
    if not isinstance(claims, ApplicationSessionClaims):
        raise HTTPException(status_code=401, detail="Application session authentication required.")
    try:
        claims.requires(scope)
    except ApplicationTokenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return claims


def get_or_create_ai_settings(db: Session, owner_user_id: str) -> AIUserSettings:
    record = db.get(AIUserSettings, owner_user_id)
    if record is None:
        configured_mode = settings.ai_mode.strip().upper()
        if configured_mode not in {"LOCAL_ONLY", "BALANCED", "EXTERNAL_ALLOWED"}:
            configured_mode = "BALANCED"
        record = AIUserSettings(
            owner_user_id=owner_user_id,
            ai_mode=configured_mode,
        )
        db.add(record)
        db.flush()
    return record


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
    if settings.public_demo_mode:
        init_db()
        with SessionLocal() as db:
            seed_profile_and_sources(db)
            if db.scalar(select(Job.id).limit(1)) is None:
                await refresh_all_sources(db, source_types={"local_json"})
    if settings.environment.strip().lower() != "production":
        init_db()
        with SessionLocal() as db:
            seed_profile_and_sources(db)
            santiago_resume = db.scalar(select(ResumeProfile).where(
                ResumeProfile.user_id == settings.effective_primary_user_id,
            ))
            if santiago_resume is not None:
                ensure_santiago_verified_certifications(santiago_resume)
                db.commit()
            seed_authorized_accounts_and_candidates(db)
            ensure_joshua_job_catalog(db)
            ensure_independent_candidate_job_catalogs(db)
            joshua_profile = db.scalar(select(UserProfile).where(
                UserProfile.owner_user_id == JOSHUA_USER_ID
            ))
            if joshua_profile:
                for job in db.scalars(select(Job).outerjoin(JobAnalysis).where(
                    Job.owner_user_id == JOSHUA_USER_ID,
                    JobAnalysis.id.is_(None),
                ).limit(25)):
                    persist_analysis(db, job, joshua_profile)
                db.commit()
            alonso_profile = db.scalar(select(UserProfile).where(
                UserProfile.owner_user_id == ALONSO_USER_ID
            ))
            if alonso_profile:
                for job in db.scalars(select(Job).outerjoin(JobAnalysis).where(
                    Job.owner_user_id == ALONSO_USER_ID,
                    JobAnalysis.id.is_(None),
                ).limit(25)):
                    persist_analysis(db, job, alonso_profile)
                db.commit()
            if db.scalar(select(Job.id).limit(1)) is None:
                await refresh_all_sources(db, source_types={"local_json"})
    else:
        with SessionLocal() as db:
            # These exact records are Santiago-only. The upsert is idempotent
            # and never reads or writes Joshua's or Alonso's resume profiles.
            santiago_resume = db.scalar(select(ResumeProfile).where(
                ResumeProfile.user_id == settings.effective_primary_user_id,
            ))
            if santiago_resume is not None:
                ensure_santiago_verified_certifications(santiago_resume)
                ensure_santiago_resume_projects(santiago_resume)
                # Exact Santiago-requested Handshake and Guadalajara roles
                # must be stored in production, not left in an operator-only
                # import script waiting for an unset environment variable.
                ensure_santiago_requested_opportunities(
                    db, settings.effective_primary_user_id,
                )
            for candidate in INDEPENDENT_CANDIDATE_SEEDS:
                seed_independent_candidate(db, candidate)
                ensure_candidate_job_catalog(db, candidate.user_id)
            # A deploy can interrupt an in-process worker. Keep the immutable
            # record and either resume queued work or make an interrupted task
            # explicitly retryable; never leave the UI polling forever.
            interrupted = db.scalars(select(GeneratedResume).where(
                GeneratedResume.status == "generating",
            )).all()
            for record in interrupted:
                record.status = "failed_retryable"
                record.active_generation_owner = None
                record.generation_error = "Generation was interrupted by a service restart. Retry to continue."
            queued_tasks: list[tuple[int, str, bool]] = []
            for record in db.scalars(select(GeneratedResume).where(
                GeneratedResume.status == "queued",
            )).all():
                is_best_resume = (
                    record.application_type == "BEST_RESUME"
                    and record.company_id == BEST_RESUME_COMPANY_ID
                    and record.job_id is None
                )
                if is_best_resume or record.job_id is not None:
                    queued_tasks.append((record.id, record.user_id, is_best_resume))
            db.commit()
        for record_id, owner_user_id, is_best_resume in queued_tasks:
            resume_generation_queue.enqueue(
                owner_user_id,
                lambda generation_id=record_id, best=is_best_resume: (
                    _run_best_resume_generation(generation_id)
                    if best else _run_job_resume_generation(generation_id)
                ),
            )
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
    local_development = (
        settings.local_development_mode
        and settings.environment.strip().lower() != "production"
    )
    if not settings.app_access_enabled and not local_development:
        return JSONResponse(
            {"detail": "Internship Radar is temporarily unavailable."},
            status_code=503,
            headers={"Cache-Control": "no-store", "Retry-After": "3600"},
        )

    extension_request = path.startswith("/api/extension/")
    if extension_request:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        try:
            claims = validate_application_session_token(token)
        except ApplicationTokenError:
            audit_event("extension_access_rejected", resource=path, outcome="invalid_session_token")
            return JSONResponse(
                {"detail": "Application session authentication required."},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        request.state.application_session_claims = claims
        identity = AuthenticatedIdentity(
            primary_user_id=claims.owner_user_id,
            authenticated_email="extension-session@internship-radar.invalid",
            issued_at=claims.issued_at,
            expires_at=claims.expires_at,
            nonce=claims.nonce,
        )
    elif local_development:
        now = int(datetime.now(timezone.utc).timestamp())
        identity = AuthenticatedIdentity(
            primary_user_id=settings.effective_primary_user_id,
            authenticated_email="local@internship-radar.test",
            issued_at=now,
            expires_at=now + 3600,
            nonce="local-development",
        )
    else:
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
        with SessionLocal() as identity_db:
            account = identity_db.scalar(select(AuthorizedAccount).where(
                AuthorizedAccount.user_id == identity.primary_user_id,
                AuthorizedAccount.email == identity.authenticated_email,
                AuthorizedAccount.provider == "google",
                AuthorizedAccount.is_active.is_(True),
            ))
        if not account:
            audit_event("backend_access_rejected", email=identity.authenticated_email, resource=path, outcome="inactive_account")
            return JSONResponse({"detail": "Access denied."}, status_code=403, headers={"Cache-Control": "no-store"})
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
                {
                    "error": "resume_generation_rate_limit" if rule.key == "resume" else "rate_limit",
                    "detail": "Resume generation limit reached." if rule.key == "resume" else "Too many requests. Try again later.",
                    "message": "Resume generation limit reached." if rule.key == "resume" else "Too many requests. Try again later.",
                    "retry_after_seconds": retry_after,
                },
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
def health() -> dict[str, str | None]:
    # Render uses this as a liveness probe. It must never wait for PostgreSQL,
    # LaTeX, source refreshes, or any other dependency that can be slow.
    return {
        "status": "ok",
        "database": "not_checked",
        "latex_compiler": "not_checked",
        "scheduler": (
            "configured"
            if settings.scheduler_enabled and settings.search_scheduler_enabled
            else "external_cron"
        ),
        "last_successful_search": None,
    }


@app.get("/api/profile", response_model=ProfileRead)
def get_profile(user_id: str = Depends(require_private_api), db: Session = Depends(get_db)) -> UserProfile:
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.put("/api/profile", response_model=ProfileRead)
def update_profile(payload: ProfilePayload, user_id: str = Depends(require_private_api), db: Session = Depends(get_db)) -> UserProfile:
    if "@" not in payload.notification_email or "." not in payload.notification_email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid notification email address.")
    values = payload.model_dump()
    if user_id == settings.effective_primary_user_id:
        values["linkedin_url"] = CANONICAL_LINKEDIN
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    if not profile:
        profile = UserProfile(owner_user_id=user_id, **values)
        db.add(profile)
    else:
        for key, value in values.items():
            setattr(profile, key, value)
    db.flush()
    for job in db.scalars(select(Job).where(Job.owner_user_id == user_id).options(joinedload(Job.analysis))):
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
    values = payload.model_dump()
    if user_id == settings.effective_primary_user_id:
        values["linkedin_url"] = CANONICAL_LINKEDIN
    credentials = canonical_language_credentials(SimpleNamespace(**values))
    values["language_credentials_json"] = credentials
    values["certifications_json"] = language_certifications(
        credentials,
        values["certifications_json"],
    )
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile:
        profile = ResumeProfile(user_id=user_id, **values)
        db.add(profile)
    else:
        for key, value in values.items():
            setattr(profile, key, value)
    db.flush()
    application_profile = db.scalar(
        select(ApplicationProfile).where(ApplicationProfile.owner_user_id == user_id)
    )
    if application_profile:
        application_profile.languages_json = resume_language_lines(profile)
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


@app.get("/api/application-profile", response_model=ApplicationProfileRead)
def get_application_profile(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationProfile:
    profile = get_or_create_application_profile(db, user_id)
    db.commit()
    db.refresh(profile)
    return profile


@app.put("/api/application-profile", response_model=ApplicationProfileRead)
def update_application_profile(
    payload: ApplicationProfilePayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationProfile:
    profile = get_or_create_application_profile(db, user_id)
    values = payload.model_dump()
    if user_id == settings.effective_primary_user_id:
        values["linkedin_url"] = CANONICAL_LINKEDIN
    for key, value in values.items():
        setattr(profile, key, value)
    profile.application_preferences_confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def _get_or_create_kospie_profile(db: Session, user_id: str) -> KospieProfile:
    profile = db.scalar(select(KospieProfile).where(KospieProfile.owner_user_id == user_id))
    if profile is None:
        profile = KospieProfile(
            owner_user_id=user_id,
            selected_universities_json=list(DEFAULT_UNIVERSITIES),
            primary_interests_json=list(DEFAULT_INTERESTS),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _studio_candidate(db: Session, user_id: str, profile_id: str) -> ResumeProfile:
    try:
        studio_config(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile or not profile.full_name or not profile.education_json:
        raise HTTPException(status_code=422, detail="Complete Resume Profile before using Resume Studio.")
    return profile


@app.get("/api/resume-studio/profiles")
def list_studio_profiles(user_id: str = Depends(require_private_api)) -> list[dict[str, str]]:
    return [{"id": key, "label": value["label"], "description": value["description"]} for key, value in STUDIO_PROFILES.items()]


@app.get("/api/resume-studio/analysis")
def analyze_resume_studio(
    profile_id: str = "general",
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = _studio_candidate(db, user_id, profile_id)
    try:
        return analyze_studio_profile(profile, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/resume-studio/resumes", response_model=list[GeneratedResumeRead])
def list_resume_studio_versions(
    profile_id: str = "general",
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[GeneratedResumeRead]:
    _studio_candidate(db, user_id, profile_id)
    records = db.scalars(select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.application_type == "PROFILE_PORTFOLIO",
        GeneratedResume.company_id == f"profile-cv-{profile_id}",
    ).order_by(GeneratedResume.version.desc())).all()
    return [resume_read(record) for record in records]


@app.post("/api/resume-studio/resumes", response_model=GeneratedResumeRead)
def generate_resume_studio_version(
    profile_id: str = "general",
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    profile = _studio_candidate(db, user_id, profile_id)
    try:
        analysis = analyze_studio_profile(profile, profile_id)
        if not analysis["can_generate"]:
            raise ValueError("Add at least two substantial projects before generating a CV.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = build_studio_job(profile_id)
    company_id = f"profile-cv-{profile_id}"
    version = db.scalar(select(func.max(GeneratedResume.version)).where(
        GeneratedResume.user_id == user_id, GeneratedResume.company_id == company_id,
    )) or 0
    record = GeneratedResume(
        user_id=user_id, job_id=None, application_type="PROFILE_PORTFOLIO",
        company_id=company_id, company="Personal portfolio",
        company_profile={"profile_id": profile_id, "analysis": analysis},
        target_role_categories=[analysis["label"]], version=version + 1,
        status="generating", target_role=job.title, resume_target=job.resume_target,
        content_hash="pending", generation_model="local",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        content, latex_source, pdf_bytes = generate_resume(job, profile, record.id)
        record.status = "compiled"
        record.tailored_content_json = content.model_dump()
        record.latex_source = latex_source
        record.compiled_pdf = pdf_bytes
        record.compiled_pdf_at = datetime.now(timezone.utc)
        record.match_score = content.match_score
        record.selected_skills = content.selected_skills
        record.skill_categories = [group.model_dump() for group in content.skill_categories]
        record.job_skill_matches = [item.model_dump() for item in content.job_skill_matches]
        record.skill_verification = content.skill_verification.model_dump()
        record.changes_json = [item.model_dump() for item in content.changes]
        record.warnings_json = content.warnings
        record.keywords_json = {"included": content.selected_skills, "missing": []}
        record.content_hash = content_hash(content, latex_source)
        db.commit()
        db.refresh(record)
        return resume_read(record)
    except Exception as exc:
        record.status = "failed"
        record.generation_error = str(exc)[:1200]
        db.commit()
        if isinstance(exc, (ValueError, RuntimeError)):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.exception("Resume Studio generation failed")
        raise HTTPException(status_code=502, detail="CV generation failed. Please try again.") from exc


BEST_RESUME_COMPANY_ID = "candidate-best-resume"


def _best_resume_versions(db: Session, user_id: str) -> list[GeneratedResume]:
    profile = _studio_candidate(db, user_id, "general")
    current_version = best_resume_profile_version(profile)
    records = db.scalars(select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.application_type == "BEST_RESUME",
        GeneratedResume.company_id == BEST_RESUME_COMPANY_ID,
    ).order_by(GeneratedResume.version.desc())).all()
    for record in records:
        record._profile_is_stale = record.source_input_hash != current_version
    return records


@app.get("/api/best-resume/analysis")
def analyze_best_resume(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = _studio_candidate(db, user_id, "general")
    plan = build_best_resume_plan(profile, user_id)
    return {
        "candidate_id": user_id,
        "profile_version": plan.profile_version,
        "can_generate": True,
        "description": "Generate a resume using your strongest verified projects, experience, skills, and certifications.",
        "plan": plan.model_dump(mode="json"),
    }


@app.get("/api/best-resume/versions", response_model=list[GeneratedResumeRead])
def list_best_resume_versions(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[GeneratedResumeRead]:
    records = _best_resume_versions(db, user_id)
    return [
        resume_read(record).model_copy(update={"is_stale": bool(getattr(record, "_profile_is_stale", False))})
        for record in records
    ]


@app.post("/api/best-resume/versions", response_model=GeneratedResumeRead)
def generate_best_resume_version(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    profile = _studio_candidate(db, user_id, "general")
    plan = build_best_resume_plan(profile, user_id)

    in_flight = db.scalar(select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.application_type == "BEST_RESUME",
        GeneratedResume.company_id == BEST_RESUME_COMPANY_ID,
        GeneratedResume.status.in_(["queued", "generating"]),
    ).order_by(GeneratedResume.version.desc()))
    if in_flight:
        return resume_read(in_flight)

    retryable = db.scalar(select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.application_type == "BEST_RESUME",
        GeneratedResume.company_id == BEST_RESUME_COMPANY_ID,
        GeneratedResume.status == "failed_retryable",
    ).order_by(GeneratedResume.version.desc()).limit(1))
    if retryable and retryable.source_input_hash == plan.profile_version:
        retryable.status = "queued"
        retryable.generation_error = None
        db.commit()
        resume_generation_queue.enqueue(
            user_id, lambda generation_id=retryable.id: _run_best_resume_generation(generation_id),
        )
        db.refresh(retryable)
        return resume_read(retryable)

    version = db.scalar(select(func.max(GeneratedResume.version)).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.application_type == "BEST_RESUME",
        GeneratedResume.company_id == BEST_RESUME_COMPANY_ID,
    )) or 0
    record = GeneratedResume(
        user_id=user_id,
        job_id=None,
        application_type="BEST_RESUME",
        company_id=BEST_RESUME_COMPANY_ID,
        company="Candidate",
        company_profile={
            "candidate_id": user_id,
            "best_resume_plan": plan.model_dump(mode="json"),
            "profile_version": plan.profile_version,
            "profile_snapshot": best_resume_profile_snapshot(profile),
        },
        target_role_categories=["General Engineering"],
        version=version + 1,
        status="queued",
        target_role="Best Resume",
        resume_target="best_resume",
        content_hash="pending",
        source_input_hash=plan.profile_version,
        generation_model="local",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    resume_generation_queue.enqueue(
        user_id, lambda generation_id=record.id: _run_best_resume_generation(generation_id),
    )
    db.refresh(record)
    return resume_read(record).model_copy(update={"is_stale": False})


@app.get("/api/kospie/profile", response_model=KospieProfileRead)
def get_kospie_profile(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> KospieProfile:
    return _get_or_create_kospie_profile(db, user_id)


@app.put("/api/kospie/profile", response_model=KospieProfileRead)
def update_kospie_profile(
    payload: KospieProfilePayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> KospieProfile:
    profile = _get_or_create_kospie_profile(db, user_id)
    profile.selected_universities_json = payload.selected_universities_json
    profile.primary_interests_json = payload.primary_interests_json
    db.commit()
    db.refresh(profile)
    return profile


@app.post("/api/kospie/analyze", response_model=KospieAnalysisRead)
def analyze_kospie(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> KospieAnalysisRead:
    resume_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not resume_profile or not resume_profile.education_json:
        raise HTTPException(status_code=422, detail="Complete Resume Profile before KOSPIE analysis.")
    candidate = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    config = _get_or_create_kospie_profile(db, user_id)
    try:
        return KospieAnalysisRead.model_validate(analyze_kospie_profile(resume_profile, candidate, config))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/kospie/resumes", response_model=GeneratedResumeRead)
def generate_kospie_resume(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    resume_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not resume_profile or not resume_profile.full_name or not resume_profile.education_json:
        raise HTTPException(status_code=422, detail="Complete Resume Profile before generating a KOSPIE CV.")
    candidate = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    config = _get_or_create_kospie_profile(db, user_id)
    latest_version = db.scalar(select(func.max(GeneratedResume.version)).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.company_id == "kospie-daad",
    )) or 0
    record = GeneratedResume(
        user_id=user_id, job_id=None, application_type="KOSPIE_PROGRAM",
        company_id="kospie-daad", company=config.organization,
        company_profile={
            "program_name": config.program_name,
            "organization": config.organization,
            "program_type": config.program_type,
            "selected_universities": list(config.selected_universities_json),
            "primary_interests": list(config.primary_interests_json),
        },
        target_role_categories=list(config.primary_interests_json), version=latest_version + 1,
        status="generating", target_role="KOSPIE 2027-2028 Engineering CV",
        resume_target="kospie_germany", content_hash="pending", generation_model="local",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        job = build_kospie_job(config, resume_profile, candidate)
        content, latex_source, pdf_bytes = generate_resume(job, resume_profile, record.id)
        analysis = analyze_kospie_profile(resume_profile, candidate, config)
        content.program_eligibility = analysis["eligibility"]
        record.status = "compiled"
        record.tailored_content_json = content.model_dump()
        record.latex_source = latex_source
        record.compiled_pdf = pdf_bytes
        record.compiled_pdf_at = datetime.now(timezone.utc)
        record.match_score = content.match_score
        record.keywords_json = {
            "included": content.keywords_used, "supported_not_included": [],
            "missing": [], "refused": [],
        }
        record.changes_json = [item.model_dump() for item in content.changes]
        record.warnings_json = content.warnings
        record.selected_skills = content.selected_skills
        record.skill_categories = [group.model_dump() for group in content.skill_categories]
        record.job_skill_matches = [item.model_dump() for item in content.job_skill_matches]
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
        raise HTTPException(status_code=502, detail="KOSPIE CV generation failed.") from exc


@app.get("/api/kospie/resumes", response_model=list[GeneratedResumeRead])
def list_kospie_resumes(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[GeneratedResumeRead]:
    resumes = db.scalars(select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.company_id == "kospie-daad",
        GeneratedResume.resume_target == "kospie_germany",
    ).order_by(GeneratedResume.version.desc())).all()
    return [resume_read(item) for item in resumes]


@app.get("/api/ai-settings", response_model=AISettingsRead)
def get_ai_settings(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> AIUserSettings:
    record = get_or_create_ai_settings(db, user_id)
    db.commit()
    db.refresh(record)
    return record


@app.put("/api/ai-settings", response_model=AISettingsRead)
def update_ai_settings(
    payload: AISettingsPayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> AIUserSettings:
    record = get_or_create_ai_settings(db, user_id)
    record.ai_mode = payload.ai_mode
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/ai-privacy-activity", response_model=list[ExternalAIAuditRead])
def list_ai_privacy_activity(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[ExternalAIAudit]:
    return list(db.scalars(
        select(ExternalAIAudit)
        .where(ExternalAIAudit.owner_user_id == user_id)
        .order_by(ExternalAIAudit.created_at.desc())
        .limit(50)
    ))


@app.post(
    "/api/ai-approved-mappings",
    response_model=UserApprovedMappingRead,
    status_code=status.HTTP_201_CREATED,
)
def approve_ai_mapping(
    payload: UserApprovedMappingPayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> UserApprovedMapping:
    record = db.scalar(select(UserApprovedMapping).where(
        UserApprovedMapping.owner_user_id == user_id,
        UserApprovedMapping.portal == payload.portal,
        UserApprovedMapping.canonical_field == payload.canonical_field,
        UserApprovedMapping.canonical_value == payload.canonical_value,
        UserApprovedMapping.portal_option == payload.portal_option,
    ))
    if record is None:
        record = UserApprovedMapping(owner_user_id=user_id, **payload.model_dump())
        db.add(record)
    else:
        record.match_type = payload.match_type
        record.approved_by_user = True
        record.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


@app.post(
    "/api/ai-corrections",
    response_model=CandidateCorrectionRead,
    status_code=status.HTTP_201_CREATED,
)
def remember_ai_correction(
    payload: CandidateCorrectionPayload,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> CandidateCorrectionMemory:
    if payload.application_session_id is not None:
        application_session = db.get(ApplicationSession, payload.application_session_id)
        if application_session is None or application_session.owner_user_id != user_id:
            raise HTTPException(status_code=404, detail="Application session not found.")
    if payload.scope == "APPLICATION_ONLY" and payload.application_session_id is None:
        raise HTTPException(status_code=422, detail="Application-only corrections require a session.")
    record = CandidateCorrectionMemory(
        owner_user_id=user_id,
        scope=payload.scope,
        portal=payload.portal,
        company=payload.company,
        canonical_field=payload.canonical_field,
        old_value_json={"value": payload.old_value},
        corrected_value_json={"value": payload.corrected_value},
        application_session_id=payload.application_session_id,
        verified=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get(
    "/api/jobs/{job_id}/application-readiness",
    response_model=ApplicationReadinessRead,
)
def get_application_readiness(
    job_id: int,
    resume_version_id: int | None = None,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationReadinessRead:
    job = db.scalar(
        select(Job).where(Job.id == job_id).options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    profile = get_or_create_application_profile(db, user_id)
    candidate = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    resume_query = (
        select(GeneratedResume)
        .where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
            GeneratedResume.status == "compiled",
        )
        .order_by(GeneratedResume.version.desc())
        .limit(1)
    )
    if resume_version_id is not None:
        resume_query = resume_query.where(GeneratedResume.id == resume_version_id)
    resume = db.scalar(resume_query)
    if resume_version_id is not None and resume is None:
        raise HTTPException(status_code=404, detail="Compiled resume not found for this user and job.")
    portfolio = (
        get_or_create_role_specific_portfolio(db, user_id, job, resume, profile)
        if resume
        else None
    )
    result = application_readiness(job, profile, resume, candidate, portfolio)
    result["resume"] = resume_read(resume).model_dump(mode="json") if resume else None
    result["portfolio"] = portfolio_read(portfolio) if portfolio else None
    db.commit()
    return ApplicationReadinessRead.model_validate(result)


@app.get("/api/application-sessions", response_model=list[ApplicationSessionRead])
def list_application_sessions(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[ApplicationSession]:
    return list(
        db.scalars(
            select(ApplicationSession)
            .where(ApplicationSession.owner_user_id == user_id)
            .order_by(ApplicationSession.updated_at.desc())
        )
    )


@app.get("/api/application-sessions/{session_id}", response_model=ApplicationSessionRead)
def get_application_session(
    session_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationSession:
    session = db.get(ApplicationSession, session_id)
    if not session or session.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Application session not found.")
    return session


@app.post(
    "/api/jobs/{job_id}/application-sessions",
    response_model=ApplicationSessionLaunch,
    status_code=status.HTTP_201_CREATED,
)
def create_application_session(
    job_id: int,
    payload: ApplicationSessionCreate,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationSessionLaunch:
    return _create_application_session(job_id, payload, user_id, db)


def _create_application_session(job_id, payload, user_id, db, talent_context=None):
    expire_past_deadline_jobs(db)
    job = talent_context or db.scalar(
        _job_with_candidate_override(select(Job).where(Job.id == job_id), user_id)
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail=f"Cannot start an application for a {job.status} job.")
    application_url = direct_application_url(
        (job.official_apply_url or job.apply_url or "").strip(),
        job.company,
        job.ats_requisition_id,
    )
    try:
        validate_public_url(application_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="This job does not have a safe public application URL.") from exc
    portal = detect_portal(application_url, job.company)
    if portal["support_status"] == "UNSUPPORTED":
        raise HTTPException(
            status_code=422,
            detail=f"{portal['portal_type'].replace('_', ' ').title()} is not supported by Apply Assistant yet.",
        )
    resume_query = select(GeneratedResume).where(
        GeneratedResume.user_id == user_id,
        GeneratedResume.job_id == job_id,
        GeneratedResume.status == "compiled",
    )
    if talent_context:
        resume_query = resume_query.where(
            GeneratedResume.application_type == "TALENT_COMMUNITY",
            GeneratedResume.company_id == talent_context.company_id,
        )
    if payload.resume_version_id:
        resume_query = resume_query.where(GeneratedResume.id == payload.resume_version_id)
    else:
        resume_query = resume_query.order_by(GeneratedResume.version.desc()).limit(1)
    resume = db.scalar(resume_query)
    if not resume:
        raise HTTPException(status_code=422, detail="Generate or select a compiled Recommended Resume first.")
    profile = get_or_create_application_profile(db, user_id)
    candidate = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    portfolio: GeneratedPortfolio | None = None
    if payload.portfolio_version_id:
        portfolio = db.scalar(
            select(GeneratedPortfolio).where(
                GeneratedPortfolio.id == payload.portfolio_version_id,
                GeneratedPortfolio.user_id == user_id,
                GeneratedPortfolio.job_id == job.id,
                GeneratedPortfolio.status == "ready",
            )
        )
        if not portfolio:
            raise HTTPException(status_code=422, detail="The selected Project Portfolio is unavailable for this job.")
    elif not talent_context:
        portfolio = get_or_create_role_specific_portfolio(db, user_id, job, resume, profile)
    readiness = application_readiness(job, profile, resume, candidate, portfolio)
    forced_action = user_id == settings.effective_primary_user_id and force_apply_action_is_active(job)
    if readiness["hard_blocked"] and not (payload.allow_ineligible_override or forced_action):
        raise HTTPException(
            status_code=409,
            detail=f"Apply Assistant unavailable: {readiness['blocker_reason']}",
        )
    missing_required = [
        item["label"]
        for item in readiness["checks"]
        if not item["ready"]
        and item["key"]
        in {
            "contact",
            "education",
            "location",
            "availability",
            "authorization",
            "skills",
            "projects",
            "resume",
            "portal",
        }
    ]
    if missing_required:
        raise HTTPException(
            status_code=422,
            detail=f"Application profile is not ready: {', '.join(missing_required)}.",
        )
    nonce = secrets.token_urlsafe(24)
    snapshot = profile_snapshot(profile, candidate)
    selection = build_application_selection(
        job,
        profile,
        resume,
        selected_project_names=payload.selected_project_names,
        selected_skills=payload.selected_skills,
    )
    selected_projects = selection["selected_projects"]
    if not selected_projects:
        raise HTTPException(
            status_code=422,
            detail="Select at least one verified project from the Recommended Resume.",
        )
    if not selection["selected_skills"]:
        raise HTTPException(
            status_code=422,
            detail="Select at least one verified skill from the Recommended Resume.",
        )
    job_snapshot = {
        "id": job.id,
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "country": job.country,
        "physical_work_country_required": job.physical_work_country_required,
        "description": job.description,
        "requirements": job.requirements,
        "application_url": application_url,
        "eligibility": job.analysis.eligibility_status if job.analysis else "UNKNOWN",
        "eligibility_reason": job.analysis.explanation if job.analysis else "",
        "force_apply_now": forced_action,
        "resume_version": resume.version,
        "resume_version_id": resume.id,
    }
    from app.services.talent_communities import company_resume_filename
    record = ApplicationSession(
        owner_user_id=user_id,
        job_id=job.id,
        application_type="TALENT_COMMUNITY" if talent_context else "STANDARD_JOB",
        company_id=resume.company_id if talent_context else None,
        company_profile=resume.company_profile if talent_context else {},
        talent_community_url=application_url if talent_context else "",
        target_role_categories=resume.target_role_categories if talent_context else [],
        company=job.company,
        portal_type=portal["portal_type"],
        application_url=application_url,
        resume_version_id=resume.id,
        resume_filename=(
            company_resume_filename(profile.full_name, job.company, resume.target_role_categories, resume.version)
            if talent_context else f"{sanitize_filename(f'{profile.full_name}_{job.company}_{resume.target_role}_Resume_v{resume.version}')}.pdf"
        ),
        resume_download_url="/api/extension/application-session/resume.pdf",
        portfolio_version_id=portfolio.id if portfolio else None,
        portfolio_filename=portfolio.filename if portfolio else "",
        portfolio_download_url=(
            "/api/extension/application-session/portfolio.pdf" if portfolio else ""
        ),
        status="CREATED",
        current_step="Application Readiness",
        portal_job_id=portal["portal_job_id"] or job.ats_requisition_id,
        profile_snapshot_json=snapshot,
        job_snapshot_json=job_snapshot,
        project_experience_json=selected_projects,
        selected_projects_json=selected_projects,
        generated_experience_text=selection["generated_experience_text"],
        selected_skills_json=selection["selected_skills"],
        skill_match_reasons_json=selection["skill_match_reasons"],
        project_match_reasons_json=selection["project_match_reasons"],
        selection_warnings_json=selection["selection_warnings"],
        portal_detection_evidence_json=portal["detection_evidence"],
        adapter_version="2.3.0",
        company_policy_key=portal["company_policy_key"],
        token_nonce=nonce,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    token, expires_at = create_application_session_token(
        session_id=record.id,
        owner_user_id=user_id,
        nonce=nonce,
    )
    return ApplicationSessionLaunch(
        session=application_session_read(record),
        application_session_token=token,
        token_expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
        extension_message_origin=settings.frontend_url.rstrip("/"),
    )


@app.post(
    "/api/application-sessions/{session_id}/rotate-token",
    response_model=ApplicationSessionLaunch,
)
def rotate_application_session_token(
    session_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationSessionLaunch:
    session = db.get(ApplicationSession, session_id)
    if not session or session.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Application session not found.")
    if session.status in {"SUBMITTED_BY_USER", "ABANDONED", "ERROR"}:
        raise HTTPException(status_code=409, detail="This application session is closed.")
    session.token_nonce = secrets.token_urlsafe(24)
    db.commit()
    db.refresh(session)
    token, expires_at = create_application_session_token(
        session_id=session.id,
        owner_user_id=user_id,
        nonce=session.token_nonce,
    )
    return ApplicationSessionLaunch(
        session=application_session_read(session),
        application_session_token=token,
        token_expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
        extension_message_origin=settings.frontend_url.rstrip("/"),
    )


@app.post(
    "/api/application-sessions/{session_id}/revoke",
    response_model=ApplicationSessionRevokeResult,
)
def revoke_application_session(
    session_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationSessionRevokeResult:
    session = db.get(ApplicationSession, session_id)
    if not session or session.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Application session not found.")
    session.token_nonce = ""
    db.commit()
    return ApplicationSessionRevokeResult(
        session_id=session.id,
        status=session.status,
        token_revoked=True,
    )


@app.post(
    "/api/application-sessions/{session_id}/abandon",
    response_model=ApplicationSessionRevokeResult,
)
def abandon_application_session(
    session_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ApplicationSessionRevokeResult:
    session = db.get(ApplicationSession, session_id)
    if not session or session.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Application session not found.")
    if session.status != "SUBMITTED_BY_USER":
        session.status = "ABANDONED"
        session.current_step = "Abandoned"
        session.token_nonce = ""
        db.commit()
    return ApplicationSessionRevokeResult(
        session_id=session.id,
        status=session.status,
        token_revoked=not bool(session.token_nonce),
    )


@app.get(
    "/api/extension/application-session",
    response_model=ExtensionApplicationPayload,
)
def get_extension_application_session(
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> ExtensionApplicationPayload:
    require_extension_scope(request, "read_application_profile")
    require_extension_scope(request, "read_resume_version")
    resume = db.get(GeneratedResume, session.resume_version_id)
    if not resume or resume.user_id != session.owner_user_id or resume.status != "compiled":
        raise HTTPException(status_code=409, detail="The resume bound to this session is unavailable.")
    suggestions = list(
        db.scalars(
            select(ApplicationAnswerRegistry)
            .where(ApplicationAnswerRegistry.owner_user_id == session.owner_user_id)
            .order_by(
                ApplicationAnswerRegistry.updated_at.desc()
            )
        )
    )
    session.last_extension_seen_at = datetime.now(timezone.utc)
    if session.status == "CREATED":
        session.status = "OPENED"
        session.started_at = session.last_extension_seen_at
        session.current_step = f"Connected to {session.portal_type.replace('_', ' ').title()}"
    db.commit()
    db.refresh(session)
    resume_payload = resume_read(resume).model_dump(mode="json")
    resume_payload["pdf_url"] = f"/api/extension/application-session/resume.pdf"
    resume_payload["filename"] = session.resume_filename
    resume_payload["latex_source"] = ""
    resume_payload["selected_skills"] = list(
        session.selected_skills_json or resume.selected_skills or []
    )
    portfolio = (
        db.get(GeneratedPortfolio, session.portfolio_version_id)
        if session.portfolio_version_id
        else None
    )
    if portfolio and portfolio.user_id != session.owner_user_id:
        portfolio = None
    ai_settings = get_or_create_ai_settings(db, session.owner_user_id)
    db.commit()
    db.refresh(ai_settings)
    return ExtensionApplicationPayload(
        session=application_session_read(session),
        profile=session.profile_snapshot_json,
        resume=resume_payload,
        portfolio=portfolio_read(portfolio) if portfolio else None,
        answer_suggestions=[ApplicationAnswerRead.model_validate(item) for item in suggestions],
        field_policies=FIELD_POLICIES,
        sensitive_question_keys=sorted(SENSITIVE_QUESTION_KEYS),
        company_policy=company_policy(session.company),
        adapter_status=PORTAL_SUPPORT.get(session.portal_type, "UNSUPPORTED"),
        ai_settings=AISettingsRead.model_validate(ai_settings),
        final_submit_policy="MANUAL_ONLY",
    )


@app.post(
    "/api/extension/application-session/agent/analyze",
    response_model=ApplicationAgentResponse,
)
def analyze_extension_application_page(
    payload: ApplicationAgentRequest,
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> ApplicationAgentResponse:
    require_extension_scope(request, "read_application_profile")
    require_extension_scope(request, "write_application_progress")
    session.last_page_url = payload.page_url
    session.last_extension_seen_at = datetime.now(timezone.utc)
    session.current_step = "AI field analysis"
    try:
        return ApplicationAgent().analyze(db, session, payload.fields)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/extension/application-session/agent/approve-mapping",
    response_model=UserApprovedMappingRead,
)
def approve_extension_agent_mapping(
    payload: UserApprovedMappingPayload,
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> UserApprovedMapping:
    require_extension_scope(request, "write_application_progress")
    record = db.scalar(select(UserApprovedMapping).where(
        UserApprovedMapping.owner_user_id == session.owner_user_id,
        UserApprovedMapping.portal == session.portal_type,
        UserApprovedMapping.canonical_field == payload.canonical_field,
        UserApprovedMapping.canonical_value == payload.canonical_value,
        UserApprovedMapping.portal_option == payload.portal_option,
    ))
    if record is None:
        record = UserApprovedMapping(
            owner_user_id=session.owner_user_id,
            portal=session.portal_type,
            canonical_field=payload.canonical_field,
            canonical_value=payload.canonical_value,
            portal_option=payload.portal_option,
            match_type=payload.match_type,
        )
        db.add(record)
    else:
        record.match_type = payload.match_type
        record.approved_by_user = True
        record.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


@app.patch(
    "/api/extension/application-session/progress",
    response_model=ApplicationSessionRead,
)
def update_extension_application_progress(
    payload: ApplicationSessionProgress,
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> ApplicationSession:
    require_extension_scope(request, "write_application_progress")
    changes = payload.model_dump(exclude_unset=True)
    requested_status = changes.pop("status", None)
    observed = changes.pop("observed_fields", None)
    if requested_status == "SUBMITTED_BY_USER":
        raise HTTPException(
            status_code=409,
            detail="Submission must be confirmed through the dedicated manual-submission endpoint.",
        )
    if requested_status:
        session.status = requested_status
    for key, value in changes.items():
        setattr(session, key, value)
    session.last_extension_seen_at = datetime.now(timezone.utc)
    if session.started_at is None:
        session.started_at = session.last_extension_seen_at
    if observed is not None:
        observed = dict(observed)
        observed["confirmed_application_answers"] = session.application_answers_json or {}
        session.consistency_issues_json = validate_application_consistency(
            session.profile_snapshot_json,
            observed,
            expected_resume_version_id=session.resume_version_id,
        )
    db.commit()
    db.refresh(session)
    return session


@app.post(
    "/api/extension/application-session/confirm-answer",
    response_model=ApplicationAnswerRead,
)
def confirm_extension_application_answer(
    payload: ApplicationAnswerConfirmation,
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> ApplicationAnswerRegistry:
    require_extension_scope(request, "write_application_progress")
    if payload.answer is None or (isinstance(payload.answer, str) and not payload.answer.strip()):
        raise HTTPException(status_code=422, detail="Confirm a non-empty answer.")
    classification = classify_question(payload.normalized_question)
    if (
        classification["policy"] not in {"CONFIRM_REQUIRED", "AUTO_FILL_REVIEW_REQUIRED"}
        or classification["confidence"] < 0.72
        or classification["question_key"] != payload.question_key
        or payload.question_key not in (SENSITIVE_QUESTION_KEYS | AUTO_FILL_REVIEW_QUESTION_KEYS)
    ):
        raise HTTPException(
            status_code=422,
            detail="This question could not be matched safely and must be completed manually.",
        )
    now = datetime.now(timezone.utc)
    record = db.scalar(
        select(ApplicationAnswerRegistry).where(
            ApplicationAnswerRegistry.owner_user_id == session.owner_user_id,
            ApplicationAnswerRegistry.question_key == payload.question_key,
        )
    )
    if not record:
        record = ApplicationAnswerRegistry(
            owner_user_id=session.owner_user_id,
            question_key=payload.question_key,
        )
        db.add(record)
    record.normalized_question = payload.normalized_question
    record.answer_json = {"value": payload.answer}
    record.answer_type = payload.answer_type
    record.sensitivity = classification["policy"]
    record.last_confirmed_at = now
    record.source = "application_confirmation"
    answers = dict(session.application_answers_json or {})
    answers[payload.question_key] = {
        "answer": payload.answer,
        "question": payload.normalized_question,
        "confirmed_at": now.isoformat(),
        "classification_confidence": classification["confidence"],
    }
    session.application_answers_json = answers
    session.fields_confirmed_count = len(answers)
    session.last_extension_seen_at = now
    db.commit()
    db.refresh(record)
    return record


@app.post(
    "/api/extension/application-session/confirm-submitted",
    response_model=ApplicationSessionRead,
)
def confirm_extension_application_submitted(
    payload: ApplicationSubmittedConfirmation,
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> ApplicationSession:
    require_extension_scope(request, "write_application_progress")
    normalized = " ".join(payload.confirmation_text.casefold().split())
    confirmation_phrases = (
        "application submitted",
        "thank you for applying",
        "application has been received",
        "application was submitted",
        "application received",
        "thanks for applying",
        "thank you for your application",
    )
    if not any(phrase in normalized for phrase in confirmation_phrases):
        raise HTTPException(
            status_code=422,
            detail="A recognizable portal submission confirmation is required.",
        )
    now = datetime.now(timezone.utc)
    job = db.get(Job, session.job_id) if session.job_id else None
    if not job and session.application_type != "TALENT_COMMUNITY":
        raise HTTPException(status_code=404, detail="Job not found.")
    application = db.scalar(
        select(Application)
        .where(
            Application.owner_user_id == session.owner_user_id,
            (Application.application_session_id == session.id if not job else Application.job_id == job.id),
        )
        .order_by(Application.updated_at.desc())
        .limit(1)
    )
    if not application:
        application = Application(
            owner_user_id=session.owner_user_id,
            job_id=job.id if job else None,
            application_type=session.application_type,
            company=session.company,
            company_id=session.company_id,
            company_profile=session.company_profile,
            talent_community_url=session.talent_community_url,
            target_role_categories=session.target_role_categories,
            status="Applied",
            applied_at=now,
            submitted_resume_id=session.resume_version_id,
            application_session_id=session.id,
            resume_type=(job.analysis.recommended_resume_type if job and job.analysis else "Company Resume"),
        )
        _record_application_status(application, None, "Applied", previous_job_status=job.status if job else None)
        db.add(application)
    else:
        if application.status != "Applied":
            _record_application_status(application, application.status, "Applied", previous_job_status=job.status if job else None)
        application.status = "Applied"
        application.applied_at = application.applied_at or now
        application.submitted_resume_id = session.resume_version_id
        application.application_session_id = session.id
    if job:
        job.status = "applied"
        job.applied_at = job.applied_at or now
        job.submitted_resume_id = session.resume_version_id
    session.status = "SUBMITTED_BY_USER"
    session.completed_at = session.completed_at or now
    session.current_step = "Application submitted by user"
    session.last_page_url = payload.confirmation_url or session.last_page_url
    session.last_extension_seen_at = now
    session.token_nonce = ""
    db.commit()
    db.refresh(session)
    return session


@app.get("/api/extension/application-session/resume.pdf")
def extension_application_resume_pdf(
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> Response:
    require_extension_scope(request, "read_resume_version")
    resume = db.get(GeneratedResume, session.resume_version_id)
    if not resume or resume.user_id != session.owner_user_id or resume.status != "compiled":
        raise HTTPException(status_code=404, detail="Session resume not found.")
    try:
        pdf = compile_latex(resume.latex_source)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = session.resume_filename or (
        f"{sanitize_filename(f'{CANONICAL_NAME}_{session.company}_{resume.target_role}_Resume_v{resume.version}')}.pdf"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/extension/application-session/portfolio.pdf")
def extension_application_portfolio_pdf(
    request: Request,
    session: ApplicationSession = Depends(require_extension_session),
    db: Session = Depends(get_db),
) -> Response:
    require_extension_scope(request, "read_resume_version")
    if not session.portfolio_version_id:
        raise HTTPException(status_code=404, detail="This application has no prepared Project Portfolio.")
    portfolio = db.get(GeneratedPortfolio, session.portfolio_version_id)
    if not portfolio or portfolio.user_id != session.owner_user_id or portfolio.status != "ready":
        raise HTTPException(status_code=404, detail="Session Project Portfolio not found.")
    try:
        pdf = compile_latex(portfolio.latex_source)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = session.portfolio_filename or portfolio.filename
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs", response_model=JobPage)
def list_jobs(
    search_run_id: int | None = Query(default=None, ge=1),
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
    rating_order: Literal["highest", "lowest"] | None = Query(default=None),
    q: str | None = None,
    search_fields: Literal["full", "listing"] = Query(default="full"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> JobPage:
    # Idempotently reconcile explicit Santiago action overrides with records
    # that may have been discovered after the original migration/deployment.
    if user_id == settings.effective_primary_user_id:
        apply_requested_santiago_overrides(db, user_id)
    expire_past_deadline_jobs(db)
    hidden_statuses = ["ignored"]
    if not settings.demo_feed_enabled:
        hidden_statuses.append("demo")
    requested_statuses = job_status or list(ACTIVE_JOB_STATUSES)
    # The Jobs page's "active" lifecycle tab sends only `active`, while a
    # candidate may have explicitly saved a job and still force it into the
    # Apply Now queue. Include saved opportunities for that recommendation
    # filter without changing their underlying lifecycle/application state.
    if recommendation and "Apply Now" in recommendation and "active" in requested_statuses:
        requested_statuses = list(dict.fromkeys([*requested_statuses, "saved"]))
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
    pinned_priority = Job.raw_data["_radar_user_priority"]["owner_user_id"].as_string() == user_id
    force_apply_active = _force_apply_active_clause(user_id)
    search_rank = None
    if search_run_id is not None:
        search_run = db.get(SearchRun, search_run_id)
        if not search_run or search_run.owner_user_id != user_id:
            raise HTTPException(status_code=404, detail="Search run not found.")
        membership = select(SearchRunJob.job_id).where(
            SearchRunJob.search_run_id == search_run_id,
            SearchRunJob.owner_user_id == user_id,
        )
        filters.append(Job.id.in_(membership))
        search_rank = (
            select(SearchRunJob.rank)
            .where(
                SearchRunJob.search_run_id == search_run_id,
                SearchRunJob.job_id == Job.id,
                SearchRunJob.owner_user_id == user_id,
            )
            .scalar_subquery()
        )
    if recommendation:
        normal_recommendations = [item for item in recommendation if item != "Apply Now"]
        recommendation_filters = []
        if normal_recommendations:
            recommendation_filters.append(JobAnalysis.recommendation.in_(normal_recommendations))
        if "Apply Now" in recommendation:
            recommendation_filters.append(
                or_(JobAnalysis.recommendation == "Apply Now", force_apply_active)
            )
        filters.append(or_(*recommendation_filters))
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
                pinned_priority,
                force_apply_active,
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
        listing_fields = (Job.title.ilike(term), Job.company.ilike(term), Job.location.ilike(term))
        filters.append(
            or_(*listing_fields)
            if search_fields == "listing"
            else or_(*listing_fields, Job.description.ilike(term), Job.requirements.ilike(term))
        )

    count_stmt = select(func.count(Job.id)).outerjoin(JobAnalysis).where(*filters)
    total = db.scalar(count_stmt) or 0
    displayed_rating = func.coalesce(
        JobAnalysis.effective_score,
        JobAnalysis.overall_score,
        0,
    )
    default_ordering = [
        *([search_rank.asc()] if search_rank is not None else []),
        case((pinned_priority, 1), else_=0).desc(),
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
    ]
    rating_ordering = [
        (
            displayed_rating.asc().nullslast()
            if rating_order == "lowest"
            else displayed_rating.desc().nullslast()
        ),
        Job.id.asc(),
    ]
    query = (
        _job_with_candidate_override(select(Job), user_id)
        .options(selectinload(Job.applications))
        .outerjoin(JobAnalysis)
        .where(*filters)
        .order_by(
            *(rating_ordering if rating_order else default_ordering),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(query).unique())
    return JobPage(items=items, total=total, page=page, page_size=page_size)


@app.post("/api/search-runs", response_model=SearchRunRead, status_code=202)
async def create_criteria_search_run(
    payload: SearchCriteria,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    run = create_search_run(
        db,
        search_type="custom",
        trigger="manual",
        criteria=payload.model_dump(mode="json"),
        owner_user_id=user_id,
    )
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
    background_tasks.add_task(_execute_search_run_in_worker, run.id)
    return run


@app.get("/api/search-runs", response_model=list[SearchRunRead])
def list_search_runs(
    limit: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> list[SearchRun]:
    if fail_abandoned_search_runs(db, owner_user_id=user_id):
        db.commit()
    return list(
        db.scalars(
            select(SearchRun)
            .where(
                SearchRun.owner_user_id == user_id,
                SearchRun.search_type == "custom",
                SearchRun.history_deleted_at.is_(None),
            )
            .order_by(SearchRun.created_at.desc())
            .limit(limit)
        )
    )


@app.delete(
    "/api/search-runs/{run_id}",
    response_model=SearchRunDeleteResult,
)
def delete_search_run_history(
    run_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRunDeleteResult:
    run = db.get(SearchRun, run_id)
    if not run or run.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Search run not found.")
    if run.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="A running search cannot be removed.")
    run.history_deleted_at = datetime.now(timezone.utc)
    db.commit()
    return SearchRunDeleteResult(id=run.id, deleted_from_history=True)


@app.post("/api/jobs/search", response_model=SearchRunRead, status_code=202)
async def search_jobs(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    run = create_search_run(db, search_type="general", trigger="manual", owner_user_id=user_id)
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
    background_tasks.add_task(_execute_search_run_in_worker, run.id)
    return run


@app.get("/api/search-runs/latest", response_model=SearchRunRead)
def latest_search_run(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    if fail_abandoned_search_runs(db, owner_user_id=user_id):
        db.commit()
    run = db.scalar(
        select(SearchRun)
        .where(SearchRun.owner_user_id == user_id)
        .order_by(SearchRun.started_at.desc())
        .limit(1)
    )
    if not run:
        raise HTTPException(status_code=404, detail="No search has run yet.")
    return run


@app.get("/api/search-runs/{run_id}", response_model=SearchRunRead)
def get_search_run(
    run_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> SearchRun:
    if fail_abandoned_search_runs(db, owner_user_id=user_id):
        db.commit()
    run = db.get(SearchRun, run_id)
    if not run or run.owner_user_id != user_id:
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


@app.post("/api/jobs/import-url", response_model=JobURLImportResponse)
async def import_job_by_url(
    payload: JobURLImportRequest,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> JobURLImportResponse:
    """Import a posting for the authenticated candidate, never a supplied user ID."""
    if payload.force_apply_now:
        _require_santiago_force_apply_access(user_id)
    try:
        normalized = await extract_job_url(payload.url)
        result = persist_imported_job_for_all_profiles(
            db, normalized, payload.url, user_id, payload.force_apply_now
        )
    except UnsafeJobURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (JobFetchError, JobExtractionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JobURLImportResponse(
        job_id=result.job.id, created=result.created,
        existing_job_reused=not result.created, verified=result.verified,
        official_status=result.job.official_status,
        candidate_analysis_created=result.job.analysis is not None,
        force_apply_now=result.force_apply_now,
        force_apply_error=result.force_apply_error,
    )


@app.get("/api/jobs/{job_id}", response_model=JobRead)
def get_job(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    expire_past_deadline_jobs(db)
    job = db.scalar(_job_with_candidate_override(select(Job).where(Job.id == job_id), user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.analysis:
        from app.services.scoring import _skill_matches
        verified_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == job.owner_user_id))
        if verified_profile:
            matched, missing_required, _, _ = _skill_matches(job, verified_profile)
            job.analysis.matched_skills = matched
            job.analysis.missing_required_skills = missing_required
            db.commit()
    return job


@app.post("/api/santiago/opportunities/import")
async def import_santiago_official_opportunities(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> dict:
    """Import only the exact, open postings in Santiago's official audit list."""
    if user_id != settings.effective_primary_user_id:
        raise HTTPException(status_code=403, detail="This opportunity import is available only to Santiago.")

    collected = await collect_official_audit_jobs()
    jobs = upsert_verified_audit_jobs(db, user_id, collected.jobs)
    return {
        "status": "completed",
        "imported_count": len(jobs),
        "jobs": [
            {
                "id": job.id,
                "company": job.company,
                "title": job.title,
                "external_id": job.external_id,
                "official_url": job.official_apply_url or job.canonical_official_url or job.apply_url,
                "recommendation": job.analysis.recommendation if job.analysis else "NEEDS_REVIEW",
            }
            for job in jobs
        ],
        "source_failures": [failure.split(":", 1)[0] for failure in collected.source_failures],
    }


@app.post("/api/research-opportunities", response_model=JobRead, status_code=201)
def create_research_opportunity(
    payload: ResearchOpportunityCreate,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    areas = [sanitize_resume_text(item) for item in payload.research_areas if sanitize_resume_text(item)]
    description = sanitize_resume_text(payload.description)
    research_url = payload.url.strip()
    if research_url:
        try:
            validate_public_url(research_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    context = "Research areas: " + ", ".join(areas) if areas else "Academic robotics research opportunity."
    job = Job(
        owner_user_id=user_id,
        source_name="manual_research",
        source_url=research_url,
        opportunity_type="research",
        company=sanitize_resume_text(payload.organization),
        title=sanitize_resume_text(payload.title),
        lab=sanitize_resume_text(payload.lab),
        supervisor=sanitize_resume_text(payload.professor),
        research_areas=areas,
        research_url=research_url,
        research_notes=sanitize_resume_text(payload.notes),
        area="Robotics",
        employment_type="Research Internship",
        description=description or context,
        requirements=context,
        apply_url=research_url,
        status="saved",
        is_active=True,
        verification_status="manual",
        discovery_status="manual",
        official_status="unknown",
        raw_data_hash=f"manual-research-{secrets.token_hex(16)}",
        raw_data={"manual": True},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.post("/api/jobs/manual", response_model=JobRead, status_code=201)
def create_manual_job(
    payload: ManualJobCreate,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    """Create or enrich a job for the authenticated candidate from supplied details."""
    if payload.force_apply_now:
        _require_santiago_force_apply_access(user_id)
    apply_url = payload.apply_url.strip()
    source_url = payload.source_url.strip() or apply_url
    for candidate_url in (apply_url, source_url):
        try:
            validate_public_url(candidate_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    company = sanitize_resume_text(payload.company)
    title = sanitize_resume_text(payload.title)
    company_key, title_key = company.casefold(), title.casefold()
    job = db.scalar(select(Job).where(
        Job.owner_user_id == user_id,
        Job.opportunity_type == "job",
        or_(
            Job.apply_url == apply_url,
            and_(Job.company_normalized == company_key, Job.title_normalized == title_key),
        ),
    ))
    created = job is None
    if created:
        job = Job(
            owner_user_id=user_id,
            source_name="manual_job",
            source_url=source_url,
            original_source_url=source_url,
            opportunity_type="job",
            company=company,
            title=title,
            company_normalized=company_key,
            title_normalized=title_key,
            location=sanitize_resume_text(payload.location),
            area=sanitize_resume_text(payload.category) or "Unknown",
            description=sanitize_resume_text(payload.description),
            requirements=sanitize_resume_text(payload.requirements),
            preferred_qualifications=sanitize_resume_text(payload.preferred_qualifications),
            apply_url=apply_url,
            application_url=apply_url,
            posting_url=source_url,
            verification_status="manual",
            verification_method="candidate_supplied",
            discovery_status="manual",
            official_status="unknown",
            application_url_source="candidate_supplied",
            application_url_status="unknown",
            status="saved",
            is_active=True,
            raw_data_hash=secrets.token_hex(32),
            raw_data={"manual": True},
        )
        db.add(job)
        db.flush()
    else:
        # Preserve verified lifecycle data, filling only missing descriptive fields.
        job.description = job.description or sanitize_resume_text(payload.description)
        job.requirements = job.requirements or sanitize_resume_text(payload.requirements)
        job.preferred_qualifications = job.preferred_qualifications or sanitize_resume_text(payload.preferred_qualifications)
        job.location = job.location or sanitize_resume_text(payload.location)
        job.area = job.area if job.area and job.area != "Unknown" else (sanitize_resume_text(payload.category) or "Unknown")
        if not job.source_url:
            job.source_url = source_url

    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    if profile:
        persist_analysis(db, job, profile)
    if payload.force_apply_now:
        if not can_force_apply_now(job):
            raise HTTPException(status_code=409, detail="This job has no usable application URL and cannot be force-applied.")
        override = job.candidate_job_override
        if override is None:
            override = CandidateJobOverride(owner_user_id=user_id, job_id=job.id)
            db.add(override)
            job.candidate_job_override = override
        set_force_apply_now(override, True)
    db.commit()
    db.refresh(job)
    return job


@app.post("/api/research-opportunities/{opportunity_id}/analyze", response_model=ResearchOpportunityAnalysisRead)
def analyze_manual_research_opportunity(
    opportunity_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> ResearchOpportunityAnalysisRead:
    opportunity = db.scalar(select(Job).where(
        Job.id == opportunity_id,
        Job.owner_user_id == user_id,
        Job.opportunity_type == "research",
    ))
    if not opportunity:
        raise HTTPException(status_code=404, detail="Research opportunity not found.")
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if not profile or not profile.education_json:
        raise HTTPException(status_code=422, detail="Complete Resume Profile before analysis.")
    recent = db.scalars(
        select(GeneratedResume).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.resume_target == "robotics_research",
            GeneratedResume.status == "compiled",
        ).order_by(GeneratedResume.created_at.desc()).limit(10)
    ).all()
    return ResearchOpportunityAnalysisRead.model_validate(
        analyze_research_opportunity(profile, opportunity, recent)
    )


@app.post("/api/jobs/{job_id}/resume/generate", response_model=GeneratedResumeRead)
def generate_job_resume(
    job_id: int,
    payload: ResumeGenerateRequest = ResumeGenerateRequest(),
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> GeneratedResumeRead:
    if payload.resume_target == "kospie_germany":
        raise HTTPException(
            status_code=409,
            detail="Use the KOSPIE program workspace to select three universities and generate this CV.",
        )
    job = db.scalar(select(Job).where(
        Job.id == job_id,
        Job.owner_user_id == user_id,
    ))
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
    education = profile.education_json[0] if isinstance(profile.education_json[0], dict) else {}
    if not sanitize_resume_text(education.get("degree", "")) or not sanitize_resume_text(profile.headline):
        raise HTTPException(
            status_code=422,
            detail="Confirm the official degree/program name before generating a resume.",
        )
    if job.analysis:
        from app.services.scoring import _skill_matches
        matched, missing_required, _, _ = _skill_matches(job, profile)
        job.analysis.matched_skills = matched
        job.analysis.missing_required_skills = missing_required
    input_hash = resume_generation_input_hash(job, profile, payload.resume_target)
    in_flight = db.scalar(
        select(GeneratedResume).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
            GeneratedResume.resume_target == payload.resume_target,
            GeneratedResume.status.in_(["queued", "generating"]),
        ).order_by(GeneratedResume.created_at.desc())
    )
    if in_flight:
        return resume_read(in_flight)
    latest = db.scalar(
        select(GeneratedResume).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
            GeneratedResume.resume_target == payload.resume_target,
            GeneratedResume.status == "compiled",
        ).order_by(GeneratedResume.version.desc()).limit(1)
    )
    # A normal Generate action is idempotent. Reopening a job or retrying a
    # completed request returns the saved artifact; only explicit regeneration
    # creates another immutable version.
    if latest is not None and not payload.regenerate:
        result = resume_read(latest)
        result.is_stale = bool(latest.source_input_hash and latest.source_input_hash != input_hash)
        return result
    retryable = db.scalar(
        select(GeneratedResume).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
            GeneratedResume.resume_target == payload.resume_target,
            GeneratedResume.status == "failed_retryable",
        ).order_by(GeneratedResume.version.desc()).limit(1)
    )
    if retryable is not None and not payload.regenerate:
        # A transient provider/compiler failure retries the same immutable
        # version; it never silently creates a duplicate resume.
        retryable.status = "queued"
        retryable.generation_error = None
        db.commit()
        resume_generation_queue.enqueue(user_id, lambda: _run_job_resume_generation(retryable.id))
        db.refresh(retryable)
        return resume_read(retryable)
    latest_version = db.scalar(
        select(func.max(GeneratedResume.version)).where(
            GeneratedResume.user_id == user_id,
            GeneratedResume.job_id == job_id,
        )
    ) or 0
    job.resume_target = payload.resume_target
    record = GeneratedResume(
        user_id=user_id,
        job_id=job_id,
        version=latest_version + 1,
        status="queued",
        target_role=job.title,
        resume_target=payload.resume_target,
        content_hash="pending",
        source_input_hash=input_hash,
        generation_model=(
            settings.openai_resume_model
            if settings.resume_generation_provider.strip().lower() == "openai"
            else "local"
        ),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    resume_generation_queue.enqueue(user_id, lambda: _run_job_resume_generation(record.id))
    # Development/tests execute the queue immediately; production returns a
    # QUEUED/GENERATING record that the UI polls without issuing duplicate work.
    db.refresh(record)
    return resume_read(record)


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
    result = resume_read(resume)
    job = db.scalar(select(Job).where(Job.id == job_id, Job.owner_user_id == user_id))
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    if job and profile and resume.source_input_hash:
        result.is_stale = resume.source_input_hash != resume_generation_input_hash(
            job, profile, resume.resume_target
        )
    return result


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
    job = db.get(Job, resume.job_id) if resume.job_id else None
    pdf = resume.compiled_pdf
    if pdf is None:
        # Backfill immutable artifacts from versions generated before PDF
        # persistence. Every subsequent preview/download is cache-only.
        try:
            pdf = (
                compile_latex(resume.latex_source, max_pages=2)
                if resume.resume_target == "kospie_germany"
                else compile_latex(resume.latex_source)
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        resume.compiled_pdf = pdf
        resume.compiled_pdf_at = datetime.now(timezone.utc)
        db.commit()
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    name = profile.full_name if profile and profile.full_name else CANONICAL_NAME
    filename = resume_filename(
        name,
        job.company if job else resume.company,
        resume.resume_target,
        resume.target_role,
        (job.supervisor or job.lab) if job and resume.resume_target == "robotics_research" else "",
    )
    if resume.application_type == "TALENT_COMMUNITY":
        from app.services.talent_communities import company_resume_filename
        filename = company_resume_filename(name, resume.company, resume.target_role_categories, resume.version)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
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
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == user_id))
    name = profile.full_name if profile and profile.full_name else "Resume"
    degree = ""
    if profile and profile.education_json and isinstance(profile.education_json[0], dict):
        degree = profile.education_json[0].get("degree", "")
    filename = (
        sanitize_filename(f"{name}_KOSPIE_DAAD_CV")
        if resume.resume_target == "kospie_germany"
        else sanitize_filename(f"{name}_{degree}_{resume.target_role}_Resume")
    )
    return Response(
        content=resume.latex_source,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}.tex"'},
    )


@app.post("/api/jobs/{job_id}/analyze", response_model=JobRead)
def analyze_one_job(job_id: int, user_id: str = Depends(require_private_api), db: Session = Depends(get_db)) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).options(joinedload(Job.analysis)))
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == user_id))
    if not job or not profile:
        raise HTTPException(status_code=404, detail="Job or profile not found")
    persist_analysis(db, job, profile)
    db.commit()
    db.refresh(job)
    return job


@app.post("/api/jobs/{job_id}/force-apply-now", response_model=JobRead)
def enable_force_apply_now(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    """Enable Santiago's explicit action override without changing analysis."""
    _require_santiago_force_apply_access(user_id)
    job = db.scalar(_job_with_candidate_override(select(Job).where(
        Job.id == job_id, Job.owner_user_id == user_id,
    ), user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not can_force_apply_now(job):
        detail = (
            "A confirmed closed or expired application cannot be force-applied."
            if is_application_confirmed_unavailable(job)
            else "This job has no usable application URL and cannot be force-applied."
        )
        raise HTTPException(status_code=409, detail=detail)
    if str(job.status or "").lower() not in ACTIVE_JOB_STATUSES or not job.is_active:
        job.status = "active"
        job.is_active = True
        job.archived_at = None
        job.expired_at = None
    override = job.candidate_job_override
    if override is None:
        override = CandidateJobOverride(owner_user_id=user_id, job_id=job.id)
        db.add(override)
        # The relationship was eagerly loaded above (and is therefore cached
        # as ``None``).  Attach the new record explicitly so this request and
        # its response cannot observe a stale action state.
        job.candidate_job_override = override
        db.flush()
    set_force_apply_now(override, True)
    db.commit()
    # Reload the relationship after commit.  A same-session SELECT can return
    # the identity-mapped Job whose eagerly-loaded relationship was previously
    # ``None``; expiring this attribute makes the response reflect the record
    # just written.
    db.expire(job, ["candidate_job_override"])
    return job


@app.delete("/api/jobs/{job_id}/force-apply-now", response_model=JobRead)
def disable_force_apply_now(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    """Remove Santiago's override and restore the normal displayed action."""
    _require_santiago_force_apply_access(user_id)
    job = db.scalar(_job_with_candidate_override(select(Job).where(
        Job.id == job_id, Job.owner_user_id == user_id,
    ), user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.candidate_job_override:
        set_force_apply_now(job.candidate_job_override, False)
        db.commit()
    db.expire(job, ["candidate_job_override"])
    return job


@app.post("/api/jobs/{job_id}/recheck", response_model=JobRead)
async def recheck_job(
    job_id: int,
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> Job:
    """Manually revalidate the stored official posting/application URL."""
    job = db.scalar(
        select(Job).where(Job.id == job_id, Job.owner_user_id == user_id)
        .options(joinedload(Job.analysis))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    summary = await revalidate_existing_jobs(
        db,
        owner_user_id=user_id,
        job_id=job_id,
        force=True,
    )
    if summary["checked"] != 1:
        raise HTTPException(status_code=409, detail="Only active or saved jobs can be rechecked.")
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
def create_application(payload: ApplicationCreate, user_id: str = Depends(require_private_api), db: Session = Depends(get_db)) -> Application:
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    previous_job_status = job.status
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
    application = Application(owner_user_id=user_id, **data)
    _record_application_status(application, None, application.status, previous_job_status=previous_job_status if application.status == "Applied" else None)
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
    if "applied_at" in changes and changes["applied_at"] is None and application.applied_at is not None:
        # The first submission timestamp is historical even after removal.
        changes.pop("applied_at")
    new_status = changes.get("status")
    if new_status is not None and new_status not in {"Draft", "Saved", "Applied", "Interview", "Rejected", "Offer", "Withdrawn", "Not interested"}:
        raise HTTPException(status_code=422, detail="Unsupported application status.")
    old_status = application.status
    previous_job_status = application.job.status if application.job else None
    if changes.get("status") == "Applied" and not application.applied_at and "applied_at" not in changes:
        changes["applied_at"] = datetime.now(timezone.utc)
    for key, value in changes.items():
        setattr(application, key, value)
    if new_status and new_status != old_status:
        _record_application_status(application, old_status, new_status, previous_job_status=previous_job_status)
    if changes.get("status") == "Applied" and application.job:
        application.job.status = "applied"
        application.job.applied_at = changes.get("applied_at") or application.applied_at
    elif changes.get("status") == "Saved" and application.job and application.job.status in {"active", "applied"}:
        application.job.status = "saved"
        application.job.applied_at = None
    elif changes.get("status") == "Draft" and application.job and application.job.status == "applied":
        application.job.status = "active"
        application.job.applied_at = None
    elif changes.get("status") in {"Interview", "Rejected", "Offer", "Withdrawn"} and application.job:
        # The application process progresses, but the job remains in the
        # candidate's Applied list rather than returning to discovery.
        application.job.status = "applied"
    elif changes.get("status") == "Not interested" and application.job:
        application.job.status = "not_interested"
    db.commit()
    db.refresh(application)
    if "next_action_at" in changes:
        _send_follow_up_safely(db, application)
    return application


def _record_application_status(
    application: Application,
    old_status: str | None,
    new_status: str,
    *,
    previous_job_status: str | None = None,
) -> None:
    history = list(application.status_history or [])
    history.append({
        "from": old_status,
        "to": new_status,
        "at": datetime.now(timezone.utc).isoformat(),
        "previous_job_status": previous_job_status,
    })
    application.status_history = history


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
            previous_status=_previous_job_status(application),
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
            owner_user_id=user_id,
            job_id=job.id,
            status="Applied",
            applied_at=now,
            resume_type=job.analysis.recommended_resume_type if job.analysis else "General Engineering",
            submitted_resume_id=latest_resume.id if latest_resume else None,
        )
        db.add(application)
        _record_application_status(application, None, "Applied", previous_job_status=previous_status)
    else:
        _record_application_status(application, application.status, "Applied", previous_job_status=previous_status)
        application.status = "Applied"
        application.applied_at = application.applied_at or now
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


def _previous_job_status(application: Application | None) -> Literal["active", "saved"]:
    if application:
        for event in reversed(application.status_history or []):
            if event.get("to") == "Applied" and event.get("previous_job_status") in {"active", "saved"}:
                return event["previous_job_status"]
    return "saved"


@app.post("/api/jobs/{job_id}/undo-applied", response_model=JobLifecycleActionRead)
def undo_job_applied(
    job_id: int,
    payload: UndoAppliedPayload | None = None,
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

    application = db.scalar(
        select(Application)
        .where(Application.job_id == job.id, Application.status == "Applied")
        .order_by(Application.updated_at.desc())
        .limit(1)
    )
    previous_status = _previous_job_status(application)
    job.status = previous_status
    job.applied_at = None
    if application:
        new_status = "Saved" if previous_status == "saved" else "Draft"
        _record_application_status(application, application.status, new_status, previous_job_status="applied")
        application.status = new_status
        # applied_at and submitted_resume_id are historical evidence.
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
        previous_status=previous_status,
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
    latest_application = db.scalar(
        select(Application).where(Application.job_id == job.id).order_by(Application.updated_at.desc()).limit(1)
    )
    job.status = (
        "applied" if latest_application and latest_application.status in {"Applied", "Interview", "Rejected", "Offer"}
        else "saved" if latest_application and latest_application.status == "Saved"
        else "active"
    )
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
def delete_application(
    application_id: int,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="Permanent deletion requires confirm=true. Use status changes or archive to preserve history.",
        )
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


@app.get("/api/discovery/status")
def get_discovery_status(
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Compact operational view; it does not alter normal job dashboards."""
    return discovery_status(db)


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
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> TargetCompany:
    if db.scalar(
        select(TargetCompany.id).where(
            func.lower(TargetCompany.company_name) == payload.company_name.strip().lower()
        )
    ):
        raise HTTPException(status_code=409, detail="Target company already exists.")
    company = TargetCompany(owner_user_id=user_id, **payload.model_dump(), custom=True)
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
def create_source(payload: SourceCreate, user_id: str = Depends(require_private_api), db: Session = Depends(get_db)) -> CompanySource:
    if payload.source_type in {
        "greenhouse", "lever", "workday", "smartrecruiters", "embedded_jobs",
        "amazon_jobs", "official_careers", "oracle_recruiting", "community_repo",
    }:
        validate_public_url(payload.source_url)
    source = CompanySource(owner_user_id=user_id, **payload.model_dump())
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
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == db.info.get("owner_user_id")))
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
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == db.info.get("owner_user_id")))
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


_source_refresh_tasks: dict[str, asyncio.Task] = {}
_source_refresh_results: dict[str, dict] = {}


def _execute_search_run_in_worker(run_id: int) -> None:
    """Keep crawler and synchronous ORM work off the API event loop."""
    asyncio.run(execute_search_run(run_id))


def _run_source_refresh_in_worker(owner_user_id: str) -> dict:
    """Run network and synchronous ORM work outside the web server event loop."""
    with SessionLocal() as refresh_db:
        refresh_db.info["owner_user_id"] = owner_user_id
        return asyncio.run(refresh_all_sources(refresh_db))


async def _run_source_refresh(owner_user_id: str) -> None:
    try:
        summary = await asyncio.to_thread(_run_source_refresh_in_worker, owner_user_id)
        _source_refresh_results[owner_user_id] = {
            "status": "completed",
            "summary": summary,
        }
    except Exception:
        logger.exception("Background source refresh failed for owner %s", owner_user_id)
        _source_refresh_results[owner_user_id] = {
            "status": "failed",
            "message": "Source refresh failed. Check source health for details.",
        }
    finally:
        _source_refresh_tasks.pop(owner_user_id, None)


@app.post("/api/sources/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_sources(
    user_id: str = Depends(require_private_api),
) -> dict:
    if settings.environment.strip().lower() == "production":
        return {
            "status": "external_scheduler",
            "accepted": False,
            "message": "Production source refreshes run outside the web service.",
        }
    running = _source_refresh_tasks.get(user_id)
    if running and not running.done():
        return {"status": "running", "accepted": False}
    _source_refresh_results[user_id] = {"status": "running"}
    _source_refresh_tasks[user_id] = asyncio.create_task(_run_source_refresh(user_id))
    return {"status": "running", "accepted": True}


@app.get("/api/sources/refresh/status")
def source_refresh_status(
    user_id: str = Depends(require_private_api),
) -> dict:
    return _source_refresh_results.get(user_id, {"status": "idle"})


@app.get("/api/stats", response_model=StatsRead)
def get_stats(
    search_run_id: int | None = Query(default=None, ge=1),
    user_id: str = Depends(require_private_api),
    db: Session = Depends(get_db),
) -> StatsRead:
    # Statistics arrive before (or in parallel with) the job list. Reconcile
    # here too so Santiago sees a valid manual action immediately.
    if user_id == settings.effective_primary_user_id:
        apply_requested_santiago_overrides(db, user_id)
    if fail_abandoned_search_runs(db, owner_user_id=user_id):
        db.commit()
    expire_past_deadline_jobs(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    hidden_statuses = ["ignored"]
    if not settings.demo_feed_enabled:
        hidden_statuses.append("demo")
    visible_filters = [
        Job.discovery_status.not_in(hidden_statuses),
        Job.status.in_(ACTIVE_JOB_STATUSES),
    ]
    scoped_run = None
    if search_run_id is not None:
        scoped_run = db.get(SearchRun, search_run_id)
        if not scoped_run or scoped_run.owner_user_id != user_id:
            raise HTTPException(status_code=404, detail="Search run not found.")
        visible_filters.append(
            Job.id.in_(
                select(SearchRunJob.job_id).where(
                    SearchRunJob.search_run_id == search_run_id,
                    SearchRunJob.owner_user_id == user_id,
                )
            )
        )
    visible_jobs = and_(*visible_filters)
    recommendation_counts = dict(
        db.execute(
            select(JobAnalysis.recommendation, func.count(JobAnalysis.id))
            .join(Job, JobAnalysis.job_id == Job.id)
            .where(visible_jobs)
            .group_by(JobAnalysis.recommendation)
        ).all()
    )
    # Manual actions intentionally do not rewrite JobAnalysis.recommendation.
    # Include this candidate-owned action in the dashboard without counting a
    # naturally Apply Now/Today posting twice.
    manual_apply_now_count = db.scalar(
        select(func.count(Job.id))
        .join(JobAnalysis, JobAnalysis.job_id == Job.id)
        .where(
            visible_jobs,
            _force_apply_active_clause(user_id),
            JobAnalysis.recommendation.not_in(("Apply Now", "Apply Today")),
        )
    ) or 0
    latest_run = scoped_run or db.scalar(
        select(SearchRun)
        .where(SearchRun.owner_user_id == user_id)
        .order_by(SearchRun.started_at.desc())
        .limit(1)
    )
    last_completed_run = (
        scoped_run
        if scoped_run and scoped_run.status in {"completed", "partial"}
        else db.scalar(
            select(SearchRun)
            .where(
                SearchRun.owner_user_id == user_id,
                SearchRun.status.in_(("completed", "partial")),
            )
            .order_by(SearchRun.completed_at.desc())
            .limit(1)
        )
    )
    return StatsRead(
        total_jobs=db.scalar(select(func.count(Job.id)).where(visible_jobs)) or 0,
        new_jobs=db.scalar(
            select(func.count(Job.id)).where(visible_jobs, Job.first_seen_at >= cutoff)
        )
        or 0,
        apply_today=(
            recommendation_counts.get("Apply Today", 0)
            + recommendation_counts.get("Apply Now", 0)
            + manual_apply_now_count
        ),
        review=recommendation_counts.get("Review", 0),
        needs_verification=recommendation_counts.get("Needs Verification", 0),
        not_eligible=recommendation_counts.get("Not Eligible", 0),
        low_match=recommendation_counts.get("Low Match", 0),
        closed=(
            recommendation_counts.get("Closed", 0)
            + recommendation_counts.get("Expired", 0)
        ),
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


from app.talent_api import router as talent_router
app.include_router(talent_router)
