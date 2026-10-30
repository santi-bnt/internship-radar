from sqlalchemy import func, inspect, select, text

from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import (
    Application,
    ApplicationAnswerRegistry,
    ApplicationProfile,
    ApplicationSession,
    CompanyPortalRegistry,
    CandidateJobOverride,
    CompanySource,
    GeneratedResume,
    GeneratedPortfolio,
    Job,
    JobAnalysis,
    Notification,
    ResumeProfile,
    SearchRun,
    SearchRunJob,
    TargetCompany,
    TargetSearchRun,
    UserProfile,
)
from app.services.company_portal_registry import COMPANY_PORTAL_REGISTRY
from app.security.identity import JOSHUA_EMAIL, JOSHUA_USER_ID


SQLITE_ADDITIONS = {
    "user_profiles": {
        "display_name": "VARCHAR(80) NOT NULL DEFAULT ''",
        "gpa_scale_status": "VARCHAR(40) NOT NULL DEFAULT 'CONFIRMED'",
        "current_semester": "INTEGER",
        "official_degree_name": "VARCHAR(240)",
        "official_degree_name_status": "VARCHAR(40) NOT NULL DEFAULT 'CONFIRMED'",
        "citizenship_status": "VARCHAR(40) NOT NULL DEFAULT 'CONFIRMED'",
        "us_authorization_conflict_detected": "BOOLEAN NOT NULL DEFAULT 0",
        "work_authorization_raw_statement": "TEXT NOT NULL DEFAULT ''",
        "minimum_hours_per_week": "INTEGER",
        "github_url": "TEXT NOT NULL DEFAULT ''",
        "linkedin_url": "TEXT NOT NULL DEFAULT ''",
        "onboarding_status": "VARCHAR(40) NOT NULL DEFAULT 'PROFILE_READY'",
        "profile_warnings": "JSON NOT NULL DEFAULT '[]'",
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
        "citizenship_country": "VARCHAR(100) NOT NULL DEFAULT 'Mexico'",
        "work_authorized_countries": """JSON NOT NULL DEFAULT '["Mexico"]'""",
        "us_work_authorized": "BOOLEAN NOT NULL DEFAULT 0",
        "requires_us_employment_sponsorship": "BOOLEAN NOT NULL DEFAULT 1",
        "degree_level_current": "VARCHAR(30) NOT NULL DEFAULT 'BACHELORS'",
        "degree_status": "VARCHAR(40) NOT NULL DEFAULT 'IN_PROGRESS'",
        "expected_graduation_date": "DATE",
        "degree_field": "VARCHAR(240) NOT NULL DEFAULT 'Robotics and Digital Systems Engineering'",
        "veteran_status": "VARCHAR(30) NOT NULL DEFAULT 'NOT_VETERAN'",
        "military_status": "VARCHAR(40) NOT NULL DEFAULT 'NONE'",
        "military_spouse": "BOOLEAN NOT NULL DEFAULT 0",
        "disability_status": "VARCHAR(40) NOT NULL DEFAULT 'NO_DISABILITY'",
        "current_service_member": "BOOLEAN NOT NULL DEFAULT 0",
        "countries_to_search": """JSON NOT NULL DEFAULT '["Mexico","United States","Canada"]'""",
        "include_remote": "BOOLEAN NOT NULL DEFAULT 1",
        "only_remote": "BOOLEAN NOT NULL DEFAULT 0",
        "remote_from_mexico_only": "BOOLEAN NOT NULL DEFAULT 0",
        "include_hybrid": "BOOLEAN NOT NULL DEFAULT 1",
        "include_onsite": "BOOLEAN NOT NULL DEFAULT 1",
        "priority_alerts": "BOOLEAN NOT NULL DEFAULT 1",
        "priority_minimum_score": "FLOAT NOT NULL DEFAULT 80",
        "alert_for_major_companies": "BOOLEAN NOT NULL DEFAULT 1",
        "major_company_minimum_score": "FLOAT NOT NULL DEFAULT 70",
        "alert_for_deadlines": "BOOLEAN NOT NULL DEFAULT 1",
        "email_notifications": "BOOLEAN NOT NULL DEFAULT 0",
        "notification_email": "VARCHAR(320) NOT NULL DEFAULT 'notifications@example.com'",
        "priority_email_alerts": "BOOLEAN NOT NULL DEFAULT 1",
        "major_company_email_alerts": "BOOLEAN NOT NULL DEFAULT 0",
        "deadline_alerts": "BOOLEAN NOT NULL DEFAULT 0",
        "daily_digest": "BOOLEAN NOT NULL DEFAULT 0",
        "application_follow_up_alerts": "BOOLEAN NOT NULL DEFAULT 0",
        "email_minimum_score": "FLOAT NOT NULL DEFAULT 80",
        "immediate_priority_alerts": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "jobs": {
        "opportunity_type": "VARCHAR(40) NOT NULL DEFAULT 'job'",
        "lab": "VARCHAR(240) NOT NULL DEFAULT ''",
        "supervisor": "VARCHAR(240) NOT NULL DEFAULT ''",
        "research_areas": "JSON NOT NULL DEFAULT '[]'",
        "research_url": "TEXT NOT NULL DEFAULT ''",
        "research_notes": "TEXT NOT NULL DEFAULT ''",
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
        "city": "VARCHAR(140) NOT NULL DEFAULT ''",
        "region": "VARCHAR(140) NOT NULL DEFAULT ''",
        "remote_regions": """JSON NOT NULL DEFAULT '[]'""",
        "remote_countries_allowed": """JSON NOT NULL DEFAULT '[]'""",
        "remote_from_mexico_allowed": "BOOLEAN NOT NULL DEFAULT 0",
        "remote_scope": "VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN'",
        "physical_work_country_required": "VARCHAR(100) NOT NULL DEFAULT 'Unknown'",
        "can_work_from_mexico": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "job_requires_work_in_us": "BOOLEAN NOT NULL DEFAULT 0",
        "sponsorship_status": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "sponsorship_evidence_text": "TEXT NOT NULL DEFAULT ''",
        "sponsorship_source_url": "TEXT NOT NULL DEFAULT ''",
        "sponsorship_last_verified_at": "DATETIME",
        "relocation_required": "BOOLEAN NOT NULL DEFAULT 0",
        "minimum_degree_level": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "accepted_degree_levels": """JSON NOT NULL DEFAULT '[]'""",
        "degree_completion_required": "VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN'",
        "currently_enrolled_allowed": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "graduation_before_start_required": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "accepted_degree_fields": """JSON NOT NULL DEFAULT '[]'""",
        "student_status_required": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "required_graduation_start": "DATE",
        "required_graduation_end": "DATE",
        "degree_requirement_evidence": "TEXT NOT NULL DEFAULT ''",
        "special_program_type": "VARCHAR(50) NOT NULL DEFAULT 'NONE'",
        "special_program_required": "BOOLEAN NOT NULL DEFAULT 0",
        "special_program_evidence": "TEXT NOT NULL DEFAULT ''",
        "area": "VARCHAR(100) NOT NULL DEFAULT 'Unknown'",
        "company_importance": "VARCHAR(50) NOT NULL DEFAULT 'Unknown'",
        "official_apply_url": "TEXT",
        "posting_url": "TEXT NOT NULL DEFAULT ''",
        "application_url": "TEXT NOT NULL DEFAULT ''",
        "application_url_source": "VARCHAR(80) NOT NULL DEFAULT 'UNKNOWN'",
        "application_url_status": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "application_url_last_verified_at": "DATETIME",
        "application_url_diagnostic": "VARCHAR(80) NOT NULL DEFAULT ''",
        "original_source_url": "TEXT NOT NULL DEFAULT ''",
        "discovered_from": "VARCHAR(100) NOT NULL DEFAULT ''",
        "discovered_from_source": "VARCHAR(180) NOT NULL DEFAULT ''",
        "verified_from_source": "VARCHAR(180) NOT NULL DEFAULT ''",
        "discovery_sources": """JSON NOT NULL DEFAULT '[]'""",
        "source_confidence_score": "FLOAT NOT NULL DEFAULT 0",
        "community_sponsorship_signal": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "community_markers": """JSON NOT NULL DEFAULT '[]'""",
        "company_normalized": "VARCHAR(180) NOT NULL DEFAULT ''",
        "title_normalized": "VARCHAR(300) NOT NULL DEFAULT ''",
        "ats_requisition_id": "VARCHAR(255) NOT NULL DEFAULT ''",
        "canonical_official_url": "TEXT NOT NULL DEFAULT ''",
        "official_domain": "VARCHAR(255) NOT NULL DEFAULT ''",
        "alternate_sources": """JSON NOT NULL DEFAULT '[]'""",
        "is_target_company": "BOOLEAN NOT NULL DEFAULT 0",
        "target_company_category": "VARCHAR(80) NOT NULL DEFAULT ''",
        "company_priority": "VARCHAR(20) NOT NULL DEFAULT ''",
        "company_priority_bonus": "FLOAT NOT NULL DEFAULT 0",
        "discovery_status": "VARCHAR(40) NOT NULL DEFAULT 'discovered'",
        "official_status": "VARCHAR(40) NOT NULL DEFAULT 'unknown'",
        "verification_status": "VARCHAR(50) NOT NULL DEFAULT 'unverified'",
        "verification_method": "VARCHAR(100) NOT NULL DEFAULT 'not_attempted'",
        "status_reason": "TEXT NOT NULL DEFAULT ''",
        "last_verified_at": "DATETIME",
        "verification_failures": "INTEGER NOT NULL DEFAULT 0",
        "official_posted_at": "DATETIME",
        "source_posted_at": "DATETIME",
        "expires_at": "DATETIME",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'active'",
        "application_deadline": "DATE",
        "deadline_source": "VARCHAR(100)",
        "deadline_confidence": "FLOAT",
        "submitted_resume_id": "INTEGER",
        "applied_at": "DATETIME",
        "expired_at": "DATETIME",
        "archived_at": "DATETIME",
        "updated_at": "DATETIME",
        "is_priority_alert": "BOOLEAN NOT NULL DEFAULT 0",
        "priority_alerted_at": "DATETIME",
        "urgency": "VARCHAR(40) NOT NULL DEFAULT 'Recent'",
        "recycled_posting": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "job_analyses": {
        "effective_score": "FLOAT NOT NULL DEFAULT 0",
        "remote_eligibility_bonus": "FLOAT NOT NULL DEFAULT 0",
        "degree_level_match": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "degree_field_match": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "degree_completion_match": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "graduation_window_match": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "student_status_match": "VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
        "education_eligibility_status": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "education_eligibility_reason": "TEXT NOT NULL DEFAULT ''",
        "special_program_eligibility_status": "VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN'",
        "special_program_eligibility_reason": "TEXT NOT NULL DEFAULT ''",
    },
    "applications": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
        "submitted_resume_id": "INTEGER",
        "application_session_id": "INTEGER",
    },
    "notifications": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
    },
    "company_sources": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
        "registry_type": "VARCHAR(40) NOT NULL DEFAULT 'OTHER'",
        "priority": "INTEGER NOT NULL DEFAULT 50",
        "base_priority": "INTEGER NOT NULL DEFAULT 50",
        "trust_level": "VARCHAR(20) NOT NULL DEFAULT 'MEDIUM'",
        "refresh_frequency": "VARCHAR(40) NOT NULL DEFAULT 'daily'",
        "supports_structured_data": "BOOLEAN NOT NULL DEFAULT 0",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "source_confidence_score": "FLOAT NOT NULL DEFAULT 50",
        "reference_only": "BOOLEAN NOT NULL DEFAULT 0",
        "last_successful_fetch": "DATETIME",
        "last_repository_update": "DATETIME",
        "last_successful_parse": "DATETIME",
        "last_new_job_seen": "DATETIME",
        "source_status": "VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'",
        "fetched_count": "INTEGER NOT NULL DEFAULT 0",
        "parsed_count": "INTEGER NOT NULL DEFAULT 0",
        "new_jobs_count": "INTEGER NOT NULL DEFAULT 0",
        "updated_jobs_count": "INTEGER NOT NULL DEFAULT 0",
        "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
        "officially_verified_count": "INTEGER NOT NULL DEFAULT 0",
        "unverified_count": "INTEGER NOT NULL DEFAULT 0",
        "error_count": "INTEGER NOT NULL DEFAULT 0",
        "duration_ms": "INTEGER NOT NULL DEFAULT 0",
        "last_attempt_at": "DATETIME",
        "last_success_at": "DATETIME",
        "last_error_at": "DATETIME",
        "last_error_type": "VARCHAR(50) NOT NULL DEFAULT ''",
        "safe_error_message": "TEXT NOT NULL DEFAULT ''",
        "http_status": "INTEGER",
        "parser_version": "VARCHAR(40) NOT NULL DEFAULT '1'",
        "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
        "jobs_discovered": "INTEGER NOT NULL DEFAULT 0",
        "jobs_verified": "INTEGER NOT NULL DEFAULT 0",
        "discovery_group": "VARCHAR(40) NOT NULL DEFAULT 'GENERAL'",
        "geography_scope": "VARCHAR(30) NOT NULL DEFAULT 'US_CANADA'",
        "source_domain": "VARCHAR(255) NOT NULL DEFAULT ''",
        "next_run_at": "DATETIME",
        "backoff_until": "DATETIME",
        "rate_limited_until": "DATETIME",
        "retry_after_seconds": "INTEGER",
        "discovery_checkpoint_json": "JSON NOT NULL DEFAULT '{}'",
    },
    "target_companies": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
    },
    "target_search_runs": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
    },
    "search_runs": {
        "owner_user_id": "VARCHAR(160) NOT NULL DEFAULT 'primary-user'",
        "source_metrics": """JSON NOT NULL DEFAULT '[]'""",
        "criteria_json": """JSON NOT NULL DEFAULT '{}'""",
        "progress_json": """JSON NOT NULL DEFAULT '{}'""",
        "result_count": "INTEGER NOT NULL DEFAULT 0",
        "eligible_count": "INTEGER NOT NULL DEFAULT 0",
        "verified_count": "INTEGER NOT NULL DEFAULT 0",
        "history_deleted_at": "DATETIME",
    },
    "application_profiles": {
        "job_discovery_source": "VARCHAR(60) NOT NULL DEFAULT 'GOOGLE_SEARCH'",
        "full_time_summer_availability": "BOOLEAN NOT NULL DEFAULT 1",
        "spring_summer_combined_availability": "BOOLEAN NOT NULL DEFAULT 1",
        "application_preferences_confirmed_at": "DATETIME",
    },
    "resume_profiles": {
        "github_evidence_json": "JSON NOT NULL DEFAULT '[]'",
    },
    "application_answer_registry": {},
    "application_sessions": {
        "portal_detection_evidence_json": "JSON NOT NULL DEFAULT '[]'",
        "adapter_diagnostics_json": "JSON NOT NULL DEFAULT '{}'",
        "adapter_version": "VARCHAR(40) NOT NULL DEFAULT ''",
        "company_policy_key": "VARCHAR(80) NOT NULL DEFAULT 'GENERIC'",
        "assessment_type": "VARCHAR(60) NOT NULL DEFAULT ''",
        "resume_filename": "VARCHAR(320) NOT NULL DEFAULT ''",
        "resume_download_url": "TEXT NOT NULL DEFAULT ''",
        "portfolio_version_id": "INTEGER",
        "portfolio_filename": "VARCHAR(320) NOT NULL DEFAULT ''",
        "portfolio_download_url": "TEXT NOT NULL DEFAULT ''",
        "selected_projects_json": "JSON NOT NULL DEFAULT '[]'",
        "generated_experience_text": "TEXT NOT NULL DEFAULT ''",
        "selected_skills_json": "JSON NOT NULL DEFAULT '[]'",
        "skill_match_reasons_json": "JSON NOT NULL DEFAULT '{}'",
        "project_match_reasons_json": "JSON NOT NULL DEFAULT '{}'",
        "selection_warnings_json": "JSON NOT NULL DEFAULT '[]'",
    },
    "generated_resumes": {
        "resume_target": "VARCHAR(80) NOT NULL DEFAULT 'recommended'",
        "selected_skills": "JSON NOT NULL DEFAULT '[]'",
        "skill_categories": "JSON NOT NULL DEFAULT '[]'",
        "job_skill_matches": "JSON NOT NULL DEFAULT '[]'",
        "skill_verification": "JSON NOT NULL DEFAULT '{}'",
        "compiled_pdf": "BLOB",
        "compiled_pdf_at": "DATETIME",
        "source_input_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
        "active_generation_owner": "VARCHAR(320)",
    },
}

POSTGRES_ADDITIONS = {
    table: {
        column: ddl.replace("BOOLEAN NOT NULL DEFAULT 1", "BOOLEAN NOT NULL DEFAULT TRUE")
        .replace("BOOLEAN NOT NULL DEFAULT 0", "BOOLEAN NOT NULL DEFAULT FALSE")
        .replace("DATETIME", "TIMESTAMPTZ")
        .replace("JSON NOT NULL DEFAULT", "JSONB NOT NULL DEFAULT")
        for column, ddl in columns.items()
    }
    for table, columns in SQLITE_ADDITIONS.items()
}

OWNER_TABLES = (
    "user_profiles",
    "jobs",
    "applications",
    "notifications",
    "company_sources",
    "target_companies",
    "target_search_runs",
    "search_runs",
    "search_run_jobs",
    "application_profiles",
    "application_answer_registry",
    "application_sessions",
)


def _add_missing_columns() -> None:
    additions = POSTGRES_ADDITIONS if engine.dialect.name == "postgresql" else SQLITE_ADDITIONS
    schema = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in schema.get_columns(table)}
            for column, ddl in columns.items():
                if column not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
        refreshed_schema = inspect(connection)
        for table_name in OWNER_TABLES:
            index_name = f"ix_{table_name}_owner_user_id"
            existing_indexes = {
                index["name"] for index in refreshed_schema.get_indexes(table_name)
            }
            if index_name not in existing_indexes:
                connection.execute(
                    text(
                        f'CREATE INDEX "{index_name}" '
                        f'ON "{table_name}" ("owner_user_id")'
                    )
                )


def _backfill_job_lifecycle() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE jobs
                SET updated_at = CURRENT_TIMESTAMP
                WHERE updated_at IS NULL
                """
            )
        )
        deadline_expression = (
            "DATE(expires_at)"
            if engine.dialect.name == "sqlite"
            else "CAST(expires_at AS DATE)"
        )
        connection.execute(
            text(
                f"""
                UPDATE jobs
                SET application_deadline = {deadline_expression}
                WHERE application_deadline IS NULL AND expires_at IS NOT NULL
                """
            )
        )
        if engine.dialect.name == "sqlite":
            connection.execute(
                text(
                    """
                    UPDATE jobs
                    SET application_deadline = DATE(expires_at)
                    WHERE application_deadline IS NOT NULL
                      AND TYPEOF(application_deadline) != 'text'
                    """
                )
            )
        connection.execute(
            text(
                """
                UPDATE jobs
                SET deadline_source = 'structured_source', deadline_confidence = 1.0
                WHERE application_deadline IS NOT NULL AND deadline_confidence IS NULL
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE jobs
                SET status = 'applied',
                    applied_at = (
                        SELECT MAX(applications.applied_at)
                        FROM applications
                        WHERE applications.job_id = jobs.id
                          AND LOWER(applications.status) = 'applied'
                    )
                WHERE status IN ('active', 'saved')
                  AND EXISTS (
                      SELECT 1 FROM applications
                      WHERE applications.job_id = jobs.id
                        AND LOWER(applications.status) = 'applied'
                  )
                """
            )
        )


def _consolidate_primary_identity() -> None:
    primary_user_id = settings.primary_user_id.strip()
    if not primary_user_id:
        return
    legacy_ids = {
        "primary-user",
        *(email for email in settings.authorized_email_set if email != JOSHUA_EMAIL),
        primary_user_id,
    }
    with SessionLocal() as db:
        joshua_legacy = db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == JOSHUA_EMAIL
        ))
        joshua_profile = db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == JOSHUA_USER_ID
        ))
        if joshua_legacy:
            if joshua_profile:
                # The UUID-backed profile is authoritative. This legacy row may
                # already have been polluted by the former single-user seed.
                db.delete(joshua_legacy)
            else:
                joshua_legacy.user_id = JOSHUA_USER_ID
        db.execute(
            GeneratedResume.__table__.update()
            .where(GeneratedResume.user_id == JOSHUA_EMAIL)
            .values(user_id=JOSHUA_USER_ID)
        )
        db.execute(
            GeneratedPortfolio.__table__.update()
            .where(GeneratedPortfolio.user_id == JOSHUA_EMAIL)
            .values(user_id=JOSHUA_USER_ID)
        )
        db.flush()
        profiles = list(
            db.scalars(
                select(ResumeProfile)
                .where(ResumeProfile.user_id.in_(legacy_ids))
                .order_by(
                    (ResumeProfile.user_id == primary_user_id).desc(),
                    (ResumeProfile.email == settings.resume_email).desc(),
                    ResumeProfile.id.asc(),
                )
            )
        )
        primary_profile = profiles[0] if profiles else None
        if primary_profile and primary_profile.user_id != primary_user_id:
            db.execute(
                GeneratedResume.__table__.update()
                .where(GeneratedResume.user_id == primary_profile.user_id)
                .values(user_id=primary_user_id)
            )
        merge_fields = (
            "full_name",
            "email",
            "phone",
            "location",
            "linkedin_url",
            "github_url",
            "headline",
            "summary",
            "education_json",
            "skills_json",
            "experience_json",
            "projects_json",
            "coursework_json",
            "certifications_json",
            "languages_json",
            "language_credentials_json",
            "forbidden_claims_json",
        )
        for duplicate in profiles[1:]:
            if primary_profile:
                for field in merge_fields:
                    if not getattr(primary_profile, field) and getattr(duplicate, field):
                        setattr(primary_profile, field, getattr(duplicate, field))
            resumes = list(
                db.scalars(
                    select(GeneratedResume)
                    .where(GeneratedResume.user_id == duplicate.user_id)
                    .order_by(GeneratedResume.job_id, GeneratedResume.version)
                )
            )
            for resume in resumes:
                next_version = (
                    db.scalar(
                        select(func.max(GeneratedResume.version)).where(
                            GeneratedResume.user_id == primary_user_id,
                            GeneratedResume.job_id == resume.job_id,
                            GeneratedResume.id != resume.id,
                        )
                    )
                    or 0
                ) + 1
                resume.user_id = primary_user_id
                resume.version = max(resume.version, next_version)
            db.delete(duplicate)
        if primary_profile:
            primary_profile.user_id = primary_user_id
            primary_profile.email = settings.resume_email
        db.execute(
            GeneratedResume.__table__.update()
            .where(GeneratedResume.user_id.in_(legacy_ids - {primary_user_id}))
            .values(user_id=primary_user_id)
        )
        db.execute(
            GeneratedPortfolio.__table__.update()
            .where(GeneratedPortfolio.user_id.in_(legacy_ids - {primary_user_id}))
            .values(user_id=primary_user_id)
        )
        for model in (
            UserProfile,
            Job,
            Application,
            ApplicationProfile,
            ApplicationAnswerRegistry,
            ApplicationSession,
            Notification,
            CompanySource,
            TargetCompany,
            TargetSearchRun,
            SearchRun,
            SearchRunJob,
        ):
            db.execute(
                model.__table__.update()
                .where(model.owner_user_id.in_(legacy_ids))
                .values(owner_user_id=primary_user_id),
                execution_options={"skip_owner_scope": True},
            )
        db.commit()


def _seed_company_portal_registry() -> None:
    with SessionLocal() as db:
        for entry in COMPANY_PORTAL_REGISTRY:
            record = db.scalar(
                select(CompanyPortalRegistry).where(
                    CompanyPortalRegistry.company_id == entry["company_id"]
                )
            )
            if record is None:
                record = CompanyPortalRegistry(company_id=entry["company_id"])
                db.add(record)
            record.company_name = entry["company_name"]
            record.known_domains_json = list(entry["known_domains"])
            record.portal_type = entry["portal_type"]
            record.application_adapter = entry["application_adapter"]
            record.company_specific_rules_json = dict(entry["company_specific_rules"])
            record.resume_behavior = "JOB_SPECIFIC"
            record.skills_behavior = "JOB_SPECIFIC_INDIVIDUAL"
            record.known_question_aliases_json = dict(entry["known_question_aliases"])
            record.support_status = entry["support_status"]
        db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    _backfill_job_lifecycle()
    _consolidate_primary_identity()
    _seed_company_portal_registry()
