import type { ExtensionPayload, PortalType } from "../src/shared/types";

export function makePayload(portalType: PortalType = "WORKDAY", company = "Example"): ExtensionPayload {
  return {
    ai_settings: { owner_user_id: "test-user", ai_mode: "BALANCED", updated_at: "2026-09-10T00:00:00Z" },
    session: {
      id: 1, job_id: 3, company, portal_type: portalType,
      application_url: "https://careers.example.com/apply/REQ-1234", resume_version_id: 18,
      resume_filename: "Santiago_Example_Recommended_Resume_v4.pdf", resume_download_url: "/api/extension/application-session/resume.pdf",
      portfolio_version_id: null, portfolio_filename: "", portfolio_download_url: "",
      status: "OPENED", current_step: "Contact", portal_job_id: "REQ-1234",
      pending_questions_json: [], application_answers_json: {}, consistency_issues_json: [],
      fields_filled_count: 0, fields_reviewed_count: 0, fields_confirmed_count: 0,
      project_experience_json: [{ name: "Internship Radar", description: "FastAPI and Next.js application.", resume_selection: { bullets: ["Built a FastAPI and Next.js internship platform."] } }],
      selected_projects_json: [{ name: "Internship Radar", description: "FastAPI and Next.js application.", resume_selection: { bullets: ["Built a FastAPI and Next.js internship platform."] } }],
      generated_experience_text: "Academic and personal software projects; not professional employment.\n\nInternship Radar\n• Built a FastAPI and Next.js internship platform.",
      selected_skills_json: ["Python", "Git"], skill_match_reasons_json: {}, project_match_reasons_json: {}, selection_warnings_json: [],
      job_snapshot_json: { country: company === "Zipline" ? "United States" : "Mexico", physical_work_country_required: company === "Zipline" ? "United States" : "Mexico" },
      portal_detection_evidence_json: [],
      adapter_diagnostics_json: { adapterVersion: "", lastSuccessfulDetection: null, fieldsDetected: 0, fieldsFilled: 0, fieldsFailed: 0, unknownFields: 0, confidence: 0, evidence: [] },
      adapter_version: "2.0.0", company_policy_key: company.toLocaleUpperCase(), assessment_type: ""
    },
    profile: {
      contact: { full_name: "Santiago Example", professional_email: "candidate@example.com", phone: "+52 555 555 5555", address_line1: "Av. Example 100", address_line2: "", city: "Monterrey", state: "Nuevo Leon", postal_code: "64000", country: "Mexico" },
      education: { university: "Tecnologico de Monterrey", degree: "B.S.", field_of_study: "Robotics", gpa: 93, gpa_scale: 100, start_date: "2024-08-01", expected_graduation_date: "2028-06-30" },
      languages: ["English — Fluent", "Spanish — Native"],
      links: { github: "https://github.com/example", linkedin: "https://www.linkedin.com/in/example-candidate/" },
      verified_skills: ["Python", "Git", "REST APIs"], verified_projects: [], verified_work_experience: [], academic_project_workaround_allowed: false,
      work_authorization: { citizenship_country: "Mexico", work_authorized_countries: ["Mexico"], us_work_authorized: false, requires_us_employment_sponsorship: true },
      application_preferences: { job_discovery_source: "GOOGLE_SEARCH", full_time_summer_availability: true, spring_summer_combined_availability: true, confirmed_at: "2026-08-24T00:00:00Z", answer_source: "USER_CONFIRMED" }
    },
    resume: { id: 18, version: 4, target_role: "Software Intern", selected_skills: ["Python", "Git"], pdf_url: "/resume.pdf", filename: "Santiago_Example_Recommended_Resume_v4.pdf" },
    portfolio: null,
    answer_suggestions: [], field_policies: ["AUTO_FILL", "AUTO_FILL_REVIEW_REQUIRED", "REVIEW_RECOMMENDED", "CONFIRM_REQUIRED", "MANUAL_ONLY"],
    sensitive_question_keys: ["US_WORK_AUTHORIZATION", "US_SPONSORSHIP_REQUIRED", "GOVERNMENT_EMPLOYEE"],
    company_policy: { company_id: company.toLocaleLowerCase().replaceAll(" ", "_"), company_name: company, known_domains: [], portal_type: portalType, application_adapter: "", company_policy_key: company.toLocaleUpperCase(), company_specific_rules: {}, known_question_aliases: {}, support_status: portalType === "WORKDAY" || portalType === "GREENHOUSE" ? "SUPPORTED" : "BETA" },
    adapter_status: portalType === "WORKDAY" || portalType === "GREENHOUSE" ? "SUPPORTED" : "BETA",
    final_submit_policy: "MANUAL_ONLY"
  };
}
