import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkdayAdapter } from "../src/content/adapters/workday/WorkdayAdapter";
import type { ExtensionPayload } from "../src/shared/types";

const payload: ExtensionPayload = {
  ai_settings: { owner_user_id: "test-user", ai_mode: "BALANCED", updated_at: "2026-09-10T00:00:00Z" },
  session: {
    id: 1,
    job_id: 3,
    company: "Example",
    portal_type: "WORKDAY",
    application_url: "https://example.wd1.myworkdayjobs.com/job/REQ-1234",
    resume_version_id: 18,
    resume_filename: "Santiago_Example_Resume.pdf",
    resume_download_url: "/api/extension/application-session/resume.pdf",
    portfolio_version_id: null,
    portfolio_filename: "",
    portfolio_download_url: "",
    status: "OPENED",
    current_step: "Contact",
    portal_job_id: "REQ-1234",
    pending_questions_json: [],
    application_answers_json: {},
    consistency_issues_json: [],
    fields_filled_count: 0,
    fields_reviewed_count: 0,
    fields_confirmed_count: 0,
    project_experience_json: [],
    selected_projects_json: [],
    generated_experience_text: "",
    selected_skills_json: ["Python", "Git"],
    skill_match_reasons_json: {},
    project_match_reasons_json: {},
    selection_warnings_json: [],
    job_snapshot_json: { country: "Mexico", physical_work_country_required: "Mexico" },
    portal_detection_evidence_json: [],
    adapter_diagnostics_json: { adapterVersion: "2.0.0", lastSuccessfulDetection: null, fieldsDetected: 0, fieldsFilled: 0, fieldsFailed: 0, unknownFields: 0, confidence: 0, evidence: [] },
    adapter_version: "2.0.0",
    company_policy_key: "GENERIC",
    assessment_type: ""
  },
  profile: {
    contact: { full_name: "Santiago Example", professional_email: "candidate@example.com", phone: "+52 555 555 5555", address_line1: "", address_line2: "", city: "Monterrey", state: "Nuevo Leon", postal_code: "", country: "Mexico", current_location: "Monterrey, Nuevo Leon, Mexico" },
    education: { university: "Tecnologico de Monterrey", degree: "B.S.", field_of_study: "Robotics", gpa: 93, gpa_scale: 100, start_date: "2024-08-01", expected_graduation_date: "2028-06-30" },
    languages: ["English — Fluent", "Spanish — Native"],
    links: { github: "https://github.com/example", linkedin: "https://www.linkedin.com/in/example-candidate/" },
    verified_skills: ["Python", "Git"],
    verified_projects: [],
    verified_work_experience: [],
    academic_project_workaround_allowed: false,
    work_authorization: { citizenship_country: "Mexico", work_authorized_countries: ["Mexico"], us_work_authorized: false, requires_us_employment_sponsorship: true },
    application_preferences: { job_discovery_source: "GOOGLE_SEARCH", full_time_summer_availability: true, spring_summer_combined_availability: true, confirmed_at: "2026-08-24T00:00:00Z", answer_source: "USER_CONFIRMED" }
  },
  resume: { id: 18, version: 18, target_role: "Software Intern", selected_skills: ["Python", "Git"], pdf_url: "/resume.pdf", filename: "Santiago_Example_Resume.pdf" },
  portfolio: null,
  answer_suggestions: [{ question_key: "US_WORK_AUTHORIZATION", normalized_question: "Authorized to work in the US", answer_json: { value: "No" }, sensitivity: "CONFIRM_REQUIRED", last_confirmed_at: "2026-08-23T12:00:00Z" }],
  field_policies: ["AUTO_FILL", "AUTO_FILL_REVIEW_REQUIRED", "REVIEW_RECOMMENDED", "CONFIRM_REQUIRED", "MANUAL_ONLY"],
  sensitive_question_keys: ["US_WORK_AUTHORIZATION"],
  company_policy: { company_id: "example", company_name: "Example", known_domains: [], portal_type: "WORKDAY", application_adapter: "WorkdayAdapter", company_policy_key: "GENERIC", company_specific_rules: {}, known_question_aliases: {}, support_status: "SUPPORTED" },
  adapter_status: "SUPPORTED",
  final_submit_policy: "MANUAL_ONLY"
};

describe("Workday adapter", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("fills safe fields and leaves sensitive legal fields untouched", async () => {
    document.body.innerHTML = `
      <label for="first">First Name</label><input id="first" />
      <label for="email">Email Address</label><input id="email" />
      <label for="city">City</label><input id="city" />
      <label for="school">University</label><input id="school" />
      <label for="github">GitHub Website</label><input id="github" />
      <label for="auth">Are you legally authorized to work in the United States?</label>
      <select id="auth"><option value="">Select</option><option>No</option><option>Yes</option></select>
    `;
    const adapter = new WorkdayAdapter();
    const result = await adapter.fillThisPage(payload);
    expect((document.getElementById("first") as HTMLInputElement).value).toBe("Santiago");
    expect((document.getElementById("email") as HTMLInputElement).value).toBe("candidate@example.com");
    expect((document.getElementById("city") as HTMLInputElement).value).toBe("Monterrey");
    expect((document.getElementById("school") as HTMLInputElement).value).toBe("Tecnologico de Monterrey");
    expect((document.getElementById("github") as HTMLInputElement).value).toBe("https://github.com/example");
    expect((document.getElementById("auth") as HTMLSelectElement).value).toBe("");
    expect(result.filled).toBe(5);
    expect(adapter.review(payload).pendingQuestions[0]?.questionKey).toBe("US_WORK_AUTHORIZATION");
  });

  it("adds verified skills one at a time rather than as a comma-separated string", async () => {
    document.body.innerHTML = `
      <label for="skills">Skills</label><input id="skills" />
      <div role="option">Python</div><div role="option">Git</div><button>Add</button>
    `;
    const values: string[] = [];
    document.getElementById("skills")!.addEventListener("input", (event) => values.push((event.target as HTMLInputElement).value));
    const adapter = new WorkdayAdapter();
    await adapter.fillThisPage(payload);
    expect(values).toEqual(expect.arrayContaining(["Python", "Git"]));
    expect(values).not.toContain("Python, Git");
  });

  it("adds verified languages individually", async () => {
    document.body.innerHTML = `
      <label for="language">Languages</label><input id="language" />
      <div role="option">English</div><div role="option">Spanish</div><button>Add</button>
    `;
    const values: string[] = [];
    document.getElementById("language")!.addEventListener("input", (event) => values.push((event.target as HTMLInputElement).value));
    await new WorkdayAdapter().fillThisPage(payload);
    expect(values).toEqual(expect.arrayContaining(["English", "Spanish"]));
  });

  it("never clicks the final submit action", async () => {
    document.body.innerHTML = `<h1>Review Your Application</h1><button id="submit">Submit</button>`;
    const click = vi.fn();
    document.getElementById("submit")!.addEventListener("click", click);
    const adapter = new WorkdayAdapter();
    expect(adapter.isReviewPage()).toBe(true);
    expect(await adapter.continuePage(0)).toBe(false);
    expect(click).not.toHaveBeenCalled();
  });

  it("rescans fields added by Workday dynamic DOM updates", async () => {
    const adapter = new WorkdayAdapter();
    const changed = vi.fn();
    const stop = adapter.observe(changed);
    document.body.insertAdjacentHTML("beforeend", `<label for="city">City</label><input id="city" />`);
    await new Promise((resolve) => setTimeout(resolve, 180));
    stop();
    expect(changed).toHaveBeenCalled();
    expect(adapter.detectFields().some((field) => field.label === "City")).toBe(true);
  });

  it("detects a Workday confirmation page but still requires final user confirmation", () => {
    document.body.innerHTML = `<main><h1>Application submitted</h1><p>Thank you for applying. Your application has been received.</p></main>`;
    const result = new WorkdayAdapter().detectConfirmation();
    expect(result.confirmed).toBe(true);
    expect(result.text).toContain("Thank you for applying");
  });
});
