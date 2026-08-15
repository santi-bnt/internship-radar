export type Recommendation =
  | "Apply Today"
  | "Review"
  | "Needs Verification"
  | "Not Eligible"
  | "Low Match"
  | "Closed";

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
  applied_at: string | null;
  expired_at: string | null;
  archived_at: string | null;
  updated_at: string;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  is_priority_alert: boolean;
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
  gpa_scale: number;
  nationality: string;
  citizenship_country: string;
  visas: string[];
  work_authorizations: Record<string, string>;
  work_authorized_countries: string[];
  us_work_authorized: boolean;
  requires_us_employment_sponsorship: boolean;
  willing_to_relocate: boolean;
  preferred_locations: string[];
  preferred_roles: string[];
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
  job_id: number;
  status: string;
  applied_at: string | null;
  submitted_resume_id: number | null;
  resume_type: string;
  application_reference: string | null;
  notes: string;
  next_action_at: string | null;
  created_at: string;
  updated_at: string;
  job: {
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
  trigger: string;
  created_at: string;
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
  score: number;
  reason: string;
  evidence: string[];
  job_occurrences: number;
}

export interface GeneratedResume {
  id: number;
  job_id: number;
  version: number;
  status: "pending" | "generating" | "compiled" | "failed";
  target_role: string;
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
  created_at: string;
  updated_at: string;
  pdf_url: string | null;
  tex_url: string;
}
