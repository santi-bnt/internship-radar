export type FieldPolicy = "AUTO_FILL" | "AUTO_FILL_REVIEW_REQUIRED" | "REVIEW_RECOMMENDED" | "CONFIRM_REQUIRED" | "MANUAL_ONLY";
export type PortalType = "WORKDAY" | "GREENHOUSE" | "MICROSOFT_CAREERS" | "AMAZON_JOBS" | "ORACLE_CAREERS" | "LEVER" | "ASHBY" | "SMARTRECRUITERS" | "GOOGLE_CAREERS" | "GENERIC" | "UNKNOWN";
export type PortalSupportStatus = "SUPPORTED" | "BETA" | "UNSUPPORTED" | "PORTAL_CHANGED";
export type ApplicationStage = "PROFILE" | "RESUME" | "CONTACT" | "EXPERIENCE" | "EDUCATION" | "SKILLS" | "QUESTIONS" | "LEGAL" | "VOLUNTARY" | "REVIEW" | "CONFIRMATION";
export type AssessmentType = "CODING_ASSESSMENT" | "ONLINE_ASSESSMENT" | "BEHAVIORAL_ASSESSMENT" | "TECHNICAL_TEST" | "";

export interface StoredApplicationSession {
  sessionId: number;
  token: string;
  expiresAt: string;
  apiBaseUrl: string;
  applicationUrl: string;
}

export interface ApplicationSession {
  id: number;
  job_id: number | null;
  application_type?: "STANDARD_JOB" | "TALENT_COMMUNITY";
  company: string;
  portal_type: string;
  application_url: string;
  resume_version_id: number;
  resume_filename: string;
  resume_download_url: string;
  portfolio_version_id: number | null;
  portfolio_filename: string;
  portfolio_download_url: string;
  status: string;
  current_step: string;
  portal_job_id: string;
  pending_questions_json: PendingQuestion[];
  application_answers_json: Record<string, unknown>;
  consistency_issues_json: ConsistencyIssue[];
  fields_filled_count: number;
  fields_reviewed_count: number;
  fields_confirmed_count: number;
  project_experience_json: Array<Record<string, unknown>>;
  selected_projects_json: Array<Record<string, unknown>>;
  generated_experience_text: string;
  selected_skills_json: string[];
  skill_match_reasons_json: Record<string, string>;
  project_match_reasons_json: Record<string, string>;
  selection_warnings_json: string[];
  job_snapshot_json: Record<string, unknown>;
  portal_detection_evidence_json: string[];
  adapter_diagnostics_json: AdapterDiagnostics;
  adapter_version: string;
  company_policy_key: string;
  assessment_type: AssessmentType;
}

export interface AnswerSuggestion {
  question_key: string;
  normalized_question: string;
  answer_json: { value?: unknown };
  sensitivity: string;
  last_confirmed_at: string | null;
}

export interface ExtensionPayload {
  session: ApplicationSession;
  profile: ApplicationProfileSnapshot;
  resume: {
    id: number;
    version: number;
    target_role: string;
    selected_skills: string[];
    pdf_url: string;
    filename: string;
  };
  portfolio: {
    id: number;
    version: number;
    status: string;
    filename: string;
    target_role: string;
    selected_projects: Array<Record<string, unknown>>;
    pdf_url: string;
  } | null;
  answer_suggestions: AnswerSuggestion[];
  field_policies: FieldPolicy[];
  sensitive_question_keys: string[];
  company_policy: CompanyApplicationPolicy;
  adapter_status: PortalSupportStatus;
  ai_settings: {
    owner_user_id: string;
    ai_mode: "LOCAL_ONLY" | "BALANCED" | "EXTERNAL_ALLOWED";
    updated_at: string;
  };
  final_submit_policy: "MANUAL_ONLY";
}

export interface ApplicationProfileSnapshot {
  contact: Record<string, string>;
  education: Record<string, string | number | null>;
  languages: string[];
  links: Record<string, string>;
  verified_skills: string[];
  verified_projects: Array<Record<string, unknown>>;
  verified_work_experience: Array<Record<string, unknown>>;
  academic_project_workaround_allowed: boolean;
  work_authorization: {
    citizenship_country: string;
    work_authorized_countries: string[];
    us_work_authorized: boolean;
    requires_us_employment_sponsorship: boolean;
  };
  application_preferences: {
    job_discovery_source: string;
    full_time_summer_availability: boolean;
    spring_summer_combined_availability: boolean;
    confirmed_at: string | null;
    answer_source: string;
  };
}

export interface PreparedApplicationFile {
  kind: "RESUME" | "PORTFOLIO";
  filename: string;
  mimeType: "application/pdf";
  base64: string;
  versionId: number;
}

export interface PendingQuestion {
  questionKey: string;
  question: string;
  confidence: number;
  policy: FieldPolicy;
  suggestedAnswer?: unknown;
  previouslyConfirmedAt?: string | null;
}

export interface DetectedField {
  element: HTMLElement;
  fieldId: string;
  label: string;
  nearbyText: string;
  controlType: string;
  availableOptions: string[];
  currentValue?: unknown;
  required: boolean;
  maxlength?: number;
  normalizedKey: string;
  policy: FieldPolicy;
  confidence: number;
  value?: unknown;
  answerSource?: string;
  conflict?: PortalValueConflict;
}

export type AgentDecisionAction = "AUTO_FILL" | "AUTO_FILL_REVIEW" | "GENERATE_REVIEW" | "CONFIRM" | "MANUAL_ONLY";

export interface AgentFieldResolution {
  field_id: string;
  canonical_field: string;
  question_category: string;
  action: AgentDecisionAction;
  selected_value?: unknown;
  selected_option?: string | null;
  confidence: number;
  match_type: string;
  reason_summary: string;
  requires_review: boolean;
  evidence_ids: string[];
  privacy_level: string;
  provider: string;
  execution_location: "LOCAL" | "EXTERNAL";
}

export interface ApplicationAgentPlan {
  status: "PLAN_READY" | "WAITING_FOR_USER" | "READY_FOR_REVIEW";
  resolutions: AgentFieldResolution[];
  local_ai_available: boolean | null;
  external_calls: number;
  fields_redacted: string[];
  final_submit_policy: "MANUAL_ONLY";
}

export interface CompanyApplicationPolicy {
  company_id: string;
  company_name: string;
  known_domains: string[];
  portal_type: PortalType;
  application_adapter: string;
  company_policy_key: string;
  company_specific_rules: Record<string, unknown>;
  known_question_aliases: Record<string, string[]>;
  support_status: PortalSupportStatus;
}

export interface PortalDetection {
  portalType: PortalType;
  confidence: number;
  evidence: string[];
  companyId: string;
  supportStatus: PortalSupportStatus;
}

export interface PortalValueConflict {
  classification: "SAME" | "FORMAT_DIFFERENCE" | "POTENTIAL_CONFLICT" | "CRITICAL_CONFLICT";
  portalValue: string;
  verifiedValue: string;
}

export interface AdapterDiagnostics {
  adapterVersion: string;
  lastSuccessfulDetection: string | null;
  fieldsDetected: number;
  fieldsFilled: number;
  fieldsFailed: number;
  unknownFields: number;
  confidence: number;
  evidence: string[];
}

export interface ConsistencyIssue {
  code: string;
  field: string;
  message: string;
  observed?: unknown;
  expected?: unknown;
}

export interface AssistantPageState {
  localVision?: { model: string; engine: "LOCAL_HTML_VISION"; analyzedAt: string; domFields: number; imageQuestions: number; message: string };
  pageObservation?: {
    url: string; title: string; readAt: string; framesScanned: number; unreadableFrames: number;
    readOnly: boolean; reason: string; documentKey: string;
  };
  applicationSessionId?: number;
  applicationPageUrl?: string;
  connected: boolean;
  lastActionMessage: string;
  paused: boolean;
  portal: PortalType;
  supportStatus: PortalSupportStatus;
  company: string;
  jobTitle: string;
  currentSection: string;
  progress: number;
  fields: Array<Omit<DetectedField, "element">>;
  pendingQuestions: PendingQuestion[];
  consistencyIssues: ConsistencyIssue[];
  isReviewPage: boolean;
  isConfirmationPage: boolean;
  confirmationText: string;
  assessmentType: AssessmentType;
  safeAutofillPausedReason: string;
  stage: ApplicationStage;
  adapterDiagnostics: AdapterDiagnostics;
  resume: ExtensionPayload["resume"] | null;
  portfolio: ExtensionPayload["portfolio"];
  legalReview: Array<{ key: string; label: string; value: string; source: string }>;
  applicationChecks: Array<{ key: string; label: string; ready: boolean; blocking: boolean }>;
  counts: { filled: number; reviewed: number; confirmed: number };
  agentDecisions: AgentFieldResolution[];
  aiMode: "LOCAL_ONLY" | "BALANCED" | "EXTERNAL_ALLOWED";
  debugEnabled: boolean;
}
