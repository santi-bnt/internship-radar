from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfilePayload(ORMModel):
    full_name: str
    display_name: str = ""
    degree: str
    university: str
    graduation_year: int
    graduation_date: date | None = None
    degree_level_current: Literal["BACHELORS", "MASTERS", "PHD", "UNKNOWN"] = "BACHELORS"
    degree_status: Literal["IN_PROGRESS", "COMPLETED", "EXPECTED_BEFORE_START", "UNKNOWN"] = "IN_PROGRESS"
    expected_graduation_date: date | None = None
    degree_field: str = "Robotics and Digital Systems Engineering"
    veteran_status: Literal["NOT_VETERAN", "VETERAN", "UNKNOWN"] = "NOT_VETERAN"
    military_status: Literal[
        "NONE", "ACTIVE_DUTY", "TRANSITIONING_SERVICE_MEMBER", "VETERAN", "UNKNOWN"
    ] = "NONE"
    military_spouse: bool = False
    disability_status: Literal["NO_DISABILITY", "HAS_DISABILITY", "UNKNOWN"] = "NO_DISABILITY"
    current_service_member: bool = False
    gpa: float
    gpa_scale: float | None = None
    gpa_scale_status: str = "CONFIRMED"
    current_semester: int | None = None
    official_degree_name: str | None = None
    official_degree_name_status: str = "CONFIRMED"
    nationality: str
    citizenship_country: str = "Mexico"
    citizenship_status: str = "CONFIRMED"
    visas: list[str] = Field(default_factory=list)
    work_authorizations: dict[str, str] = Field(default_factory=dict)
    work_authorized_countries: list[str] = Field(default_factory=lambda: ["Mexico"])
    us_work_authorized: bool = False
    requires_us_employment_sponsorship: bool = True
    us_authorization_conflict_detected: bool = False
    work_authorization_raw_statement: str = ""
    willing_to_relocate: bool = True
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    minimum_hours_per_week: int | None = Field(default=None, ge=0, le=168)
    github_url: str = ""
    linkedin_url: str = ""
    onboarding_status: str = "PROFILE_READY"
    profile_warnings: list[str] = Field(default_factory=list)
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
    opportunity_type: str = "job"
    lab: str = ""
    supervisor: str = ""
    research_areas: list[str] = Field(default_factory=list)
    research_url: str = ""
    research_notes: str = ""
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
    posting_url: str
    application_url: str
    application_url_source: str
    application_url_status: str
    application_url_last_verified_at: datetime | None
    application_url_diagnostic: str
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
    force_apply_now: bool = False
    force_apply_now_available: bool = False
    force_apply_now_permitted: bool = False
    candidate_action_recommendation: str | None = None
    applied_at: datetime | None
    expired_at: datetime | None
    archived_at: datetime | None
    updated_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    is_priority_alert: bool
    is_priority_pinned: bool = False
    priority_alerted_at: datetime | None
    urgency: str
    recycled_posting: bool
    analysis: AnalysisRead | None = None


class JobURLImportRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    force_apply_now: bool = False


class JobURLImportResponse(BaseModel):
    job_id: int
    created: bool
    existing_job_reused: bool
    verified: bool
    official_status: str
    candidate_analysis_created: bool
    force_apply_now: bool
    force_apply_error: str | None = None


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
    application_session_id: int | None = None


class ApplicationUpdate(BaseModel):
    status: str | None = None
    applied_at: datetime | None = None
    submitted_resume_id: int | None = None
    resume_type: str | None = None
    application_reference: str | None = None
    notes: str | None = None
    next_action_at: datetime | None = None
    application_session_id: int | None = None


class ApplicationRead(ORMModel):
    id: int
    job_id: int | None
    application_type: str = "STANDARD_JOB"
    company: str = ""
    company_id: str | None = None
    talent_community_url: str = ""
    status: str
    applied_at: datetime | None
    status_history: list[dict[str, Any]] = []
    submitted_resume_id: int | None
    application_session_id: int | None
    resume_type: str
    application_reference: str | None
    notes: str
    next_action_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job: JobBrief | None


FieldPolicy = Literal[
    "AUTO_FILL",
    "AUTO_FILL_REVIEW_REQUIRED",
    "REVIEW_RECOMMENDED",
    "CONFIRM_REQUIRED",
    "MANUAL_ONLY",
]
PortalType = Literal[
    "WORKDAY", "GREENHOUSE", "MICROSOFT_CAREERS", "AMAZON_JOBS", "ORACLE_CAREERS",
    "LEVER", "ASHBY", "SMARTRECRUITERS", "GOOGLE_CAREERS", "GENERIC", "UNKNOWN",
]
PortalSupportStatus = Literal["SUPPORTED", "BETA", "UNSUPPORTED", "PORTAL_CHANGED"]
ApplicationSessionStatus = Literal[
    "CREATED",
    "OPENED",
    "IN_PROGRESS",
    "WAITING_FOR_USER",
    "READY_FOR_REVIEW",
    "SUBMITTED_BY_USER",
    "ABANDONED",
    "ERROR",
]


class ApplicationProfilePayload(BaseModel):
    full_name: str = ""
    professional_email: str = ""
    phone: str = ""
    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "Mexico"
    university: str = ""
    degree: str = ""
    field_of_study: str = ""
    gpa: float | None = None
    gpa_scale: float | None = None
    education_start_date: date | None = None
    expected_graduation_date: date | None = None
    languages_json: list[str] = Field(default_factory=list)
    linkedin_url: str = ""
    github_url: str = ""
    skills_json: list[str] = Field(default_factory=list)
    projects_json: list[dict[str, Any]] = Field(default_factory=list)
    work_experience_json: list[dict[str, Any]] = Field(default_factory=list)
    academic_project_workaround_allowed: bool = False
    job_discovery_source: str = "GOOGLE_SEARCH"
    full_time_summer_availability: bool = True
    spring_summer_combined_availability: bool = True
    application_preferences_confirmed_at: datetime | None = None

    @field_validator(
        "full_name", "professional_email", "phone", "address_line1", "address_line2",
        "city", "state", "postal_code", "country", "university", "degree",
        "field_of_study", "linkedin_url", "github_url", mode="before",
    )
    @classmethod
    def normalize_profile_text(cls, value: object) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("professional_email")
    @classmethod
    def validate_professional_email(cls, value: str) -> str:
        if value and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("Enter a valid professional email address.")
        return value.lower()


class ApplicationProfileRead(ApplicationProfilePayload, ORMModel):
    id: int
    owner_user_id: str
    created_at: datetime
    updated_at: datetime


class ReadinessCheck(BaseModel):
    key: str
    label: str
    ready: bool


class ApplicationReadinessRead(BaseModel):
    ready: bool
    hard_blocked: bool
    blocker_reason: str
    portal_type: str
    portal_job_id: str
    support_status: PortalSupportStatus
    company_policy_key: str
    detection_evidence: list[str]
    checks: list[ReadinessCheck]
    sensitive_confirmation_notice: str
    resume: dict[str, Any] | None = None
    portfolio: dict[str, Any] | None = None
    selected_experience: list[dict[str, Any]] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    generated_experience_text: str = ""
    project_match_reasons: dict[str, str] = Field(default_factory=dict)
    skill_match_reasons: dict[str, str] = Field(default_factory=dict)
    selection_warnings: list[str] = Field(default_factory=list)


class ApplicationSessionCreate(BaseModel):
    resume_version_id: int | None = None
    portfolio_version_id: int | None = None
    allow_ineligible_override: bool = False
    selected_project_names: list[str] | None = Field(default=None, max_length=3)
    selected_skills: list[str] | None = Field(default=None, max_length=20)


class ApplicationSessionProgress(BaseModel):
    status: ApplicationSessionStatus | None = None
    current_step: str | None = Field(default=None, max_length=120)
    portal_job_id: str | None = Field(default=None, max_length=255)
    confirmed_fields_json: dict[str, Any] | None = None
    pending_questions_json: list[dict[str, Any]] | None = None
    application_answers_json: dict[str, Any] | None = None
    fields_filled_count: int | None = Field(default=None, ge=0, le=1000)
    fields_reviewed_count: int | None = Field(default=None, ge=0, le=1000)
    fields_confirmed_count: int | None = Field(default=None, ge=0, le=1000)
    last_page_url: str | None = Field(default=None, max_length=3000)
    observed_fields: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=80)
    safe_error_message: str | None = Field(default=None, max_length=1000)
    portal_type: PortalType | None = None
    portal_detection_evidence_json: list[str] | None = None
    adapter_diagnostics_json: dict[str, Any] | None = None
    adapter_version: str | None = Field(default=None, max_length=40)
    company_policy_key: str | None = Field(default=None, max_length=80)
    assessment_type: str | None = Field(default=None, max_length=60)


class ApplicationSessionRead(ORMModel):
    id: int
    job_id: int | None
    application_type: str = "STANDARD_JOB"
    company_id: str | None = None
    company: str
    portal_type: str
    application_url: str
    resume_version_id: int
    resume_filename: str
    resume_download_url: str
    portfolio_version_id: int | None
    portfolio_filename: str
    portfolio_download_url: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    current_step: str
    portal_job_id: str
    confirmed_fields_json: dict[str, Any]
    pending_questions_json: list[dict[str, Any]]
    application_answers_json: dict[str, Any]
    profile_snapshot_json: dict[str, Any]
    job_snapshot_json: dict[str, Any]
    project_experience_json: list[dict[str, Any]]
    selected_projects_json: list[dict[str, Any]]
    generated_experience_text: str
    selected_skills_json: list[str]
    skill_match_reasons_json: dict[str, Any]
    project_match_reasons_json: dict[str, Any]
    selection_warnings_json: list[str]
    consistency_issues_json: list[dict[str, Any]]
    portal_detection_evidence_json: list[str]
    adapter_diagnostics_json: dict[str, Any]
    adapter_version: str
    company_policy_key: str
    assessment_type: str
    fields_filled_count: int
    fields_reviewed_count: int
    fields_confirmed_count: int
    last_extension_seen_at: datetime | None
    last_page_url: str
    error_code: str
    safe_error_message: str


class ApplicationSessionLaunch(BaseModel):
    session: ApplicationSessionRead
    application_session_token: str
    token_expires_at: datetime
    extension_message_origin: str


class ApplicationAnswerConfirmation(BaseModel):
    question_key: str = Field(min_length=2, max_length=100)
    normalized_question: str = Field(min_length=2, max_length=2000)
    answer: Any
    answer_type: str = Field(default="text", max_length=40)
    classification_confidence: float = Field(default=1.0, ge=0, le=1)


class ApplicationAnswerRead(ORMModel):
    id: int
    question_key: str
    normalized_question: str
    answer_json: dict[str, Any]
    answer_type: str
    sensitivity: str
    last_confirmed_at: datetime | None
    source: str
    notes: str


class AISettingsPayload(BaseModel):
    ai_mode: Literal["LOCAL_ONLY", "BALANCED", "EXTERNAL_ALLOWED"] = "BALANCED"


class AISettingsRead(AISettingsPayload, ORMModel):
    owner_user_id: str
    updated_at: datetime


class ExtensionApplicationPayload(BaseModel):
    session: ApplicationSessionRead
    profile: dict[str, Any]
    resume: dict[str, Any]
    portfolio: dict[str, Any] | None = None
    answer_suggestions: list[ApplicationAnswerRead]
    field_policies: tuple[str, ...]
    sensitive_question_keys: list[str]
    company_policy: dict[str, Any]
    adapter_status: PortalSupportStatus
    ai_settings: AISettingsRead
    final_submit_policy: Literal["MANUAL_ONLY"] = "MANUAL_ONLY"


class AgentFieldInput(BaseModel):
    field_id: str = Field(min_length=1, max_length=240)
    raw_label: str = Field(default="", max_length=2000)
    nearby_text: str = Field(default="", max_length=4000)
    control_type: str = Field(default="text", max_length=80)
    available_options: list[str] = Field(default_factory=list, max_length=250)
    current_value: Any = None
    required: bool = False
    maxlength: int | None = Field(default=None, ge=1, le=10000)


class ApplicationAgentRequest(BaseModel):
    page_url: str = Field(default="", max_length=3000)
    page_title: str = Field(default="", max_length=500)
    fields: list[AgentFieldInput] = Field(default_factory=list, max_length=250)


class FieldResolution(BaseModel):
    field_id: str
    canonical_field: str
    question_category: Literal[
        "PROFILE_FACT", "DERIVED_PROFILE_FACT", "JOB_SPECIFIC_TEXT",
        "EXPERIENCE_QUESTION", "SKILL_QUESTION", "EDUCATION_MAPPING",
        "WORK_AUTHORIZATION", "LEGAL_COMPLIANCE", "VOLUNTARY_DISCLOSURE",
        "ASSESSMENT", "ELECTRONIC_ATTESTATION", "UNKNOWN",
    ]
    action: Literal[
        "AUTO_FILL", "AUTO_FILL_REVIEW", "GENERATE_REVIEW", "CONFIRM", "MANUAL_ONLY"
    ]
    selected_value: Any = None
    selected_option: str | None = None
    confidence: float = Field(ge=0, le=1)
    match_type: Literal[
        "EXACT", "STRONG_EQUIVALENT", "RELATED_PROGRAMMING",
        "RELATED_ENGINEERING", "OTHER", "UNKNOWN",
    ] = "UNKNOWN"
    reason_summary: str = Field(max_length=1000)
    requires_review: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    privacy_level: Literal[
        "PUBLIC", "NORMAL", "PERSONAL", "SENSITIVE", "HIGHLY_SENSITIVE", "NEVER_AI"
    ] = "NORMAL"
    provider: str = "DETERMINISTIC"
    execution_location: Literal["LOCAL", "EXTERNAL"] = "LOCAL"


class ApplicationAgentResponse(BaseModel):
    status: Literal["PLAN_READY", "WAITING_FOR_USER", "READY_FOR_REVIEW"]
    resolutions: list[FieldResolution]
    local_ai_available: bool | None = None
    external_calls: int = 0
    fields_redacted: list[str] = Field(default_factory=list)
    final_submit_policy: Literal["MANUAL_ONLY"] = "MANUAL_ONLY"


class TextAnswer(BaseModel):
    answer: str = Field(max_length=10000)
    confidence: float = Field(ge=0, le=1)
    evidence_project_ids: list[str] = Field(default_factory=list)
    evidence_skill_ids: list[str] = Field(default_factory=list)
    character_count: int = Field(ge=0)
    requires_review: Literal[True] = True


class UserApprovedMappingPayload(BaseModel):
    portal: str = Field(default="GENERIC", max_length=40)
    canonical_field: str = Field(min_length=2, max_length=100)
    canonical_value: str = Field(min_length=1, max_length=500)
    portal_option: str = Field(min_length=1, max_length=500)
    match_type: Literal[
        "EXACT", "STRONG_EQUIVALENT", "RELATED_PROGRAMMING",
        "RELATED_ENGINEERING", "OTHER", "UNKNOWN",
    ]


class UserApprovedMappingRead(UserApprovedMappingPayload, ORMModel):
    id: int
    approved_by_user: bool
    approved_at: datetime


class CandidateCorrectionPayload(BaseModel):
    scope: Literal["USER_GLOBAL", "PORTAL", "COMPANY", "QUESTION_ALIAS", "APPLICATION_ONLY"]
    portal: str = Field(default="", max_length=40)
    company: str = Field(default="", max_length=180)
    canonical_field: str = Field(min_length=2, max_length=100)
    old_value: Any = None
    corrected_value: Any
    application_session_id: int | None = None


class CandidateCorrectionRead(ORMModel):
    id: int
    scope: str
    portal: str
    company: str
    canonical_field: str
    old_value_json: dict[str, Any]
    corrected_value_json: dict[str, Any]
    verified: bool
    application_session_id: int | None
    created_at: datetime


class ExternalAIAuditRead(ORMModel):
    id: int
    provider: str
    purpose: str
    privacy_classification: str
    fields_included_json: list[str]
    fields_redacted_json: list[str]
    created_at: datetime


class ApplicationSubmittedConfirmation(BaseModel):
    confirmation_text: str = Field(min_length=3, max_length=1000)
    confirmation_url: str = Field(default="", max_length=3000)


class ApplicationSessionRevokeResult(BaseModel):
    session_id: int
    status: str
    token_revoked: bool


class UndoAppliedPayload(BaseModel):
    # Kept for older clients; the persisted transition is authoritative.
    previous_status: Literal["active", "saved"] | None = None


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
    discovery_group: str = "GENERAL"
    geography_scope: str = "US_CANADA"


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
    discovery_group: str | None = None
    geography_scope: str | None = None


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
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_type: str
    safe_error_message: str
    http_status: int | None
    parser_version: str
    consecutive_failures: int
    jobs_discovered: int
    jobs_verified: int
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
    discovery_group: str
    geography_scope: str
    source_domain: str
    next_run_at: datetime | None
    backoff_until: datetime | None
    rate_limited_until: datetime | None
    retry_after_seconds: int | None
    discovery_checkpoint_json: dict[str, Any]
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
    match_kind: Literal["EXACT", "ALIAS", "SEMANTIC_SUPPORTED", "PARTIAL", "NOT_FOUND"] = "PARTIAL"
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
    project_type_label: str = ""
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
    within_two_pages: bool = False


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
    application_type: str = "STANDARD_JOB"
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
    projects: list[ResumeProjectItem] = Field(default_factory=list, max_length=5)
    coursework: list[ResumeCourseItem] = Field(default_factory=list, max_length=8)
    certifications: list[ResumeCertificationItem] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list, max_length=5)
    opportunity_research_areas: list[str] = Field(default_factory=list)
    additional_information: list[str] = Field(default_factory=list)
    language_verification: list[dict[str, Any]] = Field(default_factory=list)
    program_eligibility: list[dict[str, Any]] = Field(default_factory=list)
    why_this_version: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    quality_checks: ResumeQualityChecks = Field(default_factory=ResumeQualityChecks)
    match_score: float = Field(ge=0, le=100)
    keywords_used: list[str] = Field(default_factory=list)
    keywords_missing: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    changes: list[ResumeChangeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Snapshot of the evidence-only plan that produced this immutable resume.
    tailoring_plan: dict[str, Any] = Field(default_factory=dict)
    # Compact developer trace used by the existing recommendation UI.
    tailoring_trace: dict[str, Any] = Field(default_factory=dict)


class LanguageCredentialItem(BaseModel):
    language: str = ""
    proficiency: str = ""
    certificate: str = ""
    score: str = ""
    verified: bool = False


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
    language_credentials_json: list[LanguageCredentialItem] = Field(default_factory=list)
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


CompanySearchName = str
WorkModel = Literal["ANY", "REMOTE", "HYBRID", "ON_SITE"]
RemoteSearchScope = Literal["MEXICO", "LATAM", "GLOBAL", "US_ONLY", "UNKNOWN"]
RoleCategory = Literal[
    "SOFTWARE_ENGINEERING",
    "EMBEDDED_FIRMWARE",
    "ROBOTICS",
    "AI_MACHINE_LEARNING",
    "COMPUTER_VISION",
    "BACKEND",
    "FULL_STACK",
    "FPGA_DIGITAL_DESIGN",
    "HARDWARE_VALIDATION",
    "ELECTRICAL_VALIDATION",
    "DATA_ALGORITHMS",
    "RESEARCH_ENGINEERING",
    "OTHER",
]
SourceMode = Literal["ALL_SOURCES", "OFFICIAL_ONLY", "OFFICIAL_AND_COMMUNITY"]


class SearchCriteria(BaseModel):
    companies: list[CompanySearchName] = Field(default_factory=list, max_length=20)
    target_companies_only: bool = False
    work_models: list[WorkModel] = Field(default_factory=lambda: ["ANY"], max_length=4)
    remote_scopes: list[RemoteSearchScope] = Field(
        default_factory=lambda: ["MEXICO", "LATAM", "GLOBAL"],
        max_length=5,
    )
    countries: list[str] = Field(default_factory=list, max_length=10)
    states: list[str] = Field(default_factory=list, max_length=10)
    cities: list[str] = Field(default_factory=list, max_length=15)
    role_categories: list[RoleCategory] = Field(default_factory=list, max_length=12)
    include_keywords: list[str] = Field(default_factory=list, max_length=20)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=20)
    only_realistically_eligible: bool = True
    include_unknown_eligibility: bool = True
    source_mode: SourceMode = "OFFICIAL_AND_COMMUNITY"
    posted_within_days: Literal[1, 3, 7, 14, 30] | None = 14
    limit: Literal[25, 50, 100] = 50

    @field_validator(
        "companies",
        "countries",
        "states",
        "cities",
        "include_keywords",
        "exclude_keywords",
        mode="before",
    )
    @classmethod
    def clean_text_lists(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            item = " ".join(str(raw).strip().split())
            key = item.casefold()
            if not item or key in seen:
                continue
            if len(item) > 100:
                raise ValueError("Search values must be 100 characters or fewer.")
            seen.add(key)
            cleaned.append(item)
        return cleaned

    @field_validator("work_models", "remote_scopes", "role_categories", mode="before")
    @classmethod
    def unique_enum_lists(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return list(dict.fromkeys(str(item).strip().upper() for item in value if str(item).strip()))

    @model_validator(mode="after")
    def normalize_dependent_fields(self) -> "SearchCriteria":
        if not self.work_models:
            self.work_models = ["ANY"]
        if "ANY" in self.work_models:
            self.work_models = ["ANY"]
        if "REMOTE" not in self.work_models and self.work_models != ["ANY"]:
            self.remote_scopes = []
        if set(item.casefold() for item in self.include_keywords) & set(
            item.casefold() for item in self.exclude_keywords
        ):
            raise ValueError("A keyword cannot be both included and excluded.")
        return self


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
    criteria_json: dict[str, Any]
    progress_json: dict[str, Any]
    result_count: int
    eligible_count: int
    verified_count: int
    trigger: str
    created_at: datetime


class SearchRunDeleteResult(BaseModel):
    id: int
    deleted_from_history: bool


class GeneratedResumeRead(BaseModel):
    id: int
    job_id: int | None
    application_type: str = "STANDARD_JOB"
    company: str = ""
    company_id: str | None = None
    company_profile: dict[str, Any] = Field(default_factory=dict)
    target_role_categories: list[str] = Field(default_factory=list)
    version: int
    status: str
    target_role: str
    resume_target: str = "recommended"
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
    source_input_hash: str = ""
    created_at: datetime
    updated_at: datetime
    pdf_url: str | None = None
    tex_url: str
    is_stale: bool = False

    model_config = ConfigDict(from_attributes=True)


class ResumeGenerateRequest(BaseModel):
    resume_target: Literal["recommended", "software_engineering", "embedded_firmware", "electrical_validation", "hardware_engineering", "robotics_research", "kospie_germany"] = "recommended"
    regenerate: bool = False


KOSPIE_INTERESTS = {
    "Robotics", "Embedded Systems", "Control", "Automation", "Computer Vision", "Digital Systems",
}


class KospieProfilePayload(BaseModel):
    selected_universities_json: list[str] = Field(min_length=3, max_length=3)
    primary_interests_json: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("selected_universities_json")
    @classmethod
    def validate_universities(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(item.split()) for item in value]
        if any(not item for item in cleaned) or len({item.casefold() for item in cleaned}) != 3:
            raise ValueError("Select exactly three distinct German universities.")
        return cleaned

    @field_validator("primary_interests_json")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(" ".join(item.split()) for item in value if item.strip()))
        unsupported = [item for item in cleaned if item not in KOSPIE_INTERESTS]
        if unsupported:
            raise ValueError(f"Unsupported engineering interests: {', '.join(unsupported)}")
        return cleaned


class KospieProfileRead(KospieProfilePayload, ORMModel):
    owner_user_id: str
    program_name: str
    organization: str
    program_type: str
    created_at: datetime
    updated_at: datetime


class KospieAnalysisRead(BaseModel):
    academic_strengths: list[str] = Field(default_factory=list)
    technical_strengths: list[str] = Field(default_factory=list)
    recommended_projects: list[dict[str, Any]] = Field(default_factory=list)
    recommended_skills: list[str] = Field(default_factory=list)
    recommended_coursework: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    language_status: list[dict[str, Any]] = Field(default_factory=list)
    eligibility: list[dict[str, Any]] = Field(default_factory=list)
    selected_universities: list[str] = Field(min_length=3, max_length=3)
    primary_interests: list[str] = Field(default_factory=list)


class ResearchOpportunityCreate(BaseModel):
    organization: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=300)
    lab: str = Field(default="", max_length=240)
    professor: str = Field(default="", max_length=240)
    research_areas: list[str] = Field(default_factory=list, max_length=12)
    description: str = Field(default="", max_length=12000)
    url: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)


class ManualJobCreate(BaseModel):
    company: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=300)
    location: str = Field(default="", max_length=240)
    category: str = Field(default="", max_length=100)
    apply_url: str = Field(min_length=10, max_length=2048)
    description: str = Field(default="", max_length=12000)
    requirements: str = Field(default="", max_length=12000)
    preferred_qualifications: str = Field(default="", max_length=12000)
    source_url: str = Field(default="", max_length=2048)
    force_apply_now: bool = False


class ResearchOpportunityAnalysisRead(BaseModel):
    research_focus: list[str] = Field(default_factory=list)
    verified_matches: list[str] = Field(default_factory=list)
    unverified_keywords: list[str] = Field(default_factory=list)
    recommended_projects: list[dict[str, Any]] = Field(default_factory=list)
    recommended_skills: dict[str, list[str]] = Field(default_factory=dict)
    research_interests: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=100)
    similarity: float = Field(ge=0, le=100)
    similar_resume_id: int | None = None
    reuse_message: str = ""
