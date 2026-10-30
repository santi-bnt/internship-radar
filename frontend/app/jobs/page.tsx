"use client";

import { Filter, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { JobTable } from "@/components/JobTable";
import { AddJobByUrl } from "@/components/AddJobByUrl";
import { api } from "@/lib/api";
import { removeItemOptimistically } from "@/lib/jobs-state";
import { appendEligibilityFilters } from "@/lib/eligibility";
import {
  INITIAL_JOBS_LIST_FILTERS,
  jobsListPath,
  readJobsListState,
  type JobsListFilters,
  type JobsListState,
} from "@/lib/jobs-list-state";
import { readRouteData, writeRouteData } from "@/lib/route-data-cache";
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
const statusOptions = ["Apply Now", "Apply Today", "Review", "Needs Verification", "Not Eligible", "Low Match", "Closed", "Expired"];
const importanceOptions = ["Major company", "Established company", "Startup", "Unknown"];
const verificationOptions = ["Officially verified", "Partially verified", "Not verified"];
const eligibilityOptions = ["ELIGIBLE", "LIKELY_ELIGIBLE", "UNKNOWN", "LIKELY_INELIGIBLE", "NOT_ELIGIBLE"];
const remoteScopeOptions = ["GLOBAL", "LATAM", "MEXICO", "COUNTRY_LIST", "US_ONLY", "COUNTRY_RESTRICTED", "UNKNOWN", "NOT_REMOTE"];
const sponsorshipOptions = ["AVAILABLE", "NOT_AVAILABLE", "NOT_REQUIRED", "UNKNOWN"];

type FilterState = JobsListFilters;
const initialFilters = INITIAL_JOBS_LIST_FILTERS;

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
  const [lifecycleStatus, setLifecycleStatus] = useState<JobsListState["lifecycleStatus"]>("active");
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [data, setData] = useState<JobPage>({ items: [], total: 0, page: 1, page_size: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pendingJobId, setPendingJobId] = useState<number | null>(null);
  const [targetGroup, setTargetGroup] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [showIneligible, setShowIneligible] = useState(false);
  const [searchRunId, setSearchRunId] = useState<number | null>(null);
  const [ratingOrder, setRatingOrder] = useState<"highest" | "lowest">("highest");
  const [page, setPage] = useState(1);
  const [stateHydrated, setStateHydrated] = useState(false);
  const [showResearchForm, setShowResearchForm] = useState(false);
  const [research, setResearch] = useState({ organization: "", title: "", lab: "", professor: "", researchAreas: "", description: "", url: "", notes: "" });
  const [showManualJobForm, setShowManualJobForm] = useState(false);
  const [manualJob, setManualJob] = useState({ company: "", title: "", location: "", category: "", applyUrl: "", description: "", requirements: "", preferredQualifications: "", sourceUrl: "", forceApplyNow: false });

  const currentListState: JobsListState = {
    lifecycleStatus,
    filters,
    targetGroup,
    companyFilter,
    showIneligible,
    searchRunId,
    ratingOrder,
    page,
  };
  const returnTo = jobsListPath(currentListState);
  const cacheKey = `jobs-list:${returnTo}`;

  const loadJobs = useCallback(async () => {
    // Keep a matching list visible while the API refreshes it. A different
    // filter state still gets the normal loading state, so old results are
    // never presented as results for a new query.
    const cached = readRouteData<JobPage>(cacheKey);
    setLoading(!cached);
    if (cached) setData(cached);
    const params = new URLSearchParams({ page_size: "50", page: String(page), rating_order: ratingOrder });
    if (searchRunId) params.set("search_run_id", String(searchRunId));
    params.append("job_status", lifecycleStatus);
    if (targetGroup) params.set("target_group", targetGroup);
    if (companyFilter) params.set("company", companyFilter);
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
      const result = await api<JobPage>(`/api/jobs?${params.toString()}`);
      writeRouteData(cacheKey, result);
      setData(result);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load jobs.");
    } finally {
      setLoading(false);
    }
  }, [cacheKey, companyFilter, filters, lifecycleStatus, page, ratingOrder, searchRunId, showIneligible, targetGroup]);

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

  async function removeApplied(job: Job) {
    if (pendingJobId !== null) return;
    setPendingJobId(job.id);
    try {
      const result = await api<JobLifecycleAction>(`/api/jobs/${job.id}/undo-applied`, { method: "POST" });
      setData((current) => removeItemOptimistically(current, job.id));
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not remove Applied status.");
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

  async function createResearchOpportunity() {
    try {
      const created = await api<Job>("/api/research-opportunities", {
        method: "POST",
        body: JSON.stringify({
          organization: research.organization,
          title: research.title,
          lab: research.lab,
          professor: research.professor,
          research_areas: research.researchAreas.split(",").map((item) => item.trim()).filter(Boolean),
          description: research.description,
          url: research.url,
          notes: research.notes,
        }),
      });
      window.location.href = `/jobs/${created.id}`;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create research opportunity.");
    }
  }

  async function createManualJob() {
    try {
      const created = await api<Job>("/api/jobs/manual", {
        method: "POST",
        body: JSON.stringify({
          company: manualJob.company,
          title: manualJob.title,
          location: manualJob.location,
          category: manualJob.category,
          apply_url: manualJob.applyUrl,
          description: manualJob.description,
          requirements: manualJob.requirements,
          preferred_qualifications: manualJob.preferredQualifications,
          source_url: manualJob.sourceUrl,
          force_apply_now: manualJob.forceApplyNow,
        }),
      });
      window.location.href = `/jobs/${created.id}`;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add job manually.");
    }
  }

  useEffect(() => {
    if (!stateHydrated) return;
    const handle = window.setTimeout(() => void loadJobs(), 220);
    return () => window.clearTimeout(handle);
  }, [loadJobs, stateHydrated]);

  useEffect(() => {
    const restore = () => {
      const params = new URLSearchParams(window.location.search);
      const state = readJobsListState(window.location.search);
      setLifecycleStatus(state.lifecycleStatus);
      setFilters(state.filters);
      setTargetGroup(state.targetGroup);
      setCompanyFilter(state.companyFilter);
      setShowIneligible(state.showIneligible);
      setSearchRunId(state.searchRunId);
      setRatingOrder(state.ratingOrder);
      setPage(state.page);
      const cached = readRouteData<JobPage>(`jobs-list:${jobsListPath(state)}`);
      if (cached) {
        setData(cached);
        setLoading(false);
      }
      if (params.get("notice") === "applied") {
        setMessage("Application marked as submitted and moved to Applied.");
        params.delete("notice");
        window.history.replaceState({}, "", `/jobs${params.size ? `?${params.toString()}` : ""}`);
      }
      setStateHydrated(true);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!stateHydrated) return;
    const current = `${window.location.pathname}${window.location.search}`;
    if (current !== returnTo) window.history.replaceState({}, "", returnTo);
  }, [returnTo, stateHydrated]);

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
      + (companyFilter ? 1 : 0)
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
  }, [companyFilter, filters, showIneligible]);

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Opportunity database</p>
          <h1>Search Jobs</h1>
          <p className="page-subtitle">Filter {data.total} saved opportunities. Source scans are managed in Sources.</p>
        </div>
        <div className="header-actions">
          <AddJobByUrl />
          <button className="button secondary" onClick={() => setShowManualJobForm((value) => !value)}>Add Job Manually</button>
          <button className="button secondary" onClick={() => setShowResearchForm((value) => !value)}>New Research Opportunity</button>
        </div>
      </header>

      {showManualJobForm && (
        <section className="card manual-job-form">
          <h2>Add Job Manually</h2>
          <p>Enter a job posting you found. Details you provide are saved as unverified until checked against official content.</p>
          <div className="form-grid">
            <label>Company<input required value={manualJob.company} onChange={(event) => setManualJob({ ...manualJob, company: event.target.value })} /></label>
            <label>Job title<input required value={manualJob.title} onChange={(event) => setManualJob({ ...manualJob, title: event.target.value })} /></label>
            <label>Location<input value={manualJob.location} onChange={(event) => setManualJob({ ...manualJob, location: event.target.value })} /></label>
            <label>Category<input value={manualJob.category} onChange={(event) => setManualJob({ ...manualJob, category: event.target.value })} /></label>
          </div>
          <label>Official application URL<input required type="url" value={manualJob.applyUrl} onChange={(event) => setManualJob({ ...manualJob, applyUrl: event.target.value })} /></label>
          <label>Description<textarea rows={4} value={manualJob.description} onChange={(event) => setManualJob({ ...manualJob, description: event.target.value })} /></label>
          <label>Requirements<textarea rows={3} value={manualJob.requirements} onChange={(event) => setManualJob({ ...manualJob, requirements: event.target.value })} /></label>
          <label>Preferred qualifications<textarea rows={3} value={manualJob.preferredQualifications} onChange={(event) => setManualJob({ ...manualJob, preferredQualifications: event.target.value })} /></label>
          <label>Source URL<input type="url" value={manualJob.sourceUrl} onChange={(event) => setManualJob({ ...manualJob, sourceUrl: event.target.value })} /></label>
          <label className="checkbox-label"><input type="checkbox" checked={manualJob.forceApplyNow} onChange={(event) => setManualJob({ ...manualJob, forceApplyNow: event.target.checked })} /> Mark Apply Now for me (manual override; does not change eligibility or score)</label>
          <button className="button primary" disabled={!manualJob.company.trim() || !manualJob.title.trim() || !manualJob.applyUrl.trim()} onClick={() => void createManualJob()}>Add Job</button>
        </section>
      )}

      {showResearchForm && (
        <section className="card research-opportunity-form">
          <h2>New Research Opportunity</h2>
          <p>Research opportunities are tracked separately from employment postings.</p>
          <div className="form-grid">
            <label>University / Organization<input required value={research.organization} onChange={(event) => setResearch({ ...research, organization: event.target.value })} /></label>
            <label>Opportunity title<input required value={research.title} onChange={(event) => setResearch({ ...research, title: event.target.value })} /></label>
            <label>Lab (optional)<input value={research.lab} onChange={(event) => setResearch({ ...research, lab: event.target.value })} /></label>
            <label>Professor / Supervisor (optional)<input value={research.professor} onChange={(event) => setResearch({ ...research, professor: event.target.value })} /></label>
          </div>
          <label>Research areas (comma-separated)<input value={research.researchAreas} onChange={(event) => setResearch({ ...research, researchAreas: event.target.value })} /></label>
          <label>Description (optional)<textarea rows={4} value={research.description} onChange={(event) => setResearch({ ...research, description: event.target.value })} /></label>
          <label>Professor / lab URL (reference only)<input type="url" value={research.url} onChange={(event) => setResearch({ ...research, url: event.target.value })} /></label>
          <label>Notes (optional)<textarea rows={3} value={research.notes} onChange={(event) => setResearch({ ...research, notes: event.target.value })} /></label>
          <button className="button primary" disabled={!research.organization.trim() || !research.title.trim()} onClick={() => void createResearchOpportunity()}>Create Research Opportunity</button>
        </section>
      )}

      <nav className="header-actions" aria-label="Job lifecycle">
        {([
          ["active", "Active"],
          ["saved", "Saved"],
          ["applied", "Applied"],
          ["expired", "Expired"],
          ["not_interested", "Not Interested"],
          ["archived", "Archived"],
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

      <section id="job-filters" className="filter-band" aria-label="Job filters">
        <label className="search-field">
          <Search size={17} />
          <input
            value={filters.q}
            onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
            placeholder="Search title, company, skill, or location"
          />
        </label>
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="Filter company"
            value={companyFilter}
            onChange={(event) => setCompanyFilter(event.target.value)}
            placeholder="Company name"
          />
        </label>
        <div className="filter-title-row">
          <span className="filter-label"><Filter size={15} /> Combine filters</span>
          <label className="toggle-label"><input type="checkbox" checked={showIneligible} onChange={(event) => setShowIneligible(event.target.checked)} /> Show ineligible jobs</label>
          {activeFilterCount > 0 && (
            <button className="button ghost" onClick={() => { setFilters(initialFilters); setCompanyFilter(""); setShowIneligible(false); setRatingOrder("highest"); setPage(1); }}>
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
              <select aria-label="Sort jobs by rating" value={ratingOrder} onChange={(event) => setRatingOrder(event.target.value as "highest" | "lowest")}>
                <option value="highest">Highest rating first</option>
                <option value="lowest">Lowest rating first</option>
              </select>
            </div>
          </fieldset>
        </div>
      </section>

      {error && <div className="notice error" role="alert">{error}</div>}
      {message && <div className="notice success" role="status">{message}</div>}
      <section className="content-section">
        <div className="section-heading compact">
          <h2>{loading ? "Filtering..." : `${data.total} results`}</h2>
        </div>
        {loading ? <div className="empty-state">Applying filters...</div> : (
          <JobTable
            jobs={data.items}
            returnTo={returnTo}
            lifecycle={lifecycleStatus}
            pendingJobId={pendingJobId}
            onMarkApplied={lifecycleStatus === "active" || lifecycleStatus === "saved" ? (job) => void markApplied(job) : undefined}
            onRemoveApplied={lifecycleStatus === "applied" ? (job) => void removeApplied(job) : undefined}
            onArchive={lifecycleStatus !== "archived" ? (job) => void lifecycleAction(job, "archive") : undefined}
            onRestore={["expired", "archived", "not_interested"].includes(lifecycleStatus) ? (job) => void lifecycleAction(job, "restore") : undefined}
          />
        )}
      </section>
    </>
  );
}
