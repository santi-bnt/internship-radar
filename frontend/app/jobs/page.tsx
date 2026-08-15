"use client";

import { Filter, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { JobTable } from "@/components/JobTable";
import { api } from "@/lib/api";
import { removeItemOptimistically } from "@/lib/jobs-state";
import { appendEligibilityFilters } from "@/lib/eligibility";
import type { Job, JobLifecycleAction, JobPage } from "@/lib/types";

const countryOptions = ["Mexico", "United States", "Canada", "Remote outside selected countries"];
const arrangementOptions = ["On-site", "Hybrid", "Remote", "Remote from Mexico"];
const employmentOptions = ["Internship", "Co-op", "Student program"];
const areaOptions = [
  "Software / SDE",
  "Firmware / Embedded",
  "FPGA / RTL / ASIC",
  "Robotics",
  "Hardware Test / Validation",
  "Electrical Engineering",
  "Controls / Automation",
  "Computer Vision",
];
const statusOptions = ["Apply Today", "Review", "Needs Verification", "Not Eligible", "Low Match", "Closed"];
const importanceOptions = ["Major company", "Established company", "Startup", "Unknown"];
const verificationOptions = ["Officially verified", "Partially verified", "Not verified"];
const eligibilityOptions = ["ELIGIBLE", "LIKELY_ELIGIBLE", "UNKNOWN", "LIKELY_INELIGIBLE", "NOT_ELIGIBLE"];
const remoteScopeOptions = ["GLOBAL", "LATAM", "MEXICO", "COUNTRY_LIST", "US_ONLY", "COUNTRY_RESTRICTED", "UNKNOWN", "NOT_REMOTE"];
const sponsorshipOptions = ["AVAILABLE", "NOT_AVAILABLE", "NOT_REQUIRED", "UNKNOWN"];

type FilterState = {
  q: string;
  countries: string[];
  arrangements: string[];
  employment: string[];
  areas: string[];
  statuses: string[];
  importance: string[];
  verification: string[];
  eligibility: string[];
  remoteScopes: string[];
  sponsorship: string[];
  date: string;
  minScore: string;
};

const initialFilters: FilterState = {
  q: "",
  countries: ["Mexico", "United States", "Canada"],
  arrangements: [],
  employment: [],
  areas: [],
  statuses: [],
  importance: [],
  verification: [],
  eligibility: [],
  remoteScopes: [],
  sponsorship: [],
  date: "Any date",
  minScore: "",
};

function FilterGroup({
  label,
  values,
  selected,
  onToggle,
}: {
  label: string;
  values: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <fieldset className="filter-group">
      <legend>{label}</legend>
      <div className="filter-options">
        {values.map((value) => (
          <label key={value}>
            <input type="checkbox" checked={selected.includes(value)} onChange={() => onToggle(value)} />
            <span>{value}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function JobsPage() {
  const [lifecycleStatus, setLifecycleStatus] = useState<"active" | "saved" | "applied" | "expired" | "not_interested">("active");
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [data, setData] = useState<JobPage>({ items: [], total: 0, page: 1, page_size: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pendingJobId, setPendingJobId] = useState<number | null>(null);
  const [targetGroup, setTargetGroup] = useState("");
  const [showIneligible, setShowIneligible] = useState(false);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page_size: "50" });
    params.append("job_status", lifecycleStatus);
    if (targetGroup) params.set("target_group", targetGroup);
    if (filters.q) params.set("q", filters.q);
    filters.countries.forEach((value) => params.append("country", value));
    filters.arrangements.forEach((value) => params.append("remote_type", value));
    filters.employment.forEach((value) => params.append("employment", value));
    filters.areas.forEach((value) => params.append("area", value));
    filters.statuses.forEach((value) => params.append("recommendation", value));
    filters.importance.forEach((value) => params.append("company_importance", value));
    filters.verification.forEach((value) => params.append("verification", value));
    appendEligibilityFilters(params, {
      showIneligible,
      eligibility: filters.eligibility,
      remoteScopes: filters.remoteScopes,
      sponsorship: filters.sponsorship,
    });
    if (filters.date !== "Any date") params.set("date", filters.date);
    if (filters.minScore) params.set("min_score", filters.minScore);
    try {
      setData(await api<JobPage>(`/api/jobs?${params.toString()}`));
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load jobs.");
    } finally {
      setLoading(false);
    }
  }, [filters, lifecycleStatus, showIneligible, targetGroup]);

  async function markApplied(job: Job) {
    if (pendingJobId !== null) return;
    setPendingJobId(job.id);
    setData((current) => removeItemOptimistically(current, job.id));
    try {
      const result = await api<JobLifecycleAction>(`/api/jobs/${job.id}/mark-applied`, { method: "POST" });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not mark application.");
      await loadJobs();
    } finally {
      setPendingJobId(null);
    }
  }

  async function lifecycleAction(job: Job, action: "archive" | "restore") {
    if (pendingJobId !== null) return;
    setPendingJobId(job.id);
    try {
      await api<Job>(`/api/jobs/${job.id}/${action}`, { method: "POST" });
      setData((current) => removeItemOptimistically(current, job.id));
      setMessage(action === "archive" ? "Job archived." : "Job restored to Active.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Could not ${action} job.`);
    } finally {
      setPendingJobId(null);
    }
  }

  useEffect(() => {
    const handle = window.setTimeout(() => void loadJobs(), 220);
    return () => window.clearTimeout(handle);
  }, [loadJobs]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("notice") === "applied") {
      setMessage("Application marked as submitted and moved to Applied.");
      window.history.replaceState({}, "", "/jobs");
    }
  }, []);

  function toggle(key: keyof Pick<FilterState, "countries" | "arrangements" | "employment" | "areas" | "statuses" | "importance" | "verification" | "eligibility" | "remoteScopes" | "sponsorship">, value: string) {
    setFilters((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value],
    }));
  }

  const activeFilterCount = useMemo(() => {
    const defaultCountries = filters.countries.length === 3 && ["Mexico", "United States", "Canada"].every((item) => filters.countries.includes(item));
    return (
      (filters.q ? 1 : 0)
      + (defaultCountries ? 0 : 1)
      + filters.arrangements.length
      + filters.employment.length
      + filters.areas.length
      + filters.statuses.length
      + filters.importance.length
      + filters.verification.length
      + filters.eligibility.length
      + filters.remoteScopes.length
      + filters.sponsorship.length
      + (showIneligible ? 1 : 0)
      + (filters.date === "Any date" ? 0 : 1)
      + (filters.minScore ? 1 : 0)
    );
  }, [filters, showIneligible]);

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Opportunity database</p>
          <h1>Jobs</h1>
          <p className="page-subtitle">{data.total} verified, pending, and historical opportunities.</p>
        </div>
      </header>

      <nav className="header-actions" aria-label="Job lifecycle">
        {([
          ["active", "Active"],
          ["saved", "Saved"],
          ["applied", "Applied"],
          ["expired", "Expired"],
          ["not_interested", "Not Interested"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            className={`button ${lifecycleStatus === value ? "primary" : "secondary"}`}
            onClick={() => setLifecycleStatus(value)}
          >
            {label}
          </button>
        ))}
      </nav>
      <section className="filter-band" aria-label="Company group filter">
        <label className="search-field">
          <Filter size={17} />
          <select value={targetGroup} onChange={(event) => setTargetGroup(event.target.value)}>
            <option value="">All companies</option>
            <option>Target companies</option>
            <option>Oracle</option>
            <option>Semiconductors</option>
            <option>Cloud and data</option>
            <option>Robotics and automotive</option>
            <option>Other companies</option>
          </select>
        </label>
      </section>

      <section className="filter-band" aria-label="Job filters">
        <label className="search-field">
          <Search size={17} />
          <input
            value={filters.q}
            onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
            placeholder="Search title, company, skill, or location"
          />
        </label>
        <div className="filter-title-row">
          <span className="filter-label"><Filter size={15} /> Combine filters</span>
          <label className="toggle-label"><input type="checkbox" checked={showIneligible} onChange={(event) => setShowIneligible(event.target.checked)} /> Show ineligible jobs</label>
          {activeFilterCount > 0 && (
            <button className="button ghost" onClick={() => { setFilters(initialFilters); setShowIneligible(false); }}>
              <X size={16} /> Clear {activeFilterCount}
            </button>
          )}
        </div>
        <div className="filters-grid">
          <FilterGroup label="Country" values={countryOptions} selected={filters.countries} onToggle={(value) => toggle("countries", value)} />
          <FilterGroup label="Work arrangement" values={arrangementOptions} selected={filters.arrangements} onToggle={(value) => toggle("arrangements", value)} />
          <FilterGroup label="Employment" values={employmentOptions} selected={filters.employment} onToggle={(value) => toggle("employment", value)} />
          <FilterGroup label="Area" values={areaOptions} selected={filters.areas} onToggle={(value) => toggle("areas", value)} />
          <FilterGroup label="Status" values={statusOptions} selected={filters.statuses} onToggle={(value) => toggle("statuses", value)} />
          <FilterGroup label="Company importance" values={importanceOptions} selected={filters.importance} onToggle={(value) => toggle("importance", value)} />
          <FilterGroup label="Verification" values={verificationOptions} selected={filters.verification} onToggle={(value) => toggle("verification", value)} />
          <FilterGroup label="Eligibility" values={eligibilityOptions} selected={filters.eligibility} onToggle={(value) => toggle("eligibility", value)} />
          <FilterGroup label="Remote scope" values={remoteScopeOptions} selected={filters.remoteScopes} onToggle={(value) => toggle("remoteScopes", value)} />
          <FilterGroup label="Sponsorship" values={sponsorshipOptions} selected={filters.sponsorship} onToggle={(value) => toggle("sponsorship", value)} />
          <fieldset className="filter-group">
            <legend>Date and score</legend>
            <div className="stacked-selects">
              <select aria-label="Date" value={filters.date} onChange={(event) => setFilters((current) => ({ ...current, date: event.target.value }))}>
                {["Last 24 hours", "Last 3 days", "Last 7 days", "Last 14 days", "Last 30 days", "Any date"].map((value) => <option key={value}>{value}</option>)}
              </select>
              <select aria-label="Minimum score" value={filters.minScore} onChange={(event) => setFilters((current) => ({ ...current, minScore: event.target.value }))}>
                <option value="">Any score</option>
                <option value="80">80+</option>
                <option value="70">70+</option>
                <option value="50">50+</option>
              </select>
            </div>
          </fieldset>
        </div>
      </section>

      {error && <div className="notice error" role="alert">{error}</div>}
      {message && <div className="notice success" role="status">{message}</div>}
      <section className="content-section">
        <div className="section-heading compact">
          <h2>{loading ? "Scanning..." : `${data.total} results`}</h2>
        </div>
        {loading ? <div className="empty-state">Applying filters...</div> : (
          <JobTable
            jobs={data.items}
            lifecycle={lifecycleStatus}
            pendingJobId={pendingJobId}
            onMarkApplied={lifecycleStatus === "active" || lifecycleStatus === "saved" ? (job) => void markApplied(job) : undefined}
            onArchive={lifecycleStatus === "expired" ? (job) => void lifecycleAction(job, "archive") : undefined}
            onRestore={lifecycleStatus === "expired" ? (job) => void lifecycleAction(job, "restore") : undefined}
          />
        )}
      </section>
    </>
  );
}
