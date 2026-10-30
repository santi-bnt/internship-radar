"use client";

import { Plus, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, formatDate } from "@/lib/api";
import type { AISettings, ExternalAIAudit, TargetCompany, TargetSearchRun } from "@/lib/types";

const splitValues = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

export default function SettingsPage() {
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [drafts, setDrafts] = useState<Record<number, TargetCompany>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<number | "all" | "add" | "privacy" | null>(null);
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null);
  const [privacyActivity, setPrivacyActivity] = useState<ExternalAIAudit[]>([]);
  const [newCompany, setNewCompany] = useState<{
    company_name: string;
    aliases: string;
    careers_domains: string;
    category: string;
    priority: "high" | "medium" | "low";
  }>({
    company_name: "",
    aliases: "",
    careers_domains: "",
    category: "Other",
    priority: "medium",
  });

  const load = useCallback(async () => {
    try {
      const items = await api<TargetCompany[]>("/api/target-companies");
      setCompanies(items);
      setDrafts(Object.fromEntries(items.map((item) => [item.id, item])));
      const [settingsResult, activityResult] = await Promise.allSettled([
        api<AISettings>("/api/ai-settings"),
        api<ExternalAIAudit[]>("/api/ai-privacy-activity"),
      ]);
      if (settingsResult.status === "fulfilled") setAiSettings(settingsResult.value);
      if (activityResult.status === "fulfilled") setPrivacyActivity(activityResult.value);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not load target companies.");
    }
  }, []);

  async function saveAiSettings() {
    if (!aiSettings) return;
    setBusy("privacy");
    try {
      const saved = await api<AISettings>("/api/ai-settings", {
        method: "PUT",
        body: JSON.stringify({ ai_mode: aiSettings.ai_mode }),
      });
      setAiSettings(saved);
      setMessage("AI privacy settings saved.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not save AI privacy settings.");
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => { void load(); }, [load]);

  function updateDraft(id: number, changes: Partial<TargetCompany>) {
    setDrafts((current) => ({ ...current, [id]: { ...current[id], ...changes } }));
  }

  async function saveCompany(id: number) {
    setBusy(id);
    try {
      const draft = drafts[id];
      await api<TargetCompany>(`/api/target-companies/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          company_name: draft.company_name,
          aliases: draft.aliases,
          careers_domains: draft.careers_domains,
          category: draft.category,
          priority: draft.priority,
          enabled: draft.enabled,
          preferred_locations: draft.preferred_locations,
          preferred_role_categories: draft.preferred_role_categories,
        }),
      });
      setMessage(`${draft.company_name} saved.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not save company.");
    } finally {
      setBusy(null);
    }
  }

  async function searchCompany(id: number) {
    setBusy(id);
    try {
      const run = await api<TargetSearchRun>(`/api/target-companies/${id}/search`, { method: "POST" });
      setMessage(`Search complete: ${run.jobs_discovered} discovered, ${run.jobs_added} added.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Target search failed.");
    } finally {
      setBusy(null);
    }
  }

  async function searchAll() {
    setBusy("all");
    try {
      const run = await api<TargetSearchRun>("/api/target-companies/search", { method: "POST" });
      setMessage(`${run.companies_checked} companies checked; ${run.jobs_added} new jobs.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Target search failed.");
    } finally {
      setBusy(null);
    }
  }

  async function addCompany() {
    if (!newCompany.company_name.trim()) return;
    setBusy("add");
    try {
      await api<TargetCompany>("/api/target-companies", {
        method: "POST",
        body: JSON.stringify({
          company_name: newCompany.company_name.trim(),
          aliases: splitValues(newCompany.aliases || newCompany.company_name),
          careers_domains: splitValues(newCompany.careers_domains),
          category: newCompany.category,
          priority: newCompany.priority,
          enabled: true,
          preferred_locations: [],
          preferred_role_categories: [],
        }),
      });
      setNewCompany({ company_name: "", aliases: "", careers_domains: "", category: "Other", priority: "medium" });
      setMessage("Target company added.");
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not add company.");
    } finally {
      setBusy(null);
    }
  }

  async function removeCompany(id: number) {
    setBusy(id);
    try {
      await api(`/api/target-companies/${id}`, { method: "DELETE" });
      setMessage("Custom target company removed.");
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not remove company.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Search preferences</p>
          <h1>Settings</h1>
          <p className="page-subtitle">Manage priority companies without changing code.</p>
        </div>
        <button className="button primary" onClick={() => void searchAll()} disabled={busy !== null}>
          <RefreshCw size={16} /> Search now
        </button>
      </header>
      {message && <div className="notice" role="status">{message}</div>}

      <section className="content-section">
        <div className="section-heading compact"><h2>AI Application Agent</h2></div>
        <p className="page-subtitle">Local-first assistance for interpreting application forms. Final submission, passwords, MFA, CAPTCHA, assessments, and signatures always remain manual.</p>
        {aiSettings ? (
          <div className="settings-fields">
            <label>Privacy mode
              <select value={aiSettings.ai_mode} onChange={(event) => setAiSettings({ ...aiSettings, ai_mode: event.target.value as AISettings["ai_mode"] })}>
                <option value="LOCAL_ONLY">Maximum Privacy — local processing only</option>
                <option value="BALANCED">Balanced — local first, redacted fallback allowed</option>
                <option value="EXTERNAL_ALLOWED">Best Quality — external help allowed after redaction</option>
              </select>
            </label>
            <div>
              <strong>Never shared with external AI</strong>
              <p>Passwords, authentication tokens, MFA/OTP codes, CAPTCHA responses, passport or visa document numbers, government IDs, banking data, medical documents, and electronic signatures.</p>
            </div>
            <button className="button secondary" onClick={() => void saveAiSettings()} disabled={busy !== null}><Save size={15} /> Save privacy mode</button>
          </div>
        ) : <p>AI privacy controls are unavailable until the application-agent database update finishes.</p>}
        <div className="target-company-meta">
          <span>External AI activity: {privacyActivity.length ? `${privacyActivity.length} recent call${privacyActivity.length === 1 ? "" : "s"}` : "None — no data sent"}</span>
          {privacyActivity[0] && <span>Last: {formatDate(privacyActivity[0].created_at)} · {privacyActivity[0].provider} · {privacyActivity[0].fields_redacted_json.length} fields redacted</span>}
        </div>
      </section>

      <section className="content-section target-add-form">
        <div className="section-heading compact"><h2>Target Companies</h2></div>
        <div className="settings-add-grid">
          <input placeholder="Company name" value={newCompany.company_name} onChange={(event) => setNewCompany({ ...newCompany, company_name: event.target.value })} />
          <input placeholder="Aliases, comma separated" value={newCompany.aliases} onChange={(event) => setNewCompany({ ...newCompany, aliases: event.target.value })} />
          <input placeholder="Verified careers URLs" value={newCompany.careers_domains} onChange={(event) => setNewCompany({ ...newCompany, careers_domains: event.target.value })} />
          <select value={newCompany.priority} onChange={(event) => setNewCompany({ ...newCompany, priority: event.target.value as "high" | "medium" | "low" })}>
            <option value="high">High priority</option><option value="medium">Medium priority</option><option value="low">Low priority</option>
          </select>
          <button className="button secondary" onClick={() => void addCompany()} disabled={busy !== null}><Plus size={16} /> Add</button>
        </div>
      </section>

      <div className="target-company-grid">
        {companies.map((company) => {
          const draft = drafts[company.id] ?? company;
          return (
            <section className="content-section target-company-card" key={company.id}>
              <div className="target-company-title">
                <div>
                  <h2>{company.company_name}</h2>
                  <span>{company.category} · {company.open_jobs_count} open jobs</span>
                </div>
                <label className="toggle-label">
                  <input type="checkbox" checked={draft.enabled} onChange={(event) => updateDraft(company.id, { enabled: event.target.checked })} />
                  Enabled
                </label>
              </div>
              <div className="settings-fields">
                <label>Priority<select value={draft.priority} onChange={(event) => updateDraft(company.id, { priority: event.target.value as TargetCompany["priority"] })}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
                <label>Category<input value={draft.category} onChange={(event) => updateDraft(company.id, { category: event.target.value })} /></label>
                <label>Aliases<textarea rows={2} value={draft.aliases.join(", ")} onChange={(event) => updateDraft(company.id, { aliases: splitValues(event.target.value) })} /></label>
                <label>Career URLs<textarea rows={2} value={draft.careers_domains.join(", ")} onChange={(event) => updateDraft(company.id, { careers_domains: splitValues(event.target.value) })} /></label>
                <label>Role categories<textarea rows={2} value={draft.preferred_role_categories.join(", ")} onChange={(event) => updateDraft(company.id, { preferred_role_categories: splitValues(event.target.value) })} /></label>
                <label>Locations<textarea rows={2} value={draft.preferred_locations.join(", ")} onChange={(event) => updateDraft(company.id, { preferred_locations: splitValues(event.target.value) })} /></label>
              </div>
              <div className="target-company-meta">
                <span>Last checked: {formatDate(company.last_checked_at)}</span>
                <span>Last result: {formatDate(company.last_successful_result_at)}</span>
              </div>
              <div className="header-actions">
                <button className="button secondary" onClick={() => void saveCompany(company.id)} disabled={busy !== null}><Save size={15} /> Save</button>
                <button className="button secondary" onClick={() => void searchCompany(company.id)} disabled={busy !== null}><Search size={15} /> Search now</button>
                {company.custom && <button className="button ghost" onClick={() => void removeCompany(company.id)} disabled={busy !== null}><Trash2 size={15} /> Delete</button>}
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
}
