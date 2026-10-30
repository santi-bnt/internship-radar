import { describe, expect, it } from "vitest";

import { validateConsistency } from "../src/shared/consistency";
import type { ApplicationProfileSnapshot } from "../src/shared/types";

const profile: ApplicationProfileSnapshot = {
  contact: { professional_email: "candidate@example.com", city: "Monterrey", current_location: "Monterrey, Nuevo Leon, Mexico" },
  education: { start_date: "2024-08-01", expected_graduation_date: "2028-06-30", gpa: 93 },
  languages: ["English — Fluent", "Spanish — Native"],
  links: {},
  verified_skills: ["Python", "Git"],
  verified_projects: [],
  verified_work_experience: [],
  academic_project_workaround_allowed: false,
  work_authorization: { citizenship_country: "Mexico", work_authorized_countries: ["Mexico"], us_work_authorized: false, requires_us_employment_sponsorship: true },
  application_preferences: { job_discovery_source: "GOOGLE_SEARCH", full_time_summer_availability: true, spring_summer_combined_availability: true, confirmed_at: "2026-08-24T00:00:00Z", answer_source: "USER_CONFIRMED" }
};

describe("pre-submit consistency validation", () => {
  it("detects bad dates, duplicate addresses, wrong resume, and unverified skills", () => {
    const issues = validateConsistency(profile, {
      email: "wrong@example.com",
      education_start_year: "2002",
      graduation_date: "2026-06-30",
      gpa: 88,
      degree_status: "Degree completed",
      address_line1: "123 Main St",
      address_line2: "123 Main St",
      resume_version_id: 9,
      skills: ["Python", "Invented Skill"],
      languages: ["English — Basic"],
      work_authorization_answers: { US_WORK_AUTHORIZATION: ["Yes", "No"] }
    }, 18);
    expect(issues.map((issue) => issue.code)).toEqual(expect.arrayContaining([
      "MISMATCH_EMAIL",
      "BAD_EDUCATION_START_YEAR",
      "MISMATCH_GRADUATION_DATE",
      "MISMATCH_GPA",
      "DEGREE_STATUS_CONTRADICTION",
      "DUPLICATED_ADDRESS",
      "WRONG_RESUME",
      "UNVERIFIED_SKILLS",
      "INCONSISTENT_LANGUAGE_FLUENCY",
      "CONTRADICTORY_WORK_AUTHORIZATION"
    ]));
  });

  it("requires the project-as-employment disclosure", () => {
    const issues = validateConsistency(profile, {
      project_as_employment: true,
      experience_description: "Built several school projects."
    }, 18);
    expect(issues.some((issue) => issue.code === "PROJECT_EMPLOYMENT_DISCLOSURE")).toBe(true);
  });
});
