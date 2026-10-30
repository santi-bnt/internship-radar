from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def primary_owner() -> str:
    return settings.primary_user_id.strip() or "primary-user"


def notification_recipient() -> str:
    return settings.notification_email.strip() or "notifications@example.com"


class AuthorizedAccount(Base):
    __tablename__ = "authorized_accounts"
    __table_args__ = (UniqueConstraint("provider", "email", name="uq_authorized_account_provider_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(160), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="google")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    full_name: Mapped[str] = mapped_column(String(160))
    # Used only in the workspace UI; resumes and applications keep full_name.
    display_name: Mapped[str] = mapped_column(String(80), default="")
    degree: Mapped[str] = mapped_column(String(240))
    university: Mapped[str] = mapped_column(String(240))
    graduation_year: Mapped[int] = mapped_column(Integer)
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    degree_level_current: Mapped[str] = mapped_column(String(30), default="BACHELORS")
    degree_status: Mapped[str] = mapped_column(String(40), default="IN_PROGRESS")
    expected_graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    degree_field: Mapped[str] = mapped_column(
        String(240), default="Robotics and Digital Systems Engineering"
    )
    veteran_status: Mapped[str] = mapped_column(String(30), default="NOT_VETERAN")
    military_status: Mapped[str] = mapped_column(String(40), default="NONE")
    military_spouse: Mapped[bool] = mapped_column(Boolean, default=False)
    disability_status: Mapped[str] = mapped_column(String(40), default="NO_DISABILITY")
    current_service_member: Mapped[bool] = mapped_column(Boolean, default=False)
    gpa: Mapped[float] = mapped_column(Float)
    gpa_scale: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpa_scale_status: Mapped[str] = mapped_column(String(40), default="CONFIRMED")
    current_semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    official_degree_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    official_degree_name_status: Mapped[str] = mapped_column(String(40), default="CONFIRMED")
    nationality: Mapped[str] = mapped_column(String(100))
    citizenship_country: Mapped[str] = mapped_column(String(100), default="Mexico")
    citizenship_status: Mapped[str] = mapped_column(String(40), default="CONFIRMED")
    visas: Mapped[list[str]] = mapped_column(JSON, default=list)
    work_authorizations: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    work_authorized_countries: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["Mexico"]
    )
    us_work_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_us_employment_sponsorship: Mapped[bool] = mapped_column(Boolean, default=True)
    us_authorization_conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    work_authorization_raw_statement: Mapped[str] = mapped_column(Text, default="")
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_hours_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_url: Mapped[str] = mapped_column(Text, default="")
    linkedin_url: Mapped[str] = mapped_column(Text, default="")
    onboarding_status: Mapped[str] = mapped_column(String(40), default="PROFILE_READY")
    profile_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    education_notes: Mapped[str] = mapped_column(Text, default="")
    countries_to_search: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["Mexico", "United States", "Canada"]
    )
    include_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    only_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_from_mexico_only: Mapped[bool] = mapped_column(Boolean, default=False)
    include_hybrid: Mapped[bool] = mapped_column(Boolean, default=True)
    include_onsite: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_minimum_score: Mapped[float] = mapped_column(Float, default=80.0)
    alert_for_major_companies: Mapped[bool] = mapped_column(Boolean, default=True)
    major_company_minimum_score: Mapped[float] = mapped_column(Float, default=70.0)
    alert_for_deadlines: Mapped[bool] = mapped_column(Boolean, default=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_email: Mapped[str] = mapped_column(
        String(320), default=notification_recipient
    )
    priority_email_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    major_company_email_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    deadline_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    application_follow_up_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    email_minimum_score: Mapped[float] = mapped_column(Float, default=80.0)
    immediate_priority_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    opportunity_type: Mapped[str] = mapped_column(String(40), default="job", index=True)
    lab: Mapped[str] = mapped_column(String(240), default="")
    supervisor: Mapped[str] = mapped_column(String(240), default="")
    research_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    research_url: Mapped[str] = mapped_column(Text, default="")
    research_notes: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str] = mapped_column(String(180), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    location: Mapped[str] = mapped_column(String(240), default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(140), default="")
    region: Mapped[str] = mapped_column(String(140), default="")
    remote_type: Mapped[str] = mapped_column(String(50), default="On-site")
    remote_regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    remote_countries_allowed: Mapped[list[str]] = mapped_column(JSON, default=list)
    remote_from_mexico_allowed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    remote_scope: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)
    physical_work_country_required: Mapped[str] = mapped_column(String(100), default="Unknown")
    can_work_from_mexico: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    job_requires_work_in_us: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sponsorship_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    sponsorship_evidence_text: Mapped[str] = mapped_column(Text, default="")
    sponsorship_source_url: Mapped[str] = mapped_column(Text, default="")
    sponsorship_last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    relocation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    employment_type: Mapped[str] = mapped_column(String(80), default="Internship")
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    area: Mapped[str] = mapped_column(String(100), default="Unknown", index=True)
    company_importance: Mapped[str] = mapped_column(String(50), default="Unknown", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    preferred_qualifications: Mapped[str] = mapped_column(Text, default="")
    minimum_degree_level: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    accepted_degree_levels: Mapped[list[str]] = mapped_column(JSON, default=list)
    degree_completion_required: Mapped[str] = mapped_column(
        String(40), default="UNKNOWN", index=True
    )
    currently_enrolled_allowed: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    graduation_before_start_required: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    accepted_degree_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    student_status_required: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    required_graduation_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    required_graduation_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    degree_requirement_evidence: Mapped[str] = mapped_column(Text, default="")
    special_program_type: Mapped[str] = mapped_column(String(50), default="NONE", index=True)
    special_program_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    special_program_evidence: Mapped[str] = mapped_column(Text, default="")
    apply_url: Mapped[str] = mapped_column(Text)
    posting_url: Mapped[str] = mapped_column(Text, default="")
    application_url: Mapped[str] = mapped_column(Text, default="")
    application_url_source: Mapped[str] = mapped_column(String(80), default="UNKNOWN")
    application_url_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    application_url_last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_url_diagnostic: Mapped[str] = mapped_column(String(80), default="")
    official_apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_source_url: Mapped[str] = mapped_column(Text, default="")
    discovered_from: Mapped[str] = mapped_column(String(100), default="")
    discovered_from_source: Mapped[str] = mapped_column(String(180), default="")
    verified_from_source: Mapped[str] = mapped_column(String(180), default="")
    discovery_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_confidence_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    community_sponsorship_signal: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN", index=True
    )
    community_markers: Mapped[list[str]] = mapped_column(JSON, default=list)
    company_normalized: Mapped[str] = mapped_column(String(180), default="", index=True)
    title_normalized: Mapped[str] = mapped_column(String(300), default="", index=True)
    ats_requisition_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    canonical_official_url: Mapped[str] = mapped_column(Text, default="")
    official_domain: Mapped[str] = mapped_column(String(255), default="")
    alternate_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_target_company: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    target_company_category: Mapped[str] = mapped_column(String(80), default="", index=True)
    company_priority: Mapped[str] = mapped_column(String(20), default="", index=True)
    company_priority_bonus: Mapped[float] = mapped_column(Float, default=0)
    discovery_status: Mapped[str] = mapped_column(String(40), default="discovered", index=True)
    official_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", index=True)
    verification_method: Mapped[str] = mapped_column(String(100), default="not_attempted")
    status_reason: Mapped[str] = mapped_column(Text, default="")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_failures: Mapped[int] = mapped_column(Integer, default=0)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    deadline_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deadline_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_resumes.id"), nullable=True, index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_priority_alert: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    priority_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    urgency: Mapped[str] = mapped_column(String(40), default="Recent", index=True)
    recycled_posting: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_refreshes: Mapped[int] = mapped_column(Integer, default=0)
    raw_data_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    analysis: Mapped[JobAnalysis | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    applications: Mapped[list[Application]] = relationship(back_populates="job")
    notifications: Mapped[list[Notification]] = relationship(back_populates="job")
    candidate_job_override: Mapped[CandidateJobOverride | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )

    @property
    def latest_application(self) -> Application | None:
        return max(self.applications, key=lambda item: item.id or 0, default=None)

    @property
    def is_priority_pinned(self) -> bool:
        from app.services.user_priority import is_user_priority_pinned
        return is_user_priority_pinned(self)

    @property
    def application_status(self) -> str | None:
        application = self.latest_application
        return application.status if application else None

    @property
    def submitted_resume_type(self) -> str | None:
        application = self.latest_application
        return application.resume_type if application else None

    @property
    def force_apply_now(self) -> bool:
        override = self.candidate_job_override
        return bool(
            override
            and override.owner_user_id == self.owner_user_id
            and override.force_apply_now
        )

    @property
    def force_apply_now_available(self) -> bool:
        from app.services.force_apply import force_apply_action_is_active
        return force_apply_action_is_active(self)

    @property
    def force_apply_now_permitted(self) -> bool:
        from app.services.force_apply import can_force_apply_now
        return (
            self.owner_user_id == settings.effective_primary_user_id
            and can_force_apply_now(self)
        )

    @property
    def candidate_action_recommendation(self) -> str | None:
        if self.force_apply_now_available:
            return "Apply Now"
        return self.analysis.recommendation if self.analysis else None


class JobAnalysis(Base):
    __tablename__ = "job_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    technical_score: Mapped[float] = mapped_column(Float)
    academic_score: Mapped[float] = mapped_column(Float)
    eligibility_score: Mapped[float] = mapped_column(Float)
    level_score: Mapped[float] = mapped_column(Float)
    logistics_score: Mapped[float] = mapped_column(Float)
    freshness_score: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float, index=True)
    effective_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    remote_eligibility_bonus: Mapped[float] = mapped_column(Float, default=0)
    degree_level_match: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    degree_field_match: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    degree_completion_match: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    graduation_window_match: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    student_status_match: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    education_eligibility_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    education_eligibility_reason: Mapped[str] = mapped_column(Text, default="")
    special_program_eligibility_status: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN"
    )
    special_program_eligibility_reason: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(String(50), index=True)
    eligibility_status: Mapped[str] = mapped_column(String(50))
    recommended_resume_type: Mapped[str] = mapped_column(String(100))
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    positive_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocker_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[Job] = relationship(back_populates="analysis")


class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    location: Mapped[str] = mapped_column(String(240), default="")
    linkedin_url: Mapped[str] = mapped_column(Text, default="")
    github_url: Mapped[str] = mapped_column(Text, default="")
    headline: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    education_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    projects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    coursework_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    certifications_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    languages_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    language_credentials_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Candidate-owned repository evidence. It can strengthen factual skill
    # mappings, but is intentionally separate from resume-eligible projects.
    github_evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    forbidden_claims_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KospieProfile(Base):
    __tablename__ = "kospie_profiles"

    owner_user_id: Mapped[str] = mapped_column(String(320), primary_key=True)
    program_name: Mapped[str] = mapped_column(String(180), default="KOSPIE 2027-2028")
    organization: Mapped[str] = mapped_column(
        String(240), default="DAAD + Tecnológico de Monterrey"
    )
    program_type: Mapped[str] = mapped_column(
        String(120), default="International Academic + Professional Program"
    )
    selected_universities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_interests_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ApplicationProfile(Base):
    __tablename__ = "application_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(160), default="")
    professional_email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    address_line1: Mapped[str] = mapped_column(String(240), default="")
    address_line2: Mapped[str] = mapped_column(String(240), default="")
    city: Mapped[str] = mapped_column(String(140), default="")
    state: Mapped[str] = mapped_column(String(140), default="")
    postal_code: Mapped[str] = mapped_column(String(40), default="")
    country: Mapped[str] = mapped_column(String(100), default="Mexico")
    university: Mapped[str] = mapped_column(String(240), default="")
    degree: Mapped[str] = mapped_column(String(240), default="")
    field_of_study: Mapped[str] = mapped_column(String(240), default="")
    gpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpa_scale: Mapped[float | None] = mapped_column(Float, nullable=True)
    education_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    languages_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    linkedin_url: Mapped[str] = mapped_column(Text, default="")
    github_url: Mapped[str] = mapped_column(Text, default="")
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    projects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    work_experience_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    academic_project_workaround_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    job_discovery_source: Mapped[str] = mapped_column(
        String(60), default="GOOGLE_SEARCH"
    )
    full_time_summer_availability: Mapped[bool] = mapped_column(Boolean, default=True)
    spring_summer_combined_availability: Mapped[bool] = mapped_column(Boolean, default=True)
    application_preferences_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class GeneratedResume(Base):
    __tablename__ = "generated_resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", "version", name="uq_generated_resume_version"),
        UniqueConstraint("user_id", "company_id", "version", name="uq_company_resume_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    application_type: Mapped[str] = mapped_column(String(40), default="STANDARD_JOB")
    company_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    company: Mapped[str] = mapped_column(String(180), default="")
    company_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    talent_community_url: Mapped[str] = mapped_column(Text, default="")
    target_role_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    target_role: Mapped[str] = mapped_column(String(300), default="")
    resume_target: Mapped[str] = mapped_column(String(80), default="recommended")
    tailored_content_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latex_source: Mapped[str] = mapped_column(Text, default="")
    # The final artifact is immutable with its resume version. Keeping it
    # avoids running Tectonic again for every preview or download.
    compiled_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    compiled_pdf_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_input_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    # A nullable unique value is populated only while the record is queued or
    # generating. It gives each candidate at most one active resume task.
    active_generation_owner: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    match_score: Mapped[float] = mapped_column(Float, default=0)
    keywords_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    changes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    selected_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_categories: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    job_skill_matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    skill_verification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    generation_model: Mapped[str] = mapped_column(String(120), default="")
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    job: Mapped[Job] = relationship(foreign_keys=[job_id])


class GeneratedPortfolio(Base):
    __tablename__ = "generated_portfolios"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", "version", name="uq_generated_portfolio_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    filename: Mapped[str] = mapped_column(String(320), default="Project_Portfolio.pdf")
    target_role: Mapped[str] = mapped_column(String(300), default="")
    selected_projects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    latex_source: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    job: Mapped[Job] = relationship(foreign_keys=[job_id])


class ApplicationAnswerRegistry(Base):
    __tablename__ = "application_answer_registry"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "question_key",
            name="uq_application_answer_registry_owner_question",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    question_key: Mapped[str] = mapped_column(String(100), index=True)
    normalized_question: Mapped[str] = mapped_column(Text, default="")
    answer_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    answer_type: Mapped[str] = mapped_column(String(40), default="text")
    sensitivity: Mapped[str] = mapped_column(
        String(30), default="CONFIRM_REQUIRED", index=True
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), default="user_confirmation")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CompanyPortalRegistry(Base):
    __tablename__ = "company_portal_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    known_domains_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    portal_type: Mapped[str] = mapped_column(String(40), index=True)
    application_adapter: Mapped[str] = mapped_column(String(120))
    company_specific_rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resume_behavior: Mapped[str] = mapped_column(String(80), default="JOB_SPECIFIC")
    skills_behavior: Mapped[str] = mapped_column(String(80), default="JOB_SPECIFIC_INDIVIDUAL")
    known_question_aliases_json: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    support_status: Mapped[str] = mapped_column(String(30), default="BETA", index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ApplicationSession(Base):
    __tablename__ = "application_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    application_type: Mapped[str] = mapped_column(String(40), default="STANDARD_JOB")
    company_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    talent_community_url: Mapped[str] = mapped_column(Text, default="")
    target_role_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    company: Mapped[str] = mapped_column(String(180), default="")
    portal_type: Mapped[str] = mapped_column(String(40), default="WORKDAY", index=True)
    application_url: Mapped[str] = mapped_column(Text)
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("generated_resumes.id"), index=True
    )
    resume_filename: Mapped[str] = mapped_column(String(320), default="")
    resume_download_url: Mapped[str] = mapped_column(Text, default="")
    portfolio_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_portfolios.id"), nullable=True, index=True
    )
    portfolio_filename: Mapped[str] = mapped_column(String(320), default="")
    portfolio_download_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="CREATED", index=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_step: Mapped[str] = mapped_column(String(120), default="Readiness")
    portal_job_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    confirmed_fields_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pending_questions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    application_answers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    profile_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    job_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    project_experience_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    selected_projects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_experience_text: Mapped[str] = mapped_column(Text, default="")
    selected_skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    skill_match_reasons_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    project_match_reasons_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    selection_warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    consistency_issues_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    portal_detection_evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    adapter_diagnostics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    adapter_version: Mapped[str] = mapped_column(String(40), default="")
    company_policy_key: Mapped[str] = mapped_column(String(80), default="GENERIC")
    assessment_type: Mapped[str] = mapped_column(String(60), default="")
    fields_filled_count: Mapped[int] = mapped_column(Integer, default=0)
    fields_reviewed_count: Mapped[int] = mapped_column(Integer, default=0)
    fields_confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_extension_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_page_url: Mapped[str] = mapped_column(Text, default="")
    token_nonce: Mapped[str] = mapped_column(String(64), default="", index=True)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    safe_error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    job: Mapped[Job] = relationship(foreign_keys=[job_id])
    resume_version: Mapped[GeneratedResume] = relationship(
        foreign_keys=[resume_version_id]
    )
    portfolio_version: Mapped[GeneratedPortfolio | None] = relationship(
        foreign_keys=[portfolio_version_id]
    )


class AIUserSettings(Base):
    __tablename__ = "ai_user_settings"

    owner_user_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    ai_mode: Mapped[str] = mapped_column(String(40), default="BALANCED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class UserApprovedMapping(Base):
    __tablename__ = "user_approved_mappings"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "portal", "canonical_field", "canonical_value", "portal_option",
            name="uq_user_approved_mapping",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    portal: Mapped[str] = mapped_column(String(40), default="GENERIC", index=True)
    canonical_field: Mapped[str] = mapped_column(String(100), index=True)
    canonical_value: Mapped[str] = mapped_column(Text, default="")
    portal_option: Mapped[str] = mapped_column(Text, default="")
    match_type: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    approved_by_user: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CandidateCorrectionMemory(Base):
    __tablename__ = "candidate_correction_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    scope: Mapped[str] = mapped_column(String(40), default="APPLICATION_ONLY", index=True)
    portal: Mapped[str] = mapped_column(String(40), default="")
    company: Mapped[str] = mapped_column(String(180), default="")
    canonical_field: Mapped[str] = mapped_column(String(100), index=True)
    old_value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    corrected_value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    application_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_sessions.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AIDecisionLog(Base):
    __tablename__ = "ai_decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    application_session_id: Mapped[int] = mapped_column(ForeignKey("application_sessions.id"), index=True)
    field: Mapped[str] = mapped_column(String(100), index=True)
    question_normalized: Mapped[str] = mapped_column(Text, default="")
    decision_type: Mapped[str] = mapped_column(String(60), default="MANUAL")
    provider: Mapped[str] = mapped_column(String(80), default="DETERMINISTIC")
    execution_location: Mapped[str] = mapped_column(String(30), default="LOCAL")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    selected_value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason_summary: Mapped[str] = mapped_column(Text, default="")
    user_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ExternalAIAudit(Base):
    __tablename__ = "external_ai_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    application_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_sessions.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(80), default="")
    purpose: Mapped[str] = mapped_column(String(120), default="")
    privacy_classification: Mapped[str] = mapped_column(String(40), default="NORMAL")
    fields_included_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    fields_redacted_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    application_type: Mapped[str] = mapped_column(String(40), default="STANDARD_JOB")
    company: Mapped[str] = mapped_column(String(180), default="")
    company_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    talent_community_url: Mapped[str] = mapped_column(Text, default="")
    target_role_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(60), default="Saved", index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    submitted_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_resumes.id"), nullable=True, index=True
    )
    application_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_sessions.id"), nullable=True, index=True
    )
    resume_type: Mapped[str] = mapped_column(String(100), default="General Engineering")
    application_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    job: Mapped[Job] = relationship(back_populates="applications")
    notifications: Mapped[list[Notification]] = relationship(back_populates="application")


class CandidateJobOverride(Base):
    """Candidate-owned manual action overrides for a single job.

    This table intentionally does not modify JobAnalysis. It only stores an
    explicit user decision about whether to continue to an otherwise blocked
    application.
    """

    __tablename__ = "candidate_job_overrides"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "job_id", name="uq_candidate_job_override_owner_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    force_apply_now: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    job: Mapped[Job] = relationship(back_populates="candidate_job_override")


class CompanyTalentProfile(Base):
    __tablename__ = "company_talent_profiles"

    company_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), default=primary_owner, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(180))
    company_summary: Mapped[str] = mapped_column(Text, default="")
    technical_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_role_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_project_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skill_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_url: Mapped[str] = mapped_column(Text, default="")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    talent_community_url: Mapped[str] = mapped_column(Text, default="")
    talent_community_description: Mapped[str] = mapped_column(Text, default="")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True, index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(60), index=True)
    recipient: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(60))
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[Job | None] = relationship(back_populates="notifications")
    application: Mapped[Application | None] = relationship(back_populates="notifications")


class CompanySource(Base):
    __tablename__ = "company_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    company: Mapped[str] = mapped_column(String(180), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_identifier: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text)
    registry_type: Mapped[str] = mapped_column(String(40), default="OTHER", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    base_priority: Mapped[int] = mapped_column(Integer, default=50)
    trust_level: Mapped[str] = mapped_column(String(20), default="MEDIUM", index=True)
    refresh_frequency: Mapped[str] = mapped_column(String(40), default="daily")
    supports_structured_data: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    source_confidence_score: Mapped[float] = mapped_column(Float, default=50)
    reference_only: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str] = mapped_column(String(50), default="")
    safe_error_message: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(40), default="1")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_verified: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[str] = mapped_column(String(50), default="Never")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_repository_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_parse: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_new_job_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    officially_verified_count: Mapped[int] = mapped_column(Integer, default=0)
    unverified_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    discovery_group: Mapped[str] = mapped_column(String(40), default="GENERAL", index=True)
    geography_scope: Mapped[str] = mapped_column(String(30), default="US_CANADA", index=True)
    source_domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TargetCompany(Base):
    __tablename__ = "target_companies"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "company_name", name="uq_target_company_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    careers_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(80), default="Other", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    custom: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_role_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_result_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    open_jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TargetSearchRun(Base):
    __tablename__ = "target_search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    companies_checked: Mapped[int] = mapped_column(Integer, default=0)
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_added: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_expired: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    trigger: Mapped[str] = mapped_column(String(30), default="manual")


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    search_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress_status: Mapped[str] = mapped_column(String(80), default="Starting")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    companies_checked: Mapped[int] = mapped_column(Integer, default=0)
    sources_checked: Mapped[int] = mapped_column(Integer, default=0)
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_added: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_expired: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    safe_error_summary: Mapped[str] = mapped_column(Text, default="")
    source_metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    criteria_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, default=0)
    history_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SearchRunJob(Base):
    __tablename__ = "search_run_jobs"
    __table_args__ = (
        UniqueConstraint("search_run_id", "job_id", name="uq_search_run_jobs_run_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(160), default=primary_owner, index=True
    )
    search_run_id: Mapped[int] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    discovered_during_run: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rank: Mapped[int] = mapped_column(Integer, default=0, index=True)
    technical_score_snapshot: Mapped[float] = mapped_column(Float, default=0)
    eligibility_snapshot: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
