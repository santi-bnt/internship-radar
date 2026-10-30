"use client";

import { Clock3, History, Plus, Search, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  cloneSearchCriteria,
  COMPANY_SUGGESTIONS,
  DEFAULT_SEARCH_CRITERIA,
  REMOTE_SCOPE_LABELS,
  ROLE_OPTIONS,
  SEARCH_PRESETS,
  searchHistoryLabel,
} from "@/lib/job-search";
import type {
  SearchCriteria,
  SearchRemoteScope,
  SearchRoleCategory,
  SearchRun,
  SearchWorkModel,
  TargetCompany,
} from "@/lib/types";

type Props = {
  open: boolean;
  initialCriteria?: SearchCriteria | null;
  targetCompanies: TargetCompany[];
  recentSearches: SearchRun[];
  submitting: boolean;
  onClose: () => void;
  onSubmit: (criteria: SearchCriteria) => void;
  onOpenSearch: (run: SearchRun) => void;
  onRunAgain: (run: SearchRun) => void;
  onDeleteSearch: (run: SearchRun) => void;
};

const workModels: Array<{ value: SearchWorkModel; label: string }> = [
  { value: "ANY", label: "Any" },
  { value: "REMOTE", label: "Remote" },
  { value: "HYBRID", label: "Hybrid" },
  { value: "ON_SITE", label: "On-site" },
];

const locationPresets = ["Mexico", "Guadalajara", "Jalisco", "Mexico City", "Monterrey", "Querétaro", "Tijuana"];

function toggleValue<T extends string>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function parseTags(value: string): string[] {
  return Array.from(
    new Set(value.split(",").map((item) => item.trim()).filter(Boolean)),
  );
}

export function JobSearchPanel({
  open,
  initialCriteria,
  targetCompanies,
  recentSearches,
  submitting,
  onClose,
  onSubmit,
  onOpenSearch,
  onRunAgain,
  onDeleteSearch,
}: Props) {
  const [criteria, setCriteria] = useState<SearchCriteria>(cloneSearchCriteria(DEFAULT_SEARCH_CRITERIA));
  const [customCompany, setCustomCompany] = useState("");
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCriteria(cloneSearchCriteria(initialCriteria ?? DEFAULT_SEARCH_CRITERIA));
    setCustomCompany("");
  }, [initialCriteria, open]);

  if (!open) return null;

  const knownCompanies = Array.from(
    new Set([
      ...COMPANY_SUGGESTIONS,
      ...targetCompanies.map((company) => company.company_name),
      ...criteria.companies,
    ]),
  ).slice(0, 24);
  const remoteSelected = criteria.work_models.includes("REMOTE");

  function selectWorkModel(value: SearchWorkModel) {
    setCriteria((current) => {
      if (value === "ANY") return { ...current, work_models: ["ANY"] };
      const withoutAny = current.work_models.filter((item) => item !== "ANY");
      const next = toggleValue(withoutAny, value);
      return { ...current, work_models: next.length ? next : ["ANY"] };
    });
  }

  function addCompany() {
    const company = customCompany.trim();
    if (!company) return;
    setCriteria((current) => ({
      ...current,
      target_companies_only: false,
      companies: Array.from(new Set([...current.companies, company])),
    }));
    setCustomCompany("");
  }

  function applyLocationPreset(value: string) {
    if (value === "Mexico") {
      setCriteria((current) => ({ ...current, countries: toggleValue(current.countries, value) }));
    } else if (value === "Jalisco") {
      setCriteria((current) => ({ ...current, states: toggleValue(current.states, value) }));
    } else {
      setCriteria((current) => ({ ...current, cities: toggleValue(current.cities, value) }));
    }
  }

  return (
    <div className="search-overlay" role="presentation">
      <section className="search-drawer" role="dialog" aria-modal="true" aria-labelledby="job-search-title">
        <header className="search-drawer-header">
          <div>
            <p className="eyebrow">New discovery run</p>
            <h2 id="job-search-title">Job Search</h2>
            <p>Choose what the backend should actively discover.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close job search">
            <X size={18} />
          </button>
        </header>

        <div className="search-drawer-body">
          <section className="search-presets" aria-label="Search presets">
            {SEARCH_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => setCriteria(cloneSearchCriteria(preset.criteria))}
              >
                <strong>{preset.label}</strong>
                <span>{preset.description}</span>
              </button>
            ))}
          </section>

          <fieldset className="search-fieldset">
            <legend>Companies</legend>
            <div className="chip-grid">
              <button
                type="button"
                className={`search-chip ${!criteria.companies.length && !criteria.target_companies_only ? "selected" : ""}`}
                onClick={() => setCriteria((current) => ({ ...current, companies: [], target_companies_only: false }))}
              >
                Any company
              </button>
              <button
                type="button"
                className={`search-chip ${criteria.target_companies_only ? "selected" : ""}`}
                onClick={() => setCriteria((current) => ({ ...current, companies: [], target_companies_only: !current.target_companies_only }))}
              >
                Target companies
              </button>
              {knownCompanies.map((company) => (
                <button
                  key={company}
                  type="button"
                  className={`search-chip ${criteria.companies.includes(company) ? "selected" : ""}`}
                  onClick={() => setCriteria((current) => ({
                    ...current,
                    target_companies_only: false,
                    companies: toggleValue(current.companies, company),
                  }))}
                >
                  {company}
                </button>
              ))}
            </div>
            <div className="inline-entry">
              <input
                value={customCompany}
                onChange={(event) => setCustomCompany(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addCompany();
                  }
                }}
                placeholder="Custom company"
                maxLength={100}
              />
              <button type="button" className="button secondary" onClick={addCompany}>
                <Plus size={15} /> Add company
              </button>
            </div>
          </fieldset>

          <fieldset className="search-fieldset">
            <legend>Work model</legend>
            <div className="chip-grid">
              {workModels.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`search-chip ${criteria.work_models.includes(option.value) ? "selected" : ""}`}
                  onClick={() => selectWorkModel(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>

          {remoteSelected && (
            <fieldset className="search-fieldset nested-fieldset">
              <legend>Where can you work remotely?</legend>
              <div className="chip-grid">
                {(Object.keys(REMOTE_SCOPE_LABELS) as SearchRemoteScope[]).map((scope) => (
                  <button
                    key={scope}
                    type="button"
                    className={`search-chip ${criteria.remote_scopes.includes(scope) ? "selected" : ""}`}
                    onClick={() => setCriteria((current) => ({
                      ...current,
                      remote_scopes: toggleValue(current.remote_scopes, scope),
                    }))}
                  >
                    {REMOTE_SCOPE_LABELS[scope]}
                  </button>
                ))}
              </div>
              <p className="field-help">US-only remains separate and is still subject to work-authorization rules.</p>
            </fieldset>
          )}

          <fieldset className="search-fieldset">
            <legend>Location</legend>
            <div className="chip-grid">
              {locationPresets.map((location) => {
                const selected = [...criteria.countries, ...criteria.states, ...criteria.cities].includes(location);
                return (
                  <button
                    key={location}
                    type="button"
                    className={`search-chip ${selected ? "selected" : ""}`}
                    onClick={() => applyLocationPreset(location)}
                  >
                    {location}
                  </button>
                );
              })}
            </div>
            <div className="search-grid three">
              <label>Country<input value={criteria.countries.join(", ")} onChange={(event) => setCriteria((current) => ({ ...current, countries: parseTags(event.target.value) }))} placeholder="Mexico" /></label>
              <label>State<input value={criteria.states.join(", ")} onChange={(event) => setCriteria((current) => ({ ...current, states: parseTags(event.target.value) }))} placeholder="Jalisco" /></label>
              <label>City<input value={criteria.cities.join(", ")} onChange={(event) => setCriteria((current) => ({ ...current, cities: parseTags(event.target.value) }))} placeholder="Guadalajara" /></label>
            </div>
          </fieldset>

          <fieldset className="search-fieldset">
            <legend>Role category</legend>
            <div className="chip-grid">
              {ROLE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`search-chip ${criteria.role_categories.includes(option.value) ? "selected" : ""}`}
                  onClick={() => setCriteria((current) => ({
                    ...current,
                    role_categories: toggleValue<SearchRoleCategory>(current.role_categories, option.value),
                  }))}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="search-fieldset">
            <legend>Keywords</legend>
            <div className="search-grid two">
              <label>Include<input value={criteria.include_keywords.join(", ")} onChange={(event) => setCriteria((current) => ({ ...current, include_keywords: parseTags(event.target.value) }))} placeholder="C++, Python, Linux" /></label>
              <label>Exclude<input value={criteria.exclude_keywords.join(", ")} onChange={(event) => setCriteria((current) => ({ ...current, exclude_keywords: parseTags(event.target.value) }))} placeholder="Senior, Staff, Principal" /></label>
            </div>
          </fieldset>

          <fieldset className="search-fieldset">
            <legend>Eligibility</legend>
            <label className="search-check">
              <input type="checkbox" checked={criteria.only_realistically_eligible} onChange={(event) => setCriteria((current) => ({ ...current, only_realistically_eligible: event.target.checked }))} />
              <span><strong>Only jobs I can realistically apply to</strong><small>Hard eligibility failures stay out of primary results.</small></span>
            </label>
            <label className="search-check">
              <input type="checkbox" checked={criteria.include_unknown_eligibility} onChange={(event) => setCriteria((current) => ({ ...current, include_unknown_eligibility: event.target.checked }))} />
              <span><strong>Include eligibility unknown</strong><small>Keep promising roles that still need verification.</small></span>
            </label>
          </fieldset>

          <button type="button" className="advanced-toggle" onClick={() => setAdvanced((value) => !value)}>
            Advanced options <span>{advanced ? "−" : "+"}</span>
          </button>
          {advanced && (
            <section className="advanced-options">
              <label>Source type<select value={criteria.source_mode} onChange={(event) => setCriteria((current) => ({ ...current, source_mode: event.target.value as SearchCriteria["source_mode"] }))}><option value="ALL_SOURCES">All sources</option><option value="OFFICIAL_ONLY">Official sources only</option><option value="OFFICIAL_AND_COMMUNITY">Official + community</option></select></label>
              <label>Posting age<select value={criteria.posted_within_days ?? "any"} onChange={(event) => setCriteria((current) => ({ ...current, posted_within_days: event.target.value === "any" ? null : Number(event.target.value) as SearchCriteria["posted_within_days"] }))}><option value="any">Any</option><option value="1">Last 24 hours</option><option value="3">Last 3 days</option><option value="7">Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option></select></label>
              <label>Result limit<select value={criteria.limit} onChange={(event) => setCriteria((current) => ({ ...current, limit: Number(event.target.value) as SearchCriteria["limit"] }))}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label>
            </section>
          )}

          {recentSearches.length > 0 && (
            <section className="recent-searches">
              <h3><History size={16} /> Recent Searches</h3>
              {recentSearches.slice(0, 6).map((run) => (
                <article key={run.id}>
                  <div>
                    <strong>{searchHistoryLabel(run)}</strong>
                    <span><Clock3 size={12} /> {run.result_count} results · {run.status}</span>
                  </div>
                  <div className="recent-search-actions">
                    <button type="button" onClick={() => onOpenSearch(run)}>Open</button>
                    <button type="button" onClick={() => onRunAgain(run)}>Run again</button>
                    <button type="button" aria-label={`Delete ${searchHistoryLabel(run)}`} onClick={() => onDeleteSearch(run)}><Trash2 size={14} /></button>
                  </div>
                </article>
              ))}
            </section>
          )}
        </div>

        <footer className="search-drawer-footer">
          <button type="button" className="button secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="button primary" disabled={submitting} onClick={() => onSubmit(criteria)}>
            <Search size={16} /> {submitting ? "Starting search…" : "Search Jobs"}
          </button>
        </footer>
      </section>
    </div>
  );
}
