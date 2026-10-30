"use client";

import { Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ApplicationProfile } from "@/lib/types";

export default function ApplicationProfileSection() {
  const [profile, setProfile] = useState<ApplicationProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api<ApplicationProfile>("/api/application-profile")
      .then(setProfile)
      .catch((error: Error) => setMessage(error.message));
  }, []);

  function update<K extends keyof ApplicationProfile>(key: K, value: ApplicationProfile[K]) {
    setProfile((current) => current ? { ...current, [key]: value } : current);
  }

  async function save() {
    if (!profile) return;
    setSaving(true);
    setMessage("");
    const payload = Object.fromEntries(
      Object.entries(profile).filter(([key]) => !["id", "owner_user_id", "created_at", "updated_at"].includes(key)),
    );
    try {
      setProfile(await api<ApplicationProfile>("/api/application-profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }));
      setMessage("Verified application profile saved.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Application profile could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  if (!profile) {
    return <section className="form-section"><h2>Application Profile</h2><p>{message || "Loading verified application fields…"}</p></section>;
  }

  return (
    <section className="form-section application-profile-section">
      <div className="form-section-title"><ShieldCheck size={19} /><h2>Application Profile</h2></div>
      <p className="section-description">Canonical verified fields used by Apply Assistant. Recognized stable eligibility answers may be filled from this profile and are always shown again before manual submission.</p>
      {message && <div className="notice" role="status">{message}</div>}
      <div className="form-grid two">
        <label>Full name<input value={profile.full_name} onChange={(event) => update("full_name", event.target.value)} /></label>
        <label>Professional email<input type="email" value={profile.professional_email} onChange={(event) => update("professional_email", event.target.value)} /></label>
        <label>Phone<input value={profile.phone} onChange={(event) => update("phone", event.target.value)} /></label>
        <label>Country<input value={profile.country} onChange={(event) => update("country", event.target.value)} /></label>
        <label>Address line 1<input value={profile.address_line1} onChange={(event) => update("address_line1", event.target.value)} /></label>
        <label>Address line 2<input value={profile.address_line2} onChange={(event) => update("address_line2", event.target.value)} /></label>
        <label>City<input value={profile.city} onChange={(event) => update("city", event.target.value)} /></label>
        <label>State / region<input value={profile.state} onChange={(event) => update("state", event.target.value)} /></label>
        <label>Postal code<input value={profile.postal_code} onChange={(event) => update("postal_code", event.target.value)} /></label>
        <label>University<input value={profile.university} onChange={(event) => update("university", event.target.value)} /></label>
        <label>Degree<input value={profile.degree} onChange={(event) => update("degree", event.target.value)} /></label>
        <label>Field of study<input value={profile.field_of_study} onChange={(event) => update("field_of_study", event.target.value)} /></label>
        <label>Education start date<input type="date" value={profile.education_start_date ?? ""} onChange={(event) => update("education_start_date", event.target.value || null)} /></label>
        <label>Expected graduation<input type="date" value={profile.expected_graduation_date ?? ""} onChange={(event) => update("expected_graduation_date", event.target.value || null)} /></label>
        <label>GPA<input type="number" step="0.01" value={profile.gpa ?? ""} onChange={(event) => update("gpa", event.target.value ? Number(event.target.value) : null)} /></label>
        <label>GPA scale<input type="number" step="0.01" value={profile.gpa_scale ?? ""} onChange={(event) => update("gpa_scale", event.target.value ? Number(event.target.value) : null)} /></label>
        <label>LinkedIn URL<input value={profile.linkedin_url} onChange={(event) => update("linkedin_url", event.target.value)} /></label>
        <label>GitHub URL<input value={profile.github_url} onChange={(event) => update("github_url", event.target.value)} /></label>
        <label>Verified languages<textarea rows={4} value={profile.languages_json.join("\n")} onChange={(event) => update("languages_json", event.target.value.split("\n").map((item) => item.trim()).filter(Boolean))} /></label>
        <label>Verified skills<textarea rows={4} value={profile.skills_json.join(", ")} onChange={(event) => update("skills_json", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} /></label>
        <label>How you usually find jobs
          <select value={profile.job_discovery_source} onChange={(event) => update("job_discovery_source", event.target.value)}>
            <option value="GOOGLE_SEARCH">Google Search</option>
          </select>
        </label>
      </div>
      <label className="checkbox-row">
        <input type="checkbox" checked={profile.full_time_summer_availability} onChange={(event) => update("full_time_summer_availability", event.target.checked)} />
        Available for a full-time onsite summer internship
      </label>
      <label className="checkbox-row">
        <input type="checkbox" checked={profile.spring_summer_combined_availability} onChange={(event) => update("spring_summer_combined_availability", event.target.checked)} />
        Available for a combined Spring + Summer internship
      </label>
      <label className="checkbox-row">
        <input type="checkbox" checked={profile.academic_project_workaround_allowed} onChange={(event) => update("academic_project_workaround_allowed", event.target.checked)} />
        Allow clearly disclosed “Academic &amp; Personal Projects” only when a portal requires a work-experience entry
      </label>
      <p className="status-reason">Projects are never represented as professional employment. If enabled, the assistant includes the explicit disclosure “not professional employment.”</p>
      <button className="button secondary" onClick={() => void save()} disabled={saving}><Save size={16} /> {saving ? "Saving" : "Save Application Profile"}</button>
    </section>
  );
}
