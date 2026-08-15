"use client";

import { Mail, Save, Send, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { EmailActionResult, Profile, ResumeProfile, VerifiedSkillGroup } from "@/lib/types";

function linesToMap(text: string): Record<string, string> {
  return Object.fromEntries(
    text
      .split("\n")
      .map((line) => line.split(":"))
      .filter(([key, ...rest]) => key.trim() && rest.join(":").trim())
      .map(([key, ...rest]) => [key.trim(), rest.join(":").trim()]),
  );
}

function parseCourseworkLines(text: string): Array<string | Record<string, unknown>> {
  return text.split("\n").map((value) => value.trim()).filter(Boolean).map((value) => {
    try {
      const parsed: unknown = JSON.parse(value);
      return parsed && typeof parsed === "object"
        ? parsed as Record<string, unknown>
        : value;
    } catch {
      return value;
    }
  });
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  const [resumeProfile, setResumeProfile] = useState<ResumeProfile | null>(null);
  const [verifiedSkillGroups, setVerifiedSkillGroups] = useState<VerifiedSkillGroup[]>([]);

  const loadVerifiedSkills = useCallback(async () => {
    setVerifiedSkillGroups(
      await api<VerifiedSkillGroup[]>("/api/resume-profile/verified-skills"),
    );
  }, []);

  useEffect(() => {
    api<Profile>("/api/profile")
      .then(setProfile)
      .catch((error: Error) => setMessage(error.message));
    api<ResumeProfile>("/api/resume-profile")
      .then(setResumeProfile)
      .catch((error: Error) => setMessage(error.message));
    void loadVerifiedSkills().catch((error: Error) => setMessage(error.message));
  }, [loadVerifiedSkills]);

  function update<K extends keyof Profile>(key: K, value: Profile[K]) {
    setProfile((current) => (current ? { ...current, [key]: value } : current));
  }

  async function saveProfile() {
    if (!profile) return;
    setSaving(true);
    const payload = Object.fromEntries(
      Object.entries(profile).filter(([key]) => !["id", "updated_at"].includes(key)),
    );
    try {
      setProfile(await api<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(payload) }));
      setMessage("Profile saved. Reanalyze jobs to apply the changes.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save profile.");
    } finally {
      setSaving(false);
    }
  }

  function updateResume<K extends keyof ResumeProfile>(key: K, value: ResumeProfile[K]) {
    setResumeProfile((current) => (current ? { ...current, [key]: value } : current));
  }

  async function saveResumeProfile() {
    if (!resumeProfile) return;
    setSaving(true);
    const payload = Object.fromEntries(
      Object.entries(resumeProfile).filter(
        ([key]) => !["id", "user_id", "created_at", "updated_at"].includes(key),
      ),
    );
    try {
      setResumeProfile(await api<ResumeProfile>("/api/resume-profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }));
      await loadVerifiedSkills();
      setMessage("Resume Profile saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save Resume Profile.");
    } finally {
      setSaving(false);
    }
  }

  async function sendTestEmail() {
    if (!profile) return;
    setTestingEmail(true);
    const payload = Object.fromEntries(
      Object.entries(profile).filter(([key]) => !["id", "updated_at"].includes(key)),
    );
    try {
      const saved = await api<Profile>("/api/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setProfile(saved);
      const result = await api<EmailActionResult>("/api/notifications/test-email", {
        method: "POST",
      });
      setMessage(`${result.message} Provider: ${result.provider}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not send the test email.");
    } finally {
      setTestingEmail(false);
    }
  }

  if (!profile) return <div className="empty-state">{message || "Loading profile…"}</div>;

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Scoring input</p>
          <h1>Profile</h1>
          <p className="page-subtitle">The evidence used for fit, eligibility, and resume recommendations.</p>
        </div>
        <button className="button primary" onClick={saveProfile} disabled={saving}>
          <Save size={16} /> {saving ? "Saving" : "Save profile"}
        </button>
      </header>

      {message && <div className="notice" role="status">{message}</div>}

      <div className="profile-layout">
        {resumeProfile && (
          <section className="form-section resume-profile-section">
            <div className="form-section-title"><UserRound size={19} /><h2>Resume Profile</h2></div>
            <p className="section-description">Verified facts available to the tailored-resume generator. Leave unconfirmed information empty.</p>
            <div className="verified-skills-panel">
              <h3>Verified Skills</h3>
              <p>Read-only canonical registry built from explicit profile, project, course, and experience evidence.</p>
              <div className="verified-skill-groups">
                {verifiedSkillGroups.map((group) => (
                  <div key={group.name}>
                    <strong>{group.name}</strong>
                    <div className="resume-chips">
                      {group.items.map((item) => (
                        <span key={item.skill} title={item.evidence.join("; ")}>{item.skill}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="form-grid two">
              <label>Resume name<input value={resumeProfile.full_name} onChange={(event) => updateResume("full_name", event.target.value)} /></label>
              <label>Email<input type="email" value={resumeProfile.email} onChange={(event) => updateResume("email", event.target.value)} /></label>
              <label>Phone<input value={resumeProfile.phone} onChange={(event) => updateResume("phone", event.target.value)} /></label>
              <label>Location<input value={resumeProfile.location} onChange={(event) => updateResume("location", event.target.value)} /></label>
              <label>LinkedIn URL<input value={resumeProfile.linkedin_url} onChange={(event) => updateResume("linkedin_url", event.target.value)} /></label>
              <label>GitHub URL<input value={resumeProfile.github_url} onChange={(event) => updateResume("github_url", event.target.value)} /></label>
              <label>Headline<input value={resumeProfile.headline} onChange={(event) => updateResume("headline", event.target.value)} /></label>
              <label>Languages<textarea rows={3} value={resumeProfile.languages_json.join("\n")} onChange={(event) => updateResume("languages_json", event.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} /></label>
              <label>Verified summary<textarea rows={5} value={resumeProfile.summary} onChange={(event) => updateResume("summary", event.target.value)} /></label>
              <label>Explicit verified skill records<textarea rows={5} value={resumeProfile.skills_json.join(", ")} onChange={(event) => updateResume("skills_json", event.target.value.split(",").map((value) => value.trim()).filter(Boolean))} /></label>
              <label>Coursework<textarea rows={6} value={resumeProfile.coursework_json.map((value) => typeof value === "string" ? value : JSON.stringify(value)).join("\n")} onChange={(event) => updateResume("coursework_json", parseCourseworkLines(event.target.value))} /></label>
              <label>Forbidden or unconfirmed claims<textarea rows={4} value={resumeProfile.forbidden_claims_json.join("\n")} onChange={(event) => updateResume("forbidden_claims_json", event.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} /></label>
            </div>
            <button className="button secondary" onClick={() => void saveResumeProfile()} disabled={saving}><Save size={16} /> Save Resume Profile</button>
          </section>
        )}
        <section className="form-section">
          <div className="form-section-title"><UserRound size={19} /><h2>Candidate</h2></div>
          <div className="form-grid two">
            <label>Full name<input value={profile.full_name} onChange={(e) => update("full_name", e.target.value)} /></label>
            <label>Nationality<input value={profile.nationality} onChange={(e) => update("nationality", e.target.value)} /></label>
            <label>Citizenship country<input value={profile.citizenship_country} onChange={(e) => update("citizenship_country", e.target.value)} /></label>
            <label>Degree<input value={profile.degree} onChange={(e) => update("degree", e.target.value)} /></label>
            <label>University<input value={profile.university} onChange={(e) => update("university", e.target.value)} /></label>
            <label>Graduation year<input type="number" value={profile.graduation_year} onChange={(e) => update("graduation_year", Number(e.target.value))} /></label>
            <label>Graduation date<input type="date" value={profile.graduation_date ?? ""} onChange={(e) => update("graduation_date", e.target.value || null)} /></label>
            <label>
              Current degree level
              <select value={profile.degree_level_current} onChange={(e) => update("degree_level_current", e.target.value as Profile["degree_level_current"])}>
                <option value="BACHELORS">Bachelor&apos;s</option>
                <option value="MASTERS">Master&apos;s</option>
                <option value="PHD">PhD / Doctorate</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
            </label>
            <label>
              Degree status
              <select value={profile.degree_status} onChange={(e) => update("degree_status", e.target.value as Profile["degree_status"])}>
                <option value="IN_PROGRESS">In progress</option>
                <option value="COMPLETED">Completed</option>
                <option value="EXPECTED_BEFORE_START">Expected before job start</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
            </label>
            <label>Expected graduation date<input type="date" value={profile.expected_graduation_date ?? ""} onChange={(e) => update("expected_graduation_date", e.target.value || null)} /></label>
            <label>Canonical degree field<input value={profile.degree_field} onChange={(e) => update("degree_field", e.target.value)} /></label>
            <label>GPA<input type="number" step="0.01" value={profile.gpa} onChange={(e) => update("gpa", Number(e.target.value))} /></label>
            <label>GPA scale<input type="number" value={profile.gpa_scale} onChange={(e) => update("gpa_scale", Number(e.target.value))} /></label>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={profile.willing_to_relocate} onChange={(e) => update("willing_to_relocate", e.target.checked)} />
            Willing to relocate
          </label>
        </section>

        <section className="form-section">
          <h2>Skills and target roles</h2>
          <div className="form-grid two">
            <label>
              Skills
              <textarea rows={8} value={profile.skills.join(", ")} onChange={(e) => update("skills", e.target.value.split(",").map((value) => value.trim()).filter(Boolean))} />
            </label>
            <label>
              Preferred roles
              <textarea rows={8} value={profile.preferred_roles.join("\n")} onChange={(e) => update("preferred_roles", e.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} />
            </label>
          </div>
        </section>

        <section className="form-section">
          <h2>Special program eligibility</h2>
          <p className="status-reason">
            These explicit values are used only when a posting restricts participation to a special group. Internship Radar never infers protected status from other profile data.
          </p>
          <div className="form-grid two">
            <label>
              Veteran status
              <select value={profile.veteran_status} onChange={(event) => update("veteran_status", event.target.value as Profile["veteran_status"])}>
                <option value="NOT_VETERAN">Not a veteran</option>
                <option value="VETERAN">Veteran</option>
                <option value="UNKNOWN">Prefer not to specify / unknown</option>
              </select>
            </label>
            <label>
              Military status
              <select value={profile.military_status} onChange={(event) => update("military_status", event.target.value as Profile["military_status"])}>
                <option value="NONE">None</option>
                <option value="ACTIVE_DUTY">Active duty</option>
                <option value="TRANSITIONING_SERVICE_MEMBER">Transitioning service member</option>
                <option value="VETERAN">Veteran</option>
                <option value="UNKNOWN">Prefer not to specify / unknown</option>
              </select>
            </label>
            <label>
              Disability status
              <select value={profile.disability_status} onChange={(event) => update("disability_status", event.target.value as Profile["disability_status"])}>
                <option value="NO_DISABILITY">No disability</option>
                <option value="HAS_DISABILITY">Person with a disability</option>
                <option value="UNKNOWN">Prefer not to specify / unknown</option>
              </select>
            </label>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={profile.military_spouse} onChange={(event) => update("military_spouse", event.target.checked)} />
            Military spouse
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={profile.current_service_member} onChange={(event) => update("current_service_member", event.target.checked)} />
            Current service member
          </label>
        </section>

        <section className="form-section">
          <h2>Location and authorization</h2>
          <div className="form-grid two">
            <label>
              Preferred locations
              <textarea rows={5} value={profile.preferred_locations.join("\n")} onChange={(e) => update("preferred_locations", e.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} />
            </label>
            <label>
              Work authorization
              <textarea rows={5} value={Object.entries(profile.work_authorizations).map(([key, value]) => `${key}: ${value}`).join("\n")} onChange={(e) => update("work_authorizations", linesToMap(e.target.value))} />
            </label>
            <label>
              Countries where currently authorized to work
              <textarea rows={3} value={profile.work_authorized_countries.join("\n")} onChange={(e) => update("work_authorized_countries", e.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} />
            </label>
            <label>
              Visas
              <textarea rows={3} value={profile.visas.join("\n")} onChange={(e) => update("visas", e.target.value.split("\n").map((value) => value.trim()).filter(Boolean))} />
            </label>
            <label>
              Education notes
              <textarea rows={3} value={profile.education_notes} onChange={(e) => update("education_notes", e.target.value)} />
            </label>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={profile.us_work_authorized} onChange={(e) => update("us_work_authorized", e.target.checked)} />
            Currently authorized to work in the United States
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={profile.requires_us_employment_sponsorship} onChange={(e) => update("requires_us_employment_sponsorship", e.target.checked)} />
            Requires U.S. employment sponsorship now or in the future
          </label>
        </section>

        <section className="form-section">
          <h2>Search settings</h2>
          <div className="settings-grid">
            <fieldset className="settings-group">
              <legend>Countries to search</legend>
              {["Mexico", "United States", "Canada"].map((country) => (
                <label className="checkbox-row" key={country}>
                  <input
                    type="checkbox"
                    checked={profile.countries_to_search.includes(country)}
                    onChange={() => update(
                      "countries_to_search",
                      profile.countries_to_search.includes(country)
                        ? profile.countries_to_search.filter((item) => item !== country)
                        : [...profile.countries_to_search, country],
                    )}
                  />
                  {country}
                </label>
              ))}
            </fieldset>
            <fieldset className="settings-group">
              <legend>Remote preferences</legend>
              {[
                ["include_remote", "Include remote jobs"],
                ["only_remote", "Only remote jobs"],
                ["remote_from_mexico_only", "Only remote jobs confirmed from Mexico"],
                ["include_hybrid", "Include hybrid jobs"],
                ["include_onsite", "Include on-site jobs"],
              ].map(([key, label]) => (
                <label className="checkbox-row" key={key}>
                  <input
                    type="checkbox"
                    checked={Boolean(profile[key as keyof Profile])}
                    onChange={(event) => update(key as keyof Profile, event.target.checked as never)}
                  />
                  {label}
                </label>
              ))}
            </fieldset>
            <fieldset className="settings-group">
              <legend>Priority alerts</legend>
              {[
                ["priority_alerts", "Enable priority alerts"],
                ["alert_for_major_companies", "Alert for major companies"],
                ["alert_for_deadlines", "Alert for deadlines"],
                ["immediate_priority_alerts", "Immediate priority alerts"],
              ].map(([key, label]) => (
                <label className="checkbox-row" key={key}>
                  <input
                    type="checkbox"
                    checked={Boolean(profile[key as keyof Profile])}
                    onChange={(event) => update(key as keyof Profile, event.target.checked as never)}
                  />
                  {label}
                </label>
              ))}
              <div className="threshold-row">
                <label>
                  Minimum score
                  <input type="number" min="0" max="100" value={profile.priority_minimum_score} onChange={(event) => update("priority_minimum_score", Number(event.target.value))} />
                </label>
                <label>
                  Major company score
                  <input type="number" min="0" max="100" value={profile.major_company_minimum_score} onChange={(event) => update("major_company_minimum_score", Number(event.target.value))} />
                </label>
              </div>
            </fieldset>
          </div>
        </section>

        <section className="form-section">
          <div className="form-section-title"><Mail size={19} /><h2>Email notifications</h2></div>
          <div className="email-settings-layout">
            <div className="email-preferences">
              {[
                ["email_notifications", "Enable email notifications"],
                ["priority_email_alerts", "Priority alerts"],
                ["major_company_email_alerts", "Major company alerts"],
                ["deadline_alerts", "Deadline alerts"],
                ["daily_digest", "Daily digest"],
                ["application_follow_up_alerts", "Application follow-up reminders"],
              ].map(([key, label]) => (
                <label className="checkbox-row" key={key}>
                  <input
                    type="checkbox"
                    checked={Boolean(profile[key as keyof Profile])}
                    onChange={(event) => update(key as keyof Profile, event.target.checked as never)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="email-fields">
              <label>
                Recipient email
                <input
                  type="email"
                  value={profile.notification_email}
                  onChange={(event) => update("notification_email", event.target.value)}
                />
              </label>
              <label>
                Minimum score for email alert
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={profile.email_minimum_score}
                  onChange={(event) => update("email_minimum_score", Number(event.target.value))}
                />
              </label>
              <div className="email-test-action">
                <button
                  className="button secondary"
                  onClick={() => void sendTestEmail()}
                  disabled={testingEmail}
                >
                  <Send size={16} /> {testingEmail ? "Sending" : "Send test email"}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="form-section">
          <h2>Projects</h2>
          <div className="project-list">
            {profile.projects.map((project, index) => (
              <div className="project-row" key={`${project.name}-${index}`}>
                <input
                  aria-label={`Project ${index + 1} name`}
                  value={project.name}
                  onChange={(e) => update("projects", profile.projects.map((item, itemIndex) => itemIndex === index ? { ...item, name: e.target.value } : item))}
                />
                <textarea
                  rows={2}
                  aria-label={`Project ${index + 1} details`}
                  value={project.details}
                  onChange={(e) => update("projects", profile.projects.map((item, itemIndex) => itemIndex === index ? { ...item, details: e.target.value } : item))}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
