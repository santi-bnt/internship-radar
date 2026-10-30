from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ApplicationProfile, AuthorizedAccount, CompanySource, Job, ResumeProfile,
    TargetCompany, UserProfile,
)
from app.security.identity import (
    ALONSO_EMAIL, ALONSO_USER_ID, INDEPENDENT_CANDIDATE_IDS,
    JOSHUA_EMAIL, JOSHUA_USER_ID, normalize_email,
)
from app.services.candidate_registry import INDEPENDENT_CANDIDATE_SEEDS, CandidateSeed

JOSHUA_WARNING = (
    "Your answers indicate that you are not currently authorized to work in the United States "
    "and would require sponsorship, but USA was also listed as an authorized country. Please confirm."
)
JOSHUA_DEGREE = "B.S. in Robotics and Digital Systems Engineering"
JOSHUA_STUDENT_TITLE = "Robotics and Digital Systems Engineering Student"
JOSHUA_GRADUATION_DATE = date(2028, 6, 30)

JOSHUA_SKILLS = []

JOSHUA_PROJECTS = []


def seed_authorized_accounts_and_joshua(db: Session) -> None:
    """Provision only explicitly configured identities; no candidate facts are fabricated."""
    from app.security.identity import resolve_primary_user
    for email in settings.authorized_email_set | set(INDEPENDENT_CANDIDATE_IDS):
        owner = resolve_primary_user(email)
        if owner and db.scalar(select(AuthorizedAccount).where(AuthorizedAccount.email == email)) is None:
            db.add(AuthorizedAccount(user_id=owner, email=email, provider="google", is_active=True))
    db.commit()


def _copy_candidate_discovery_configuration(db: Session, owner_user_id: str) -> None:
    """Clone discovery configuration only; jobs and analysis stay user-owned."""
    primary_user_id = settings.effective_primary_user_id
    primary_sources = list(db.scalars(select(CompanySource).where(
        CompanySource.owner_user_id == primary_user_id,
    ).execution_options(skip_owner_scope=True)))
    existing_source_keys = {
        (item.source_type, item.source_identifier)
        for item in db.scalars(select(CompanySource).where(
            CompanySource.owner_user_id == owner_user_id,
        ).execution_options(skip_owner_scope=True))
    }
    copy_fields = (
        "company", "source_type", "source_identifier", "source_url", "registry_type",
        "priority", "base_priority", "trust_level", "refresh_frequency",
        "supports_structured_data", "notes", "source_confidence_score",
        "reference_only", "enabled",
    )
    for source in primary_sources:
        key = (source.source_type, source.source_identifier)
        if key not in existing_source_keys:
            db.add(CompanySource(owner_user_id=owner_user_id, **{
                field: getattr(source, field) for field in copy_fields
            }))
    primary_targets = list(db.scalars(select(TargetCompany).where(
        TargetCompany.owner_user_id == primary_user_id,
    ).execution_options(skip_owner_scope=True)))
    existing_targets = set(db.scalars(select(TargetCompany.company_name).where(
        TargetCompany.owner_user_id == owner_user_id,
    ).execution_options(skip_owner_scope=True)))
    target_fields = (
        "company_name", "aliases", "careers_domains", "category", "priority",
        "enabled", "custom", "preferred_locations", "preferred_role_categories",
    )
    for target in primary_targets:
        if target.company_name not in existing_targets:
            db.add(TargetCompany(owner_user_id=owner_user_id, **{
                field: getattr(target, field) for field in target_fields
            }))


def seed_independent_candidate(db: Session, candidate: CandidateSeed) -> None:
    """Idempotently add a candidate without overwriting any existing profile.

    The seed is intentionally append-only after first creation. Candidate edits
    made through the product remain candidate-owned and are never reset by a
    startup or migration pass.
    """
    db.info.pop("owner_user_id", None)
    account = db.scalar(select(AuthorizedAccount).where(
        AuthorizedAccount.provider == "google", AuthorizedAccount.email == candidate.email,
    ))
    if account is None:
        db.add(AuthorizedAccount(user_id=candidate.user_id, email=candidate.email, provider="google", is_active=True))
    elif account.user_id != candidate.user_id:
        raise RuntimeError(f"Authorized email {candidate.email} is already bound to another candidate.")
    else:
        account.is_active = True

    if db.scalar(select(UserProfile).where(UserProfile.owner_user_id == candidate.user_id)) is None:
        db.add(UserProfile(owner_user_id=candidate.user_id, **candidate.user_profile))
    if db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == candidate.user_id)) is None:
        db.add(ResumeProfile(user_id=candidate.user_id, **candidate.resume_profile))
    if db.scalar(select(ApplicationProfile).where(ApplicationProfile.owner_user_id == candidate.user_id)) is None:
        db.add(ApplicationProfile(owner_user_id=candidate.user_id, **candidate.application_profile))
    _copy_candidate_discovery_configuration(db, candidate.user_id)
    db.commit()


def seed_authorized_accounts_and_candidates(db: Session) -> None:
    """Preserve the legacy primary/Joshua setup and add registry candidates."""
    seed_authorized_accounts_and_joshua(db)
    for candidate in INDEPENDENT_CANDIDATE_SEEDS:
        seed_independent_candidate(db, candidate)


def ensure_candidate_job_catalog(db: Session, owner_user_id: str) -> None:
    primary_jobs = list(db.scalars(select(Job).where(
        Job.owner_user_id == settings.effective_primary_user_id,
        Job.is_active.is_(True),
    ).order_by(Job.last_seen_at.desc()).execution_options(skip_owner_scope=True)))
    candidate_jobs = list(db.scalars(select(Job).where(
        Job.owner_user_id == owner_user_id,
    ).execution_options(skip_owner_scope=True)))

    def catalog_key(job: Job) -> tuple[str, str, str]:
        return (
            (job.source_name or "").strip().casefold(),
            (job.external_id or "").strip().casefold(),
            (job.canonical_official_url or job.apply_url or job.source_url or "").strip().casefold(),
        )

    existing_keys = {catalog_key(job) for job in candidate_jobs}
    excluded = {
        "id", "owner_user_id", "submitted_resume_id", "applied_at",
        "expired_at", "archived_at", "priority_alerted_at",
    }
    columns = [column.key for column in Job.__table__.columns if column.key not in excluded]
    for source_job in primary_jobs:
        key = catalog_key(source_job)
        if key in existing_keys:
            continue
        values = {key: getattr(source_job, key) for key in columns}
        values.update(status="active", submitted_resume_id=None, applied_at=None)
        db.add(Job(owner_user_id=owner_user_id, **values))
        existing_keys.add(key)
    db.commit()


def ensure_joshua_job_catalog(db: Session) -> None:
    return None


def ensure_independent_candidate_job_catalogs(db: Session) -> None:
    for candidate in INDEPENDENT_CANDIDATE_SEEDS:
        ensure_candidate_job_catalog(db, candidate.user_id)
