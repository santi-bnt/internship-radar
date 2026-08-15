from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfilePayload(ORMModel):
    full_name: str
    degree: str
    university: str
    graduation_year: int
    graduation_date: date | None = None
    degree_level_current: Literal["BACHELORS", "MASTERS", "PHD", "UNKNOWN"] = "BACHELORS"
    degree_status: Literal["IN_PROGRESS", "COMPLETED", "EXPECTED_BEFORE_START", "UNKNOWN"] = "IN_PROGRESS"
    expected_graduation_date: date | None = None
    degree_field: str = "Computer Engineering"
    veteran_status: Literal["NOT_VETERAN", "VETERAN", "UNKNOWN"] = "NOT_VETERAN"
    military_status: Literal[
        "NONE", "ACTIVE_DUTY", "TRANSITIONING_SERVICE_MEMBER", "VETERAN", "UNKNOWN"
    ] = "NONE"
    military_spouse: bool = False
    disability_status: Literal["NO_DISABILITY", "HAS_DISABILITY", "UNKNOWN"] = "NO_DISABILITY"
    current_service_member: bool = False
    gpa: float
    gpa_scale: float = 100
    nationality: str
    citizenship_country: str = "Mexico"
    visas: list[str] = Field(default_factory=list)
    work_authorizations: dict[str, str] = Field(default_factory=dict)
    work_authorized_countries: list[str] = Field(default_factory=lambda: ["Mexico"])
    us_work_authorized: bool = False
    requires_us_employment_sponsorship: bool = True
    willing_to_relocate: bool = True
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education_notes: str = ""
    countries_to_search: list[str] = Field(
        default_factory=lambda: ["Mexico", "United States", "Canada"]
    )
    include_remote: bool = True
    only_remote: bool = False
    remote_from_mexico_only: bool = False
    include_hybrid: bool = True
    include_onsite: bool = True
    priority_alerts: bool = True
    priority_minimum_score: float = Field(default=80, ge=0, le=100)
    alert_for_major_companies: bool = True
    major_company_minimum_score: float = Field(default=70, ge=0, le=100)
    alert_for_deadlines: bool = True
    email_notifications: bool = False
    notification_email: str = Field(
        default_factory=lambda: settings.notification_email,
        min_length=3,
        max_length=320,
    )
    priority_email_alerts: bool = True
    major_company_email_alerts: bool = False
    deadline_alerts: bool = False
    daily_digest: bool = False
    application_follow_up_alerts: bool = False
    email_minimum_score: float = Field(default=80, ge=0, le=100)
    immediate_priority_alerts: bool = True


class ProfileRead(ProfilePayload):
    id: int
    updated_at: datetime


class AnalysisRead(ORMModel):
    id: int
    technical_score: float
    academic_score: float
    eligibility_score: float
    level_score: float
    logistics_score: float
    freshness_score: float
    overall_score: float
    effective_score: float
    remote_eligibility_bonus: float
    degree_level_match: str
    degree_field_match: str
    degree_completion_match: str
    graduation_window_match: str
    student_status_match: str
    education_eligibility_status: str
    education_eligibility_reason: str
    special_program_eligibility_status: str
    special_program_eligibility_reason: str
    recommendation: str
    eligibility_status: str
    recommended_resume_type: str
    matched_skills: list[str]
    missing_required_skills: list[str]
    positive_reasons: list[str]
    risk_flags: list[str]
    blocker_reasons: list[str]
    explanation: str
    analyzed_at: datetime


class JobRead(ORMModel):
    id: int
    external_id: str | None
    source_name: str
    source_url: str
    company: str
    title: str
    location: str
    country: str
    city: str
    region: str
    remote_type: str
    remote_regions: list[str]
    remote_countries_allowed: list[str]
    remote_from_mexico_allowed: bool
    remote_scope: str
    physical_work_country_required: str
    can_work_from_mexico: str
    job_requires_work_in_us: bool
    sponsorship_status: str
    sponsorship_evidence_text: str
    sponsorship_source_url: str
    sponsorship_last_verified_at: datetime | None
    relocation_required: bool
    employment_type: str
    duration: str | None
    area: str
    company_importance: str
    description: str
    requirements: str
    preferred_qualifications: str
    minimum_degree_level: str
    accepted_degree_levels: list[str]
    degree_completion_required: str
    currently_enrolled_allowed: str
    graduation_before_start_required: str
    accepted_degree_fields: list[str]
    student_status_required: str
    required_graduation_start: date | None
    required_graduation_end: date | None
    degree_requirement_evidence: str
    special_program_type: str
    special_program_required: bool
    special_program_evidence: str
    apply_url: str
    official_apply_url: str | None
    original_source_url: str
    discovered_from: str
    discovered_from_source: str
    verified_from_source: str
    discovery_sources: list[str]
    source_confidence_score: float
    community_sponsorship_signal: str
    community_markers: list[str]
    company_normalized: str
    title_normalized: str
    ats_requisition_id: str
    canonical_official_url: str
    official_domain: str
    alternate_sources: list[dict[str, Any]]
    is_target_company: bool
    target_company_category: str
    company_priority: str
    company_priority_bonus: float
    discovery_status: str
    official_status: str
    verification_status: str
    verification_method: str
    status_reason: str
    last_verified_at: datetime | None
    verification_failures: int
    posted_at: datetime | None
    official_posted_at: datetime | None
    source_posted_at: datetime | None
    expires_at: datetime | None
    status: Literal["active", "saved", "applied", "expired", "not_interested", "archived"]
    application_deadline: date | None
    deadline_source: str | None
    deadline_confidence: float | None
    submitted_resume_id: int | None
    submitted_resume_type: str | None = None
    application_status: str | None = None
    applied_at: datetime | None
    expired_at: datetime | None
    archived_at: datetime | None
    updated_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    is_priority_alert: bool
    priority_alerted_at: datetime | None
    urgency: str
    recycled_posting: bool
    analysis: AnalysisRead | None = None


class JobPage(BaseModel):
    items: list[JobRead]
    total: int
    page: int
    page_size: int


class JobBrief(ORMModel):
    id: int
    company: str
    title: str
    location: str
    apply_url: str


class ApplicationCreate(BaseModel):
    job_id: int
    status: str = "Saved"
    applied_at: datetime | None = None
    submitted_resume_id: int | None = None
    resume_type: str = "General Engineering"
    application_reference: str | None = None
    notes: str = ""
    next_action_at: datetime | None = None


class ApplicationUpdate(BaseModel):
    status: str | None = None
    applied_at: datetime | None = None
    submitted_resume_id: int | None = None
    resume_type: str | None = None
    application_reference: str | None = None
    notes: str | None = None
    next_action_at: datetime | None = None


class ApplicationRead(ORMModel):
    id: int
    job_id: int
    status: str
    applied_at: datetime | None
    submitted_resume_id: int | None
    resume_type: str
    application_reference: str | None
    notes: str
    next_action_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job: JobBrief


class UndoAppliedPayload(BaseModel):
    previous_status: Literal["active", "saved"] = "active"


class JobLifecycleActionRead(BaseModel):
    job: JobRead
    application: ApplicationRead | None = None
    previous_status: Literal["active", "saved"]
    message: str


class SourceCreate(BaseModel):
    company: str
    source_type: str
    source_identifier: str
    source_url: str
    enabled: bool = True
    registry_type: Literal[
        "OFFICIAL_COMPANY", "OFFICIAL_ATS", "COMMUNITY_REPO", "AGGREGATOR",
        "JOB_BOARD", "UNIVERSITY_BOARD", "OTHER",
    ] = "OTHER"
    priority: int = Field(default=50, ge=0, le=100)
    base_priority: int = Field(default=50, ge=0, le=100)
    trust_level: Literal["PRIMARY", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    refresh_frequency: str = "daily"
    supports_structured_data: bool = False
    notes: str = ""
    source_confidence_score: float = Field(default=50, ge=0, le=100)
    reference_only: bool = False


class SourceUpdate(BaseModel):
    company: str | None = None
    source_type: str | None = None
    source_identifier: str | None = None
    source_url: str | None = None
    enabled: bool | None = None
    registry_type: Literal[
        "OFFICIAL_COMPANY", "OFFICIAL_ATS", "COMMUNITY_REPO", "AGGREGATOR",
        "JOB_BOARD", "UNIVERSITY_BOARD", "OTHER",
    ] | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    base_priority: int | None = Field(default=None, ge=0, le=100)
    trust_level: Literal["PRIMARY", "HIGH", "MEDIUM", "LOW"] | None = None
    refresh_frequency: str | None = None
    supports_structured_data: bool | None = None
    notes: str | None = None
    source_confidence_score: float | None = Field(default=None, ge=0, le=100)
    reference_only: bool | None = None


class SourceRead(ORMModel):
    id: int
    company: str
    source_type: str
    source_identifier: str
    source_url: str
    registry_type: str
    priority: int
    base_priority: int
    trust_level: str
    refresh_frequency: str
    supports_structured_data: bool
    notes: str
    source_confidence_score: float
    reference_only: bool
    enabled: bool
    last_refresh_at: datetime | None
    last_status: str
    last_error: str | None
    last_successful_fetch: datetime | None
    last_repository_update: datetime | None
    last_successful_parse: datetime | None
    last_new_job_seen: datetime | None
    source_status: str
    fetched_count: int
    parsed_count: int
    new_jobs_count: int
    updated_jobs_count: int
    duplicate_count: int
    officially_verified_count: int
    unverified_count: int
    error_count: int
    duration_ms: int
    created_at: datetime


class NotificationRead(ORMModel):
    id: int
    job_id: int | None
    application_id: int | None
    notification_type: str
    recipient: str
    subject: str
    sent_at: datetime | None
    provider: str
    provider_message_id: str | None
    status: str
    error_message: str | None
    created_at: datetime


class EmailActionResult(BaseModel):
    success: bool
    message: str
    provider: str


class StatsRead(BaseModel):
    total_jobs: int
    new_jobs: int
    apply_today: int
    review: int
    needs_verification: int
    not_eligible: int
    low_match: int
    closed: int
    priority_alerts: int
    urgent: int
    applications: int
    last_update: datetime | None
    latest_search_id: int | None = None
    latest_search_status: str | None = None
    latest_search_progress: str | None = None
    latest_search_errors: str = ""


class ResumeSkillGroup(BaseModel):
    name: str
    items: list[str] = Field(default_factory=list, max_length=8)


class ResumeSkillMatch(BaseModel):
    skill: str
    category: str
    match_type: Literal["required", "preferred", "contextual"] = "contextual"
    score: int = 0
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    job_occurrences: int = 0


class ResumeSkillVerification(BaseModel):
    all_verified: bool = True
    verified: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    registry_size: int = 0


class ResumeEducationItem(BaseModel):
    institution: str
    degree: str
    location: str = ""
    graduation: str = ""
    gpa: str = ""
    coursework: list[str] = Field(default_factory=list)


class ResumeExperienceItem(BaseModel):
    title: str
    organization: str
    location: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list, max_length=3)


class ResumeProjectItem(BaseModel):
    name: str
    technologies: list[str] = Field(default_factory=list)
    status: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list, min_length=2, max_length=3)
    github_url: str | None = None
    live_url: str | None = None
    relevance_score: float = Field(default=0, ge=0, le=100)


class ResumeCourseItem(BaseModel):
    name: str
    institution: str
    issued: str = ""
    areas: list[str] = Field(default_factory=list, max_length=4)
    priority: str = "normal"


class ResumeCertificationItem(BaseModel):
    name: str
    issuer: str = ""
    date: str = ""
    url: str = ""


class ResumeChangeItem(BaseModel):
    section: str
    description: str
    reason: str


class ResumeQualityChecks(BaseModel):
    canonical_degree_name: bool = False
    no_unsupported_claims: bool = False
    no_artificial_language: bool = False
    ats_text_clean: bool = False
    one_page: bool = False


class ModelTailoringOutput(BaseModel):
    classification: str
    headline: str
    summary: str
    skill_categories: list[ResumeSkillGroup] = Field(default_factory=list, max_length=4)
    projects: list[ResumeProjectItem] = Field(default_factory=list, max_length=4)
    keywords_used: list[str] = Field(default_factory=list)
    keywords_missing: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TailoredResumeContent(BaseModel):
    target_role: str
    classification: str
    headline: str
    summary: str
    skill_categories: list[ResumeSkillGroup] = Field(default_factory=list, max_length=4)
    selected_skills: list[str] = Field(default_factory=list, max_length=16)
    job_skill_matches: list[ResumeSkillMatch] = Field(default_factory=list, max_length=16)
    skill_verification: ResumeSkillVerification = Field(default_factory=ResumeSkillVerification)
    education: ResumeEducationItem
    experience: list[ResumeExperienceItem] = Field(default_factory=list)
    projects: list[ResumeProjectItem] = Field(default_factory=list, max_length=4)
    coursework: list[ResumeCourseItem] = Field(default_factory=list, max_length=2)
    certifications: list[ResumeCertificationItem] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    quality_checks: ResumeQualityChecks = Field(default_factory=ResumeQualityChecks)
    match_score: float = Field(ge=0, le=100)
    keywords_used: list[str] = Field(default_factory=list)
    keywords_missing: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    changes: list[ResumeChangeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResumeProfilePayload(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    headline: str = ""
    summary: str = ""
    education_json: list[dict[str, Any]] = Field(default_factory=list)
    skills_json: list[str] = Field(default_factory=list)
    experience_json: list[dict[str, Any]] = Field(default_factory=list)
    projects_json: list[dict[str, Any]] = Field(default_factory=list)
    coursework_json: list[Any] = Field(default_factory=list)
    certifications_json: list[dict[str, Any]] = Field(default_factory=list)
    languages_json: list[str] = Field(default_factory=list)
    forbidden_claims_json: list[str] = Field(default_factory=list)


class ResumeProfileRead(ResumeProfilePayload):
    id: int
    user_id: str
    created_at: datetime


class VerifiedSkillRead(BaseModel):
    skill: str
    category: str
    evidence: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)


class VerifiedSkillGroupRead(BaseModel):
    name: str
    items: list[VerifiedSkillRead] = Field(default_factory=list)


class TargetCompanyPayload(BaseModel):
    company_name: str = Field(min_length=1, max_length=180)
    aliases: list[str] = Field(default_factory=list)
    careers_domains: list[str] = Field(default_factory=list)
    category: str = "Other"
    priority: Literal["high", "medium", "low"] = "medium"
    enabled: bool = True
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_role_categories: list[str] = Field(default_factory=list)


class TargetCompanyUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=180)
    aliases: list[str] | None = None
    careers_domains: list[str] | None = None
    category: str | None = None
    priority: Literal["high", "medium", "low"] | None = None
    enabled: bool | None = None
    preferred_locations: list[str] | None = None
    preferred_role_categories: list[str] | None = None


class TargetCompanyRead(TargetCompanyPayload, ORMModel):
    id: int
    custom: bool
    last_checked_at: datetime | None
    last_successful_result_at: datetime | None
    open_jobs_count: int
    created_at: datetime
    updated_at: datetime


class TargetSearchRunRead(ORMModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    companies_checked: int
    jobs_discovered: int
    jobs_added: int
    jobs_updated: int
    jobs_expired: int
    errors: list[dict[str, Any]]
    trigger: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SearchRunRead(ORMModel):
    id: int
    search_type: str
    status: str
    progress_status: str
    started_at: datetime
    completed_at: datetime | None
    companies_checked: int
    sources_checked: int
    jobs_discovered: int
    jobs_added: int
    jobs_updated: int
    jobs_expired: int
    error_count: int
    safe_error_summary: str
    source_metrics: list[dict[str, Any]]
    trigger: str
    created_at: datetime


class GeneratedResumeRead(BaseModel):
    id: int
    job_id: int
    version: int
    status: str
    target_role: str
    tailored_content_json: dict[str, Any]
    latex_source: str
    match_score: float
    keywords_json: dict[str, Any]
    changes_json: list[dict[str, Any]]
    warnings_json: list[str]
    selected_skills: list[str]
    skill_categories: list[dict[str, Any]]
    job_skill_matches: list[dict[str, Any]]
    skill_verification: dict[str, Any]
    generation_model: str
    generation_error: str | None
    created_at: datetime
    updated_at: datetime
    pdf_url: str | None = None
    tex_url: str

    model_config = ConfigDict(from_attributes=True)
