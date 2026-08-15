"use client";

import { Building2, ExternalLink, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { api, formatDate } from "@/lib/api";
import type { CompanySource } from "@/lib/types";

const emptyForm = {
  company: "",
  source_type: "greenhouse",
  source_identifier: "",
  source_url: "",
  enabled: true,
  registry_type: "OFFICIAL_ATS",
  priority: 90,
  base_priority: 90,
  trust_level: "PRIMARY",
  refresh_frequency: "daily",
  supports_structured_data: true,
  notes: "",
  source_confidence_score: 95,
  reference_only: false,
};

export default function SourcesPage() {
  const [sources, setSources] = useState<CompanySource[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setSources(await api<CompanySource[]>("/api/sources"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load sources.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visibleSources = useMemo(
    () => sources.filter((source) => source.company.toLowerCase().includes(query.toLowerCase())),
    [sources, query],
  );

  async function addSource(event: FormEvent) {
    event.preventDefault();
    try {
      await api<CompanySource>("/api/sources", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm(emptyForm);
      setMessage("Source added.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add source.");
    }
  }

  async function toggleSource(source: CompanySource) {
    try {
      const updated = await api<CompanySource>(`/api/sources/${source.id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      setSources((current) => current.map((item) => item.id === source.id ? updated : item));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update source.");
    }
  }

  async function deleteSource(id: number) {
    try {
      await api(`/api/sources/${id}`, { method: "DELETE" });
      setSources((current) => current.filter((source) => source.id !== id));
      setMessage("Source removed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove source.");
    }
  }

  async function refresh() {
    setRefreshing(true);
    try {
      const result = await api<{ jobs_created: number; jobs_updated: number; errors: unknown[] }>(
        "/api/sources/refresh",
        { method: "POST" },
      );
      setMessage(`${result.jobs_created} new jobs, ${result.jobs_updated} refreshed, ${result.errors.length} errors.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Discovery inputs</p>
          <h1>Discovery Sources</h1>
          <p className="page-subtitle">Official feeds, ATS boards, and community repositories with separate verification standards.</p>
        </div>
        <button className="button primary" onClick={refresh} disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? "spin" : ""} />
          {refreshing ? "Refreshing" : "Refresh enabled"}
        </button>
      </header>

      {message && <div className="notice" role="status">{message}</div>}

      <section className="source-add form-section">
        <div className="form-section-title"><Plus size={18} /><h2>Add a source</h2></div>
        <form className="source-form" onSubmit={addSource}>
          <label>Company<input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></label>
          <label>
            Adapter
            <select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="workday">Workday</option>
              <option value="smartrecruiters">SmartRecruiters</option>
              <option value="amazon_jobs">Amazon Jobs</option>
              <option value="official_careers">Official careers</option>
              <option value="oracle_recruiting">Oracle Recruiting</option>
              <option value="embedded_jobs">EmbeddedJobs</option>
              <option value="community_repo">Community repository</option>
              <option value="manual_watchlist">Watchlist only</option>
            </select>
          </label>
          <label>Board token / company slug<input required value={form.source_identifier} onChange={(e) => setForm({ ...form, source_identifier: e.target.value })} /></label>
          <label>Official careers URL<input required type="url" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} /></label>
          <label>
            Registry type
            <select value={form.registry_type} onChange={(e) => setForm({ ...form, registry_type: e.target.value })}>
              {['OFFICIAL_COMPANY', 'OFFICIAL_ATS', 'COMMUNITY_REPO', 'AGGREGATOR', 'JOB_BOARD', 'UNIVERSITY_BOARD', 'OTHER'].map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label>
            Trust level
            <select value={form.trust_level} onChange={(e) => setForm({ ...form, trust_level: e.target.value })}>
              {['PRIMARY', 'HIGH', 'MEDIUM', 'LOW'].map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label>Priority<input type="number" min="0" max="100" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value), base_priority: Number(e.target.value) })} /></label>
          <button className="button secondary" type="submit"><Plus size={16} /> Add source</button>
        </form>
      </section>

      <section className="content-section">
        <div className="section-heading source-heading">
          <div>
            <h2>Source registry</h2>
            <p>{sources.filter((source) => source.enabled).length} enabled of {sources.length} configured.</p>
          </div>
          <label className="search-field compact-search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter companies" />
          </label>
        </div>
        <div className="source-list">
          {visibleSources.map((source) => (
            <div className="source-row" key={source.id}>
              <span className="source-logo"><Building2 size={18} /></span>
              <div className="source-name">
                <strong>{source.company}</strong>
                <span>{source.registry_type.replaceAll("_", " ")} · {source.trust_level} trust · priority {source.priority}</span>
                <span>{source.source_type.replaceAll("_", " ")} · {source.source_identifier}</span>
                <span>{source.parsed_count} parsed · {source.new_jobs_count} new · {source.duplicate_count} duplicates</span>
                <span>{source.officially_verified_count} verified · {source.unverified_count} unverified · {source.error_count} errors</span>
              </div>
              <div className="source-status">
                <span className={`status-dot ${source.last_status === "Error" ? "error" : source.enabled ? "ok" : ""}`} />
                <div>
                  <strong>{source.source_status}</strong>
                  <span>{source.last_refresh_at ? formatDate(source.last_refresh_at) : "Not refreshed"}</span>
                  <span>{source.duration_ms ? `${source.duration_ms} ms` : "No duration"}</span>
                </div>
              </div>
              <label className="switch" title={source.enabled ? "Disable source" : "Enable source"}>
                <input type="checkbox" checked={source.enabled} onChange={() => void toggleSource(source)} />
                <span />
              </label>
              {source.source_url.startsWith("https://") && !source.source_url.includes("example.com") && (
                <a
                  className="icon-button"
                  href={source.source_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Open ${source.company} careers page`}
                  title="Open official careers page"
                >
                  <ExternalLink size={16} />
                </a>
              )}
              <button className="icon-button danger" onClick={() => void deleteSource(source.id)} aria-label={`Remove ${source.company}`}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
