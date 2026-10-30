export type Recommendation =
  | "Apply Now"
  | "Apply Today"
  | "Review"
  | "Needs Verification"
  | "Not Eligible"
  | "Low Match"
  | "Closed"
  | "Expired";

export type EligibilityState = "ELIGIBLE" | "LIKELY_ELIGIBLE" | "UNKNOWN" | "LIKELY_INELIGIBLE" | "NOT_ELIGIBLE";
export type RemoteScope = "GLOBAL" | "LATAM" | "MEXICO" | "COUNTRY_LIST" | "US_ONLY" | "COUNTRY_RESTRICTED" | "UNKNOWN" | "NOT_REMOTE";
export type SponsorshipStatus = "AVAILABLE" | "NOT_AVAILABLE" | "NOT_REQUIRED" | "UNKNOWN";

export interface Analysis {
  id: number;
  technical_score: number;
  academic_score: number;
  eligibility_score: number;
  level_score: number;
  logistics_score: number;
  freshness_score: number;
  overall_score: number;
  effective_score: number;
  remote_eligibility_bonus: number;
  degree_level_match: "MATCH" | "NO_MATCH" | "UNKNOWN";
  degree_field_match: "MATCH" | "NO_MATCH" | "UNKNOWN";
  degree_completion_match: "MATCH" | "NO_MATCH" | "UNKNOWN";
  graduation_window_match: "MATCH" | "NO_MATCH" | "UNKNOWN";
  student_status_match: "MATCH" | "NO_MATCH" | "UNKNOWN";
  education_eligibility_status: EligibilityState;
  education_eligibility_reason: string;
  special_program_eligibility_status: EligibilityState;
  special_program_eligibility_reason: string;
  recommendation: Recommendation;
  eligibility_status: EligibilityState;
  recommended_resume_type: string;
  matched_skills: string[];
  missing_required_skills: string[];
  positive_reasons: string[];
  risk_flags: string[];
  blocker_reasons: string[];
  explanation: string;
  analyzed_at: string;
}

export interface Job {
  id: number;
  external_id: string | null;
  source_name: string;
  source_url: string;
  opportunity_type: string;
  lab: string;
  supervisor: string;
  research_areas: string[];
  research_url: string;
  research_notes: string;
  company: string;
  title: string;
  location: string;
  country: string;
  city: string;
  region: string;
  remote_type: string;
  remote_regions: string[];
  remote_countries_allowed: string[];
  remote_from_mexico_allowed: boolean;
  remote_scope: RemoteScope;
  physical_work_country_required: string;
  can_work_from_mexico: "YES" | "NO" | "UNKNOWN";
  job_requires_work_in_us: boolean;
  sponsorship_status: SponsorshipStatus;
  sponsorship_evidence_text: string;
  sponsorship_source_url: string;
  sponsorship_last_verified_at: string | null;
  relocation_required: boolean;
  employment_type: string;
  duration: string | null;
  area: string;
  company_importance: string;
  description: string;
  requirements: string;
  preferred_qualifications: string;
  minimum_degree_level: "BACHELORS" | "MASTERS" | "PHD" | "UNKNOWN";
  accepted_degree_levels: string[];
  degree_completion_required: "COMPLETED_REQUIRED" | "IN_PROGRESS_ALLOWED" | "COMPLETED_OR_IN_PROGRESS" | "UNKNOWN";
  currently_enrolled_allowed: "YES" | "NO" | "UNKNOWN";
  graduation_before_start_required: "YES" | "NO" | "UNKNOWN";
  accepted_degree_fields: string[];
  student_status_required: "REQUIRED" | "NOT_REQUIRED" | "UNKNOWN";
  required_graduation_start: string | null;
  required_graduation_end: string | null;
  degree_requirement_evidence: string;
  special_program_type: "NONE" | "VETERANS" | "ACTIVE_DUTY_MILITARY" | "TRANSITIONING_SERVICE_MEMBERS" | "MILITARY_SPOUSES" | "PEOPLE_WITH_DISABILITIES" | "RETURN_TO_WORK_PROGRAM" | "FORMER_EMPLOYEES" | "SPECIFIC_ACADEMIC_COHORT" | "OTHER_RESTRICTED_GROUP";
  special_program_required: boolean;
  special_program_evidence: string;
  apply_url: string;
  posting_url: string;
  application_url: string;
  application_url_source: string;
  application_url_status: string;
  application_url_last_verified_at: string | null;
  application_url_diagnostic: string;
  official_apply_url: string | null;
  original_source_url: string;
  discovered_from: string;
  discovered_from_source: string;
  verified_from_source: string;
  discovery_sources: string[];
  source_confidence_score: number;
  community_sponsorship_signal: "LIKELY_AVAILABLE" | "LIKELY_UNAVAILABLE" | "UNKNOWN";
  community_markers: string[];
  company_normalized: string;
  title_normalized: string;
  ats_requisition_id: string;
  canonical_official_url: string;
  official_domain: string;
  alternate_sources: Array<Record<string, unknown>>;
  is_target_company: boolean;
  target_company_category: string;
  company_priority: string;
  company_priority_bonus: number;
  discovery_status: string;
  official_status: string;
  verification_status: string;
  verification_method: string;
  status_reason: string;
  last_verified_at: string | null;
  verification_failures: number;
  posted_at: string | null;
  official_posted_at: string | null;
  source_posted_at: string | null;
  expires_at: string | null;
  status: "active" | "saved" | "applied" | "expired" | "not_interested" | "archived";
  application_deadline: string | null;
  deadline_source: string | null;
  deadline_confidence: number | null;
  submitted_resume_id: number | null;
  submitted_resume_type: string | null;
  application_status: string | null;
  force_apply_now: boolean;
  force_apply_now_available: boolean;
  force_apply_now_permitted: boolean;
  candidate_action_recommendation: Recommendation | null;
  applied_at: string | null;
  expired_at: string | null;
  archived_at: string | null;
  updated_at: string;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  is_priority_alert: boolean;
  is_priority_pinned?: boolean;
  priority_alerted_at: string | null;
  urgency: string;
  recycled_posting: boolean;
  analysis: Analysis | null;
}

export interface JobPage {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface Stats {
  total_jobs: number;
  new_jobs: number;
  apply_today: number;
  review: number;
  needs_verification: number;
  not_eligible: number;
  low_match: number;
  closed: number;
  priority_alerts: number;
  urgent: number;
  applications: number;
  last_update: string | null;
  latest_search_id: number | null;
  latest_search_status: string | null;
  latest_search_progress: string | null;
  latest_search_errors: string;
}

export interface Profile {
  id: number;
  full_name: string;
  display_name: string;
  degree: string;
  university: string;
  graduation_year: number;
  graduation_date: string | null;
  degree_level_current: "BACHELORS" | "MASTERS" | "PHD" | "UNKNOWN";
  degree_status: "IN_PROGRESS" | "COMPLETED" | "EXPECTED_BEFORE_START" | "UNKNOWN";
  expected_graduation_date: string | null;
  degree_field: string;
  veteran_status: "NOT_VETERAN" | "VETERAN" | "UNKNOWN";
  military_status: "NONE" | "ACTIVE_DUTY" | "TRANSITIONING_SERVICE_MEMBER" | "VETERAN" | "UNKNOWN";
  military_spouse: boolean;
  disability_status: "NO_DISABILITY" | "HAS_DISABILITY" | "UNKNOWN";
  current_service_member: boolean;
  gpa: number;
  gpa_scale: number | null;
  gpa_scale_status: string;
  current_semester: number | null;
  official_degree_name: string | null;
  official_degree_name_status: string;
  nationality: string;
  citizenship_country: string;
  citizenship_status: string;
  visas: string[];
  work_authorizations: Record<string, string>;
  work_authorized_countries: string[];
  us_work_authorized: boolean;
  requires_us_employment_sponsorship: boolean;
  us_authorization_conflict_detected: boolean;
  work_authorization_raw_statement: string;
  willing_to_relocate: boolean;
  preferred_locations: string[];
  preferred_roles: string[];
  minimum_hours_per_week: number | null;
  github_url: string;
  linkedin_url: string;
  onboarding_status: string;
  profile_warnings: string[];
  skills: string[];
  projects: Array<{ name: string; details: string }>;
  education_notes: string;
  countries_to_search: string[];
  include_remote: boolean;
  only_remote: boolean;
  remote_from_mexico_only: boolean;
  include_hybrid: boolean;
  include_onsite: boolean;
  priority_alerts: boolean;
  priority_minimum_score: number;
  alert_for_major_companies: boolean;
  major_company_minimum_score: number;
  alert_for_deadlines: boolean;
  email_notifications: boolean;
  notification_email: string;
  priority_email_alerts: boolean;
  major_company_email_alerts: boolean;
  deadline_alerts: boolean;
  daily_digest: boolean;
  application_follow_up_alerts: boolean;
  email_minimum_score: number;
  immediate_priority_alerts: boolean;
  updated_at: string;
}

export interface EmailActionResult {
  success: boolean;
  message: string;
  provider: string;
}

export interface Application {
  id: number;
  job_id: number | null;
  application_type?: "STANDARD_JOB" | "TALENT_COMMUNITY";
  company?: string;
  talent_community_url?: string;
  status: string;
  applied_at: string | null;
  submitted_resume_id: number | null;
  application_session_id: number | null;
  resume_type: string;
  application_reference: string | null;
  notes: string;
  next_action_at: string | null;
  created_at: string;
  updated_at: string;
  job: null | {
    id: number;
    company: string;
    title: string;
    location: string;
    apply_url: string;
  };
}

export interface CompanySource {
  id: number;
  company: string;
  source_type: string;
  source_identifier: string;
  source_url: string;
  registry_type: "OFFICIAL_COMPANY" | "OFFICIAL_ATS" | "COMMUNITY_REPO" | "AGGREGATOR" | "JOB_BOARD" | "UNIVERSITY_BOARD" | "OTHER";
  priority: number;
  base_priority: number;
  trust_level: "PRIMARY" | "HIGH" | "MEDIUM" | "LOW";
  refresh_frequency: string;
  supports_structured_data: boolean;
  notes: string;
  source_confidence_score: number;
  reference_only: boolean;
  enabled: boolean;
  last_refresh_at: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_type: string;
  safe_error_message: string;
  http_status: number | null;
  parser_version: string;
  consecutive_failures: number;
  jobs_discovered: number;
  jobs_verified: number;
  last_status: string;
  last_error: string | null;
  last_successful_fetch: string | null;
  last_repository_update: string | null;
  last_successful_parse: string | null;
  last_new_job_seen: string | null;
  source_status: string;
  fetched_count: number;
  parsed_count: number;
  new_jobs_count: number;
  updated_jobs_count: number;
  duplicate_count: number;
  officially_verified_count: number;
  unverified_count: number;
  error_count: number;
  duration_ms: number;
  created_at: string;
}

export interface TargetCompany {
  id: number;
  company_name: string;
  aliases: string[];
  careers_domains: string[];
  category: string;
  priority: "high" | "medium" | "low";
  enabled: boolean;
  custom: boolean;
  preferred_locations: string[];
  preferred_role_categories: string[];
  last_checked_at: string | null;
  last_successful_result_at: string | null;
  open_jobs_count: number;
  created_at: string;
  updated_at: string;
}

export interface TargetSearchRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  companies_checked: number;
  jobs_discovered: number;
  jobs_added: number;
  jobs_updated: number;
  jobs_expired: number;
  errors: Array<{ source?: string; error?: string }>;
  trigger: string;
}

export interface AISettings {
  owner_user_id: string;
  ai_mode: "LOCAL_ONLY" | "BALANCED" | "EXTERNAL_ALLOWED";
  updated_at: string;
}

export interface ExternalAIAudit {
  id: number;
  provider: string;
  purpose: string;
  privacy_classification: string;
  fields_included_json: string[];
  fields_redacted_json: string[];
  created_at: string;
}

export interface SearchRun {
  id: number;
  search_type: string;
  status: "pending" | "running" | "completed" | "partial" | "failed";
  progress_status: string;
  started_at: string;
  completed_at: string | null;
  companies_checked: number;
  sources_checked: number;
  jobs_discovered: number;
  jobs_added: number;
  jobs_updated: number;
  jobs_expired: number;
  error_count: number;
  safe_error_summary: string;
  source_metrics: Array<Record<string, unknown>>;
  criteria_json: SearchCriteria;
  progress_json: {
    sources_checked?: number;
    sources_total?: number;
    jobs_discovered?: number;
    verified?: number;
    eligible?: number;
    duplicates_removed?: number;
  };
  result_count: number;
  eligible_count: number;
  verified_count: number;
  trigger: string;
  created_at: string;
}

export interface ApplicationProfile {
  id: number;
  owner_user_id: string;
  full_name: string;
  professional_email: string;
  phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  university: string;
  degree: string;
  field_of_study: string;
  gpa: number | null;
  gpa_scale: number | null;
  education_start_date: string | null;
  expected_graduation_date: string | null;
  languages_json: string[];
  linkedin_url: string;
  github_url: string;
  skills_json: string[];
  projects_json: Array<Record<string, unknown>>;
  work_experience_json: Array<Record<string, unknown>>;
  academic_project_workaround_allowed: boolean;
  job_discovery_source: string;
  full_time_summer_availability: boolean;
  spring_summer_combined_availability: boolean;
  application_preferences_confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationReadiness {
  ready: boolean;
  hard_blocked: boolean;
  blocker_reason: string;
  portal_type: string;
  portal_job_id: string;
  support_status: "SUPPORTED" | "BETA" | "UNSUPPORTED" | "PORTAL_CHANGED";
  company_policy_key: string;
  detection_evidence: string[];
  checks: Array<{ key: string; label: string; ready: boolean }>;
  sensitive_confirmation_notice: string;
  resume: GeneratedResume | null;
  portfolio: {
    id: number;
    version: number;
    status: string;
    filename: string;
    target_role: string;
    selected_projects: Array<Record<string, unknown>>;
    pdf_url: string;
  } | null;
  selected_experience: Array<Record<string, unknown>>;
  selected_skills: string[];
  generated_experience_text: string;
  project_match_reasons: Record<string, string>;
  skill_match_reasons: Record<string, string>;
  selection_warnings: string[];
}

export type ApplicationSessionStatus =
  | "CREATED"
  | "OPENED"
  | "IN_PROGRESS"
  | "WAITING_FOR_USER"
  | "READY_FOR_REVIEW"
  | "SUBMITTED_BY_USER"
  | "ABANDONED"
  | "ERROR";

export interface ApplicationSession {
  id: number;
  job_id: number | null;
  application_type: "STANDARD_JOB" | "TALENT_COMMUNITY" | "KOSPIE_PROGRAM";
  company_id: string | null;
  company: string;
  portal_type: string;
  application_url: string;
  resume_version_id: number;
  resume_filename: string;
  resume_download_url: string;
  portfolio_version_id: number | null;
  portfolio_filename: string;
  portfolio_download_url: string;
  status: ApplicationSessionStatus;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  current_step: string;
  portal_job_id: string;
  confirmed_fields_json: Record<string, unknown>;
  pending_questions_json: Array<Record<string, unknown>>;
  application_answers_json: Record<string, unknown>;
  profile_snapshot_json: Record<string, unknown>;
  job_snapshot_json: Record<string, unknown>;
  project_experience_json: Array<Record<string, unknown>>;
  selected_projects_json: Array<Record<string, unknown>>;
  generated_experience_text: string;
  selected_skills_json: string[];
  skill_match_reasons_json: Record<string, string>;
  project_match_reasons_json: Record<string, string>;
  selection_warnings_json: string[];
  consistency_issues_json: Array<{
    code?: string;
    field?: string;
    message?: string;
    observed?: unknown;
    expected?: unknown;
  }>;
  portal_detection_evidence_json: string[];
  adapter_diagnostics_json: Record<string, unknown>;
  adapter_version: string;
  company_policy_key: string;
  assessment_type: string;
  fields_filled_count: number;
  fields_reviewed_count: number;
  fields_confirmed_count: number;
  last_extension_seen_at: string | null;
  last_page_url: string;
  error_code: string;
  safe_error_message: string;
}

export interface ApplicationSessionLaunch {
  session: ApplicationSession;
  application_session_token: string;
  token_expires_at: string;
  extension_message_origin: string;
}

export type SearchWorkModel = "ANY" | "REMOTE" | "HYBRID" | "ON_SITE";
export type SearchRemoteScope = "MEXICO" | "LATAM" | "GLOBAL" | "US_ONLY" | "UNKNOWN";
export type SearchRoleCategory =
  | "SOFTWARE_ENGINEERING"
  | "EMBEDDED_FIRMWARE"
  | "ROBOTICS"
  | "AI_MACHINE_LEARNING"
  | "COMPUTER_VISION"
  | "BACKEND"
  | "FULL_STACK"
  | "FPGA_DIGITAL_DESIGN"
  | "HARDWARE_VALIDATION"
  | "ELECTRICAL_VALIDATION"
  | "DATA_ALGORITHMS"
  | "RESEARCH_ENGINEERING"
  | "OTHER";
export type SearchSourceMode = "ALL_SOURCES" | "OFFICIAL_ONLY" | "OFFICIAL_AND_COMMUNITY";

export interface SearchCriteria {
  companies: string[];
  target_companies_only: boolean;
  work_models: SearchWorkModel[];
  remote_scopes: SearchRemoteScope[];
  countries: string[];
  states: string[];
  cities: string[];
  role_categories: SearchRoleCategory[];
  include_keywords: string[];
  exclude_keywords: string[];
  only_realistically_eligible: boolean;
  include_unknown_eligibility: boolean;
  source_mode: SearchSourceMode;
  posted_within_days: 1 | 3 | 7 | 14 | 30 | null;
  limit: 25 | 50 | 100;
}

export interface SearchRunDeleteResult {
  id: number;
  deleted_from_history: boolean;
}

export interface JobLifecycleAction {
  job: Job;
  application: Application | null;
  previous_status: "active" | "saved";
  message: string;
}

export interface ResumeProfile {
  id: number;
  user_id: string;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  github_url: string;
  headline: string;
  summary: string;
  education_json: Array<Record<string, unknown>>;
  skills_json: string[];
  experience_json: Array<Record<string, unknown>>;
  projects_json: Array<Record<string, unknown>>;
  coursework_json: Array<string | Record<string, unknown>>;
  certifications_json: Array<Record<string, unknown>>;
  languages_json: string[];
  language_credentials_json: LanguageCredential[];
  forbidden_claims_json: string[];
  created_at: string;
  updated_at: string;
}

export interface VerifiedSkill {
  skill: string;
  category: string;
  evidence: string[];
  evidence_types: string[];
}

export interface VerifiedSkillGroup {
  name: string;
  items: VerifiedSkill[];
}

export interface ResumeSkillMatch {
  skill: string;
  category: string;
  match_type: "required" | "preferred" | "contextual";
  match_kind?: "EXACT" | "ALIAS" | "SEMANTIC_SUPPORTED" | "PARTIAL" | "NOT_FOUND";
  score: number;
  reason: string;
  evidence: string[];
  job_occurrences: number;
}

export interface GeneratedResume {
  id: number;
  job_id: number | null;
  application_type: "STANDARD_JOB" | "TALENT_COMMUNITY" | "KOSPIE_PROGRAM" | "PROFILE_PORTFOLIO" | "BEST_RESUME";
  company_id: string | null;
  company_profile?: Record<string, unknown>;
  company: string;
  target_role_categories: string[];
  version: number;
  status: "pending" | "queued" | "generating" | "compiled" | "failed" | "failed_retryable";
  target_role: string;
  resume_target: "recommended" | "software_engineering" | "embedded_firmware" | "electrical_validation" | "hardware_engineering" | "robotics_research" | "talent_community" | "kospie_germany" | "best_resume";
  tailored_content_json: Record<string, unknown>;
  latex_source: string;
  match_score: number;
  keywords_json: {
    included?: string[];
    supported_not_included?: string[];
    missing?: string[];
    refused?: string[];
  };
  changes_json: Array<{ section: string; description: string; reason: string }>;
  warnings_json: string[];
  selected_skills: string[];
  skill_categories: Array<{ name: string; items: string[] }>;
  job_skill_matches: ResumeSkillMatch[];
  skill_verification: {
    all_verified: boolean;
    verified: string[];
    removed: string[];
    registry_size: number;
  };
  generation_model: string;
  generation_error: string | null;
  is_stale?: boolean;
  created_at: string;
  updated_at: string;
  pdf_url: string | null;
  tex_url: string;
}

export interface ResearchOpportunityAnalysis {
  research_focus: string[];
  verified_matches: string[];
  unverified_keywords: string[];
  recommended_projects: Array<{ name: string; match: number; why: string }>;
  recommended_skills: { strong_match: string[]; relevant: string[]; not_selected: string[] };
  research_interests: string[];
  confidence: number;
  similarity: number;
  similar_resume_id: number | null;
  reuse_message: string;
}

export interface LanguageCredential {
  language: string;
  proficiency: string;
  certificate: string;
  score: string;
  verified: boolean;
}

export interface KospieProfile {
  owner_user_id: string;
  program_name: string;
  organization: string;
  program_type: string;
  selected_universities_json: [string, string, string];
  primary_interests_json: string[];
  created_at: string;
  updated_at: string;
}

export interface KospieAnalysis {
  academic_strengths: string[];
  technical_strengths: string[];
  recommended_projects: Array<{
    name: string;
    match: number;
    why: string;
    reasons: string[];
    domains: string[];
    selected: boolean;
    rank: number;
    project_type: "complete_project" | "focused_technical_exercise" | "laboratory_practice";
    depth_evidence: string[];
    subsystems: string[];
    capabilities: string[];
    components: Record<string, number>;
  }>;
  recommended_skills: string[];
  recommended_coursework: {
    strong: Array<{ name: string; institution?: string }>;
    relevant: Array<{ name: string; institution?: string }>;
  };
  language_status: Array<Record<string, string>>;
  eligibility: Array<Record<string, string>>;
  selected_universities: string[];
  primary_interests: string[];
}

export interface ResumeStudioProfile {
  id: string;
  label: string;
  description: string;
}

export interface ResumeStudioAnalysis {
  profile_id: string;
  label: string;
  description: string;
  summary: string;
  headline: string;
  can_generate: boolean;
  notice: string;
  selected_skills: string[];
  weights: Record<string, number>;
  projects: Array<{
    name: string;
    rank: number;
    score: number;
    selected: boolean;
    project_type: string;
    domains: string[];
    reasons: string[];
    components: Record<string, number>;
  }>;
}

export interface KospieResumeContent {
  projects?: Array<{ name: string; technologies: string[]; relevance_score: number }>;
  coursework?: Array<{ name: string; institution?: string }>;
  language_verification?: Array<Record<string, string>>;
  program_eligibility?: Array<Record<string, string>>;
  why_this_version?: string[];
  quality_checks?: { one_page?: boolean; within_two_pages?: boolean };
}
