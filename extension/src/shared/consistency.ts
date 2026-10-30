import { normalizeQuestion } from "./questionMatcher";
import type { ApplicationProfileSnapshot, ConsistencyIssue } from "./types";

export function validateConsistency(
  profile: ApplicationProfileSnapshot,
  observed: Record<string, unknown>,
  resumeVersionId: number,
): ConsistencyIssue[] {
  const issues: ConsistencyIssue[] = [];
  const mismatch = (field: string, expected: unknown, message: string) => {
    const actual = observed[field];
    if (actual != null && actual !== "" && expected != null && expected !== "" && normalizeQuestion(String(actual)) !== normalizeQuestion(String(expected))) {
      issues.push({ code: `MISMATCH_${field.toUpperCase()}`, field, message, observed: actual, expected });
    }
  };
  mismatch("email", profile.contact.professional_email, "Email does not match the verified profile.");
  mismatch("city", profile.contact.city, "City does not match the verified profile.");
  mismatch("graduation_date", profile.education.expected_graduation_date, "Graduation date does not match the verified profile.");
  mismatch("gpa", profile.education.gpa, "GPA does not match the verified profile.");
  const currentLocation = normalizeQuestion(String(observed.current_location ?? ""));
  const expectedLocation = normalizeQuestion(String(profile.contact.current_location ?? ""));
  if (currentLocation && expectedLocation && currentLocation !== expectedLocation) {
    issues.push({ code: "MISMATCH_CURRENT_LOCATION", field: "current_location", message: "Current location does not match the verified profile.", observed: observed.current_location, expected: profile.contact.current_location });
  }
  if ("city" in observed && !String(observed.city ?? "").trim() && profile.contact.city) {
    issues.push({ code: "MISSING_CITY", field: "city", message: "City is missing from the application.", observed: "", expected: profile.contact.city });
  }
  const startYear = String(profile.education.start_date ?? "").slice(0, 4);
  const observedYear = String(observed.education_start_year ?? "").slice(0, 4);
  if (startYear && observedYear && startYear !== observedYear) {
    issues.push({ code: "BAD_EDUCATION_START_YEAR", field: "education_start_year", message: "Education start year conflicts with the verified profile.", observed: observedYear, expected: startYear });
  }
  if (/^\d{4}$/.test(observedYear) && Number(observedYear) < 1980) {
    issues.push({ code: "IMPOSSIBLE_EDUCATION_DATE", field: "education_start_year", message: "Education start year appears impossible.", observed: observedYear, expected: startYear });
  }
  const endYear = String(profile.education.expected_graduation_date ?? "").slice(0, 4);
  const observedEndYear = String(observed.education_end_year ?? "").slice(0, 4);
  if (endYear && observedEndYear && endYear !== observedEndYear) {
    issues.push({ code: "BAD_EDUCATION_END_YEAR", field: "education_end_year", message: "Education end year conflicts with the verified profile.", observed: observedEndYear, expected: endYear });
  }
  if (/^\d{4}$/.test(observedEndYear) && Number(observedEndYear) < 1980) {
    issues.push({ code: "IMPOSSIBLE_EDUCATION_END_DATE", field: "education_end_year", message: "Education end year appears impossible.", observed: observedEndYear, expected: endYear });
  }
  if (normalizeQuestion(String(observed.address_line1 ?? "")) && normalizeQuestion(String(observed.address_line1)) === normalizeQuestion(String(observed.address_line2 ?? ""))) {
    issues.push({ code: "DUPLICATED_ADDRESS", field: "address_line2", message: "Address line 2 duplicates address line 1.", observed: observed.address_line2, expected: "" });
  }
  if (observed.resume_version_id != null && observed.resume_version_id !== resumeVersionId) {
    issues.push({ code: "WRONG_RESUME", field: "resume_version_id", message: "The selected resume is not the session resume.", observed: observed.resume_version_id, expected: resumeVersionId });
  }
  if (observed.expected_resume_filename && observed.uploaded_resume_filename && observed.expected_resume_filename !== observed.uploaded_resume_filename) {
    issues.push({ code: "WRONG_RESUME_FILE", field: "uploaded_resume_filename", message: "The uploaded resume is not the session resume.", observed: observed.uploaded_resume_filename, expected: observed.expected_resume_filename });
  }
  if (Array.isArray(observed.required_missing_fields)) {
    for (const field of observed.required_missing_fields) {
      issues.push({ code: "MISSING_REQUIRED_FIELD", field: String(field), message: `Required field is blank: ${String(field)}.`, observed: "", expected: "Completed before final review" });
    }
  }
  if (profile.education.expected_graduation_date && /graduated|degree completed/.test(normalizeQuestion(String(observed.degree_status ?? "")))) {
    issues.push({ code: "DEGREE_STATUS_CONTRADICTION", field: "degree_status", message: "Portal degree status says completed while the verified degree is still in progress.", observed: observed.degree_status, expected: "In progress" });
  }
  const verified = new Set(profile.verified_skills.map(normalizeQuestion));
  const unknown = Array.isArray(observed.skills) ? observed.skills.filter((skill) => !verified.has(normalizeQuestion(String(skill)))) : [];
  if (unknown.length) issues.push({ code: "UNVERIFIED_SKILLS", field: "skills", message: "Unverified skills are present.", observed: unknown, expected: profile.verified_skills });
  if (observed.project_as_employment && !normalizeQuestion(String(observed.experience_description ?? "")).includes("not professional employment")) {
    issues.push({ code: "PROJECT_EMPLOYMENT_DISCLOSURE", field: "experience_description", message: "Academic projects must be disclosed as non-professional employment.", observed: observed.experience_description, expected: "Academic and personal software projects; not professional employment." });
  }
  const languageParts = (value: unknown): [string, string] => {
    const parts = String(value).split(/\s*(?:[-\u2014\u2013:|])\s*/, 2);
    return [normalizeQuestion(parts[0] || ""), normalizeQuestion(parts[1] || "")];
  };
  const canonicalLanguages = new Map(profile.languages.map(languageParts));
  if (Array.isArray(observed.languages)) {
    for (const item of observed.languages) {
      const [name, level] = languageParts(item);
      const expected = canonicalLanguages.get(name);
      if (name && level && expected && level !== expected) {
        issues.push({ code: "INCONSISTENT_LANGUAGE_FLUENCY", field: "languages", message: `Language fluency for ${name} conflicts with the verified profile.`, observed: item, expected });
      }
    }
  }
  const authorization = observed.work_authorization_answers;
  if (authorization && typeof authorization === "object" && !Array.isArray(authorization)) {
    for (const [key, rawValues] of Object.entries(authorization as Record<string, unknown>)) {
      const values = Array.isArray(rawValues) ? rawValues : [rawValues];
      const normalized = new Set(values.filter((value) => String(value).trim()).map((value) => normalizeQuestion(String(value))));
      if (normalized.size > 1) issues.push({ code: "CONTRADICTORY_WORK_AUTHORIZATION", field: key, message: "The page contains contradictory work-authorization answers.", observed: values });
      const joined = [...normalized].join(" ");
      if (key === "US_WORK_AUTHORIZATION") {
        const portalAuthorized = /legally authorized|authorized to work for any employer/.test(joined) && !/not currently authorized/.test(joined);
        const portalNotAuthorized = /not currently authorized/.test(joined);
        if ((profile.work_authorization.us_work_authorized && portalNotAuthorized) || (!profile.work_authorization.us_work_authorized && portalAuthorized)) {
          issues.push({ code: "WORK_AUTHORIZATION_PROFILE_CONFLICT", field: key, message: "U.S. work authorization conflicts with the verified candidate profile.", observed: values, expected: profile.work_authorization.us_work_authorized ? "Yes" : "No" });
        }
      }
      if (key === "US_SPONSORSHIP_REQUIRED" && /require sponsorship/.test(joined) !== profile.work_authorization.requires_us_employment_sponsorship) {
        issues.push({ code: "SPONSORSHIP_PROFILE_CONFLICT", field: key, message: "Sponsorship answer conflicts with the verified candidate profile.", observed: values, expected: profile.work_authorization.requires_us_employment_sponsorship ? "Yes" : "No" });
      }
    }
  }
  return issues;
}
