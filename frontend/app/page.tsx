"use client";

import {
  AlertTriangle,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  CircleSlash2,
  Clock3,
  LoaderCircle,
  Radar,
  Search,
  Send,
  Siren,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { CurrentResultsFilters } from "@/components/CurrentResultsFilters";
import { AddJobByUrl } from "@/components/AddJobByUrl";
import { JobTable } from "@/components/JobTable";
import { SearchResultsHeader } from "@/components/SearchResultsHeader";
import { api, ApiError, formatDate } from "@/lib/api";
import {
  buildResultsQuery,
  buildPriorityResultsQuery,
  dashboardResultsPath,
  EMPTY_CURRENT_FILTERS,
  readDashboardResultsState,
} from "@/lib/job-search";
import type { CurrentResultFilters } from "@/lib/job-search";
import {
  BACKEND_STARTUP_RETRY_DELAY_MS,
  formatStartupElapsed,
  isRetriableStartupError,
  startupRetryDelayMs,
} from "@/lib/startup";
import { readRouteData, writeRouteData } from "@/lib/route-data-cache";
import type {
  JobPage,
  SearchRun,
  Stats,
  Profile,
} from "@/lib/types";

type StartupState = "starting" | "retrying" | "ready" | "error";

const emptyStats: Stats = {
  total_jobs: 0,
  new_jobs: 0,
  apply_today: 0,
  review: 0,
  needs_verification: 0,
  not_eligible: 0,
  low_match: 0,
  closed: 0,
  priority_alerts: 0,
  urgent: 0,
  applications: 0,
  last_update: null,
  latest_search_id: null,
  latest_search_status: null,
  latest_search_progress: null,
  latest_search_errors: "",
};

const emptyJobs = (pageSize: number): JobPage => ({ items: [], total: 0, page: 1, page_size: pageSize });

type DashboardData = {
  stats: Stats;
  jobs: JobPage;
  priorityJobs: JobPage;
  activeSearchRun: SearchRun | null;
};

function dashboardCacheKey(searchRunId: number | null, filters: CurrentResultFilters): string {
  return `dashboard:${dashboardResultsPath(searchRunId, filters)}`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [jobs, setJobs] = useState<JobPage>(emptyJobs(50));
  const [priorityJobs, setPriorityJobs] = useState<JobPage>(emptyJobs(6));
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [activeSearchRunId, setActiveSearchRunId] = useState<number | null | undefined>(undefined);
  const [activeSearchRun, setActiveSearchRun] = useState<SearchRun | null>(null);
  const [candidateName, setCandidateName] = useState("Candidate");
  const [resultFilters, setResultFilters] = useState<CurrentResultFilters>({ ...EMPTY_CURRENT_FILTERS });
  const [startupState, setStartupState] = useState<StartupState>("starting");
  const [startupElapsedMs, setStartupElapsedMs] = useState(0);
  const [startupAttempts, setStartupAttempts] = useState(0);
  const [startupRetryMs, setStartupRetryMs] = useState(BACKEND_STARTUP_RETRY_DELAY_MS);
  const [startupErrorStatus, setStartupErrorStatus] = useState<number | null>(null);
  const startupStartedAt = useRef(Date.now());
  const initialLoadPending = useRef(true);
  const latestLoad = useRef(0);
  const lastFocusRefresh = useRef(0);

  useEffect(() => {
    api<Profile>("/api/profile")
      .then((profile) => setCandidateName(profile.display_name || profile.full_name.split(/\s+/)[0] || "Candidate"))
      .catch(() => setCandidateName("Candidate"));
  }, []);

  useEffect(() => {
    const syncFromUrl = () => {
      const state = readDashboardResultsState(window.location.search);
      setActiveSearchRunId(state.searchRunId);
      setResultFilters(state.filters);
      const cached = readRouteData<DashboardData>(dashboardCacheKey(state.searchRunId, state.filters));
      if (cached) {
        setStats(cached.stats);
        setJobs(cached.jobs);
        setPriorityJobs(cached.priorityJobs);
        setActiveSearchRun(cached.activeSearchRun);
        // A revalidation still starts below, but returning from a detail page
        // no longer replaces the dashboard with a loading screen first.
        setLoading(false);
        setStartupState("ready");
      }
    };
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  useEffect(() => {
    if (startupState !== "starting" && startupState !== "retrying") return;
    const timer = window.setInterval(() => {
      setStartupElapsedMs(Date.now() - startupStartedAt.current);
    }, 100);
    return () => window.clearInterval(timer);
  }, [startupState]);

  useEffect(() => {
    if (activeSearchRunId === undefined) return;
    const path = dashboardResultsPath(activeSearchRunId, resultFilters);
    if (`${window.location.pathname}${window.location.search}` !== path) {
      window.history.replaceState(window.history.state, "", path);
    }
  }, [activeSearchRunId, resultFilters]);

  const load = useCallback(async () => {
    if (activeSearchRunId === undefined) return;
    const requestId = ++latestLoad.current;
    const initialLoad = initialLoadPending.current;
    const cacheKey = dashboardCacheKey(activeSearchRunId, resultFilters);
    const cached = readRouteData<DashboardData>(cacheKey);
    if (initialLoad) setStartupAttempts((attempts) => attempts + 1);
    if (cached) {
      setStats(cached.stats);
      setJobs(cached.jobs);
      setPriorityJobs(cached.priorityJobs);
      setActiveSearchRun(cached.activeSearchRun);
    } else {
      // Never show the previous query's priority cards under a new filter.
      setPriorityJobs(emptyJobs(10));
    }
    setLoading(!cached);
    try {
      const scope = activeSearchRunId ? `?search_run_id=${activeSearchRunId}` : "";
      const statsPath = `/api/stats${scope}`;
      const jobsPath = buildResultsQuery(activeSearchRunId, resultFilters, 50);
      // Priority pins remain independent of the selected source-scan run, but
      // the visible dashboard filters must apply to this section as well.
      const priorityPath = buildPriorityResultsQuery(resultFilters);
      // Stagger dashboard reads so the small production database is not hit
      // by four simultaneous sessions whenever the screen refreshes.
      const statsData = await api<Stats>(statsPath);
      const jobsData = await api<JobPage>(jobsPath);
      const priorityData = await api<JobPage>(priorityPath);
      const runData = activeSearchRunId
        ? await api<SearchRun>(`/api/search-runs/${activeSearchRunId}`)
        : null;
      if (requestId !== latestLoad.current) return;
      setStats(statsData);
      setJobs(jobsData);
      setPriorityJobs(priorityData);
      setActiveSearchRun(runData);
      writeRouteData(cacheKey, {
        stats: statsData,
        jobs: jobsData,
        priorityJobs: priorityData,
        activeSearchRun: runData,
      });
      if (initialLoad) {
        setStartupElapsedMs(Date.now() - startupStartedAt.current);
        setStartupState("ready");
        setStartupErrorStatus(null);
        initialLoadPending.current = false;
      }
    } catch (error) {
      if (requestId !== latestLoad.current) return;
      const elapsedMs = Date.now() - startupStartedAt.current;
      const errorStatus = error instanceof ApiError ? error.status : null;
      if (initialLoad) setStartupErrorStatus(errorStatus);
      if (initialLoad && isRetriableStartupError(error, elapsedMs)) {
        setStartupElapsedMs(elapsedMs);
        setStartupRetryMs(startupRetryDelayMs(error, elapsedMs));
        setStartupState("retrying");
        setMessage("");
        return;
      }
      if (initialLoad) {
        setStartupElapsedMs(elapsedMs);
        setStartupState("error");
        initialLoadPending.current = false;
      }
      if (!cached) {
        setJobs(emptyJobs(50));
        setPriorityJobs(emptyJobs(6));
      }
      setMessage(error instanceof Error ? error.message : "Could not reach the API.");
    } finally {
      if (requestId === latestLoad.current && !initialLoadPending.current) setLoading(false);
    }
  }, [activeSearchRunId, resultFilters]);

  useEffect(() => {
    if (activeSearchRunId === undefined) return;
    const delay = resultFilters.q ? 220 : 0;
    const timer = window.setTimeout(() => void load(), delay);
    return () => window.clearTimeout(timer);
  }, [activeSearchRunId, load, resultFilters.q]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastFocusRefresh.current < 1000) return;
      lastFocusRefresh.current = now;
      void load();
    };
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [load]);

  useEffect(() => {
    if (startupState !== "retrying" || !initialLoadPending.current) return;
    const timer = window.setTimeout(() => {
      setStartupState("starting");
      void load();
    }, startupRetryMs);
    return () => window.clearTimeout(timer);
  }, [load, startupRetryMs, startupState]);

  function setActiveRun(run: SearchRun | null) {
    const id = run?.id ?? null;
    window.history.pushState({}, "", dashboardResultsPath(id, EMPTY_CURRENT_FILTERS));
    setActiveSearchRunId(id);
    setActiveSearchRun(run);
    setResultFilters({ ...EMPTY_CURRENT_FILTERS });
  }

  const cards = [
    { label: "New this week", value: stats.new_jobs, icon: Radar, tone: "blue" },
    { label: "Apply today", value: stats.apply_today, icon: CheckCircle2, tone: "green" },
    { label: "Priority alerts", value: stats.priority_alerts, icon: Siren, tone: "priority" },
    { label: "Needs review", value: stats.review, icon: AlertTriangle, tone: "amber" },
    { label: "Needs verification", value: stats.needs_verification, icon: Radar, tone: "violet" },
    { label: "Not eligible", value: stats.not_eligible, icon: CircleSlash2, tone: "red" },
  ];

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Candidate overview</p>
          <h1>Good morning, {candidateName}</h1>
          <p className="page-subtitle">
            {activeSearchRun ? "Viewing results from an earlier source scan." : "Browse and filter saved opportunities."}
          </p>
        </div>
        <div className="header-actions">
          <AddJobByUrl />
          <Link className="button secondary search-jobs-button" href="/jobs">
            <Search size={17} />
            Search Jobs
          </Link>
        </div>
      </header>

      {startupState !== "ready" && (
        <div className={`startup-timer ${startupState}`} role="status" aria-live="polite">
          {startupState === "starting" || startupState === "retrying" ? <LoaderCircle size={17} className="spin" /> : <AlertTriangle size={17} />}
          <div>
            <strong>{startupState === "starting" ? "Connecting to secure cloud services" : startupState === "retrying" && startupErrorStatus === 429 ? "API is temporarily busy" : startupState === "retrying" ? "Render is still waking up" : startupErrorStatus === 429 ? "API request limit did not clear" : "Backend did not respond"}</strong>
            <span>{startupState === "error" ? "Automatic retries stopped. Reload the page to try again." : startupErrorStatus === 429 ? `Retrying automatically. Attempt ${Math.max(1, startupAttempts)}.` : `Free hosting may need up to 60 seconds after inactivity. Attempt ${Math.max(1, startupAttempts)}.`}</span>
          </div>
          <time dateTime={`PT${Math.ceil(startupElapsedMs / 1000)}S`}><Clock3 size={14} />{formatStartupElapsed(startupElapsedMs)}</time>
        </div>
      )}

      {message && <div className="notice" role="status">{message}</div>}

      {activeSearchRun && (
        <SearchResultsHeader
          run={activeSearchRun}
          onClear={() => setActiveRun(null)}
        />
      )}

      <section className="stats-grid" aria-label="Pipeline statistics">
        {cards.map(({ label, value, icon: Icon, tone }) => (
          <div className="stat-card" key={label}>
            <span className={`stat-icon ${tone}`}><Icon size={18} /></span>
            <div><strong>{loading ? "—" : value}</strong><span>{label}</span></div>
          </div>
        ))}
      </section>

      <CurrentResultsFilters value={resultFilters} onChange={setResultFilters} />

      {priorityJobs.items.length > 0 && (
        <section className="content-section priority-section">
          <div className="section-heading">
            <div><h2><Siren size={17} /> Important opportunities</h2><p>High-priority and personally pinned roles across your account. Eligibility warnings remain visible.</p><Link href="/jobs?company=Google&include_ineligible=true">All Google internships</Link></div>
            <span className="priority-summary">{stats.urgent ? `${stats.urgent} urgent` : "Recently verified"}</span>
          </div>
          <JobTable jobs={priorityJobs.items} returnTo={dashboardResultsPath(activeSearchRunId ?? null, resultFilters)} />
        </section>
      )}

      <section className="content-section">
        <div className="section-heading">
          <div>
            <h2>{activeSearchRun ? "Results for this search" : "Priority queue"}</h2>
            <p>{activeSearchRun ? "Only jobs connected to this SearchRun are shown." : "Ranked by fit, eligibility, level, logistics, and freshness."}</p>
          </div>
          <Link href={activeSearchRunId ? `/jobs?search=${activeSearchRunId}` : "/jobs"} className="text-link">View all jobs <BriefcaseBusiness size={16} /></Link>
        </div>
        <div className="filter-row current-company-filters" aria-label="Quick company filters">
          <span>Current results:</span>
          {["", "Target companies", "Oracle", "Semiconductors", "Cloud and data", "Robotics and automotive", "Other companies"].map((group) => (
            <button key={group || "all"} className={`button ${resultFilters.targetGroup === group ? "primary" : "ghost"}`} onClick={() => setResultFilters((current) => ({ ...current, targetGroup: group }))}>{group || "All companies"}</button>
          ))}
        </div>
        {loading ? (
          <div className="empty-state">Loading your radar…</div>
        ) : activeSearchRun && jobs.items.length === 0 ? (
          <div className="search-empty-state">
            <Search size={27} />
            <h3>No matching jobs found for this search.</h3>
            <p>Try including LATAM or global remote, adding companies, including eligibility unknown, or expanding the posting age.</p>
            <Link className="button primary" href="/jobs">Search saved jobs</Link>
          </div>
        ) : (
          <JobTable jobs={jobs.items} returnTo={dashboardResultsPath(activeSearchRunId ?? null, resultFilters)} />
        )}
      </section>

      <section className="dashboard-strip">
        <div><CalendarClock size={18} /><span>Last source update</span><strong>{formatDate(stats.last_update)}</strong>{stats.latest_search_errors && <small>{stats.latest_search_errors}</small>}</div>
        <div><BriefcaseBusiness size={18} /><span>{activeSearchRun ? "Search results" : "Total tracked"}</span><strong>{activeSearchRun ? activeSearchRun.result_count : stats.total_jobs} jobs</strong></div>
        <Link href="/applications" className="button secondary"><Send size={16} /> Open application tracker</Link>
      </section>

    </>
  );
}
