"use client";

import {
  AlertTriangle,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  CircleSlash2,
  Radar,
  RefreshCw,
  Send,
  Siren,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { JobTable } from "@/components/JobTable";
import { api, formatDate } from "@/lib/api";
import type { JobPage, SearchRun, Stats } from "@/lib/types";

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

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>(emptyStats);
  const [jobs, setJobs] = useState<JobPage>({ items: [], total: 0, page: 1, page_size: 10 });
  const [priorityJobs, setPriorityJobs] = useState<JobPage>({ items: [], total: 0, page: 1, page_size: 6 });
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchProgress, setSearchProgress] = useState("Searching");
  const [message, setMessage] = useState("");
  const [companyGroup, setCompanyGroup] = useState("");
  const [searchRunId, setSearchRunId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [statsData, jobsData, priorityData] = await Promise.all([
        api<Stats>("/api/stats"),
        api<JobPage>(`/api/jobs?active=true&page_size=10${companyGroup ? `&target_group=${encodeURIComponent(companyGroup)}` : ""}`),
        api<JobPage>("/api/jobs?active=true&priority=true&page_size=6"),
      ]);
      setStats(statsData);
      setJobs(jobsData);
      setPriorityJobs(priorityData);
      if (statsData.latest_search_status === "running" || statsData.latest_search_status === "pending") {
        setSearching(true);
        setSearchRunId(statsData.latest_search_id);
        setSearchProgress(statsData.latest_search_progress ?? "Starting");
        setMessage(statsData.latest_search_progress ?? "Starting");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }, [companyGroup]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!searchRunId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const run = await api<SearchRun>(`/api/search-runs/${searchRunId}`);
        if (cancelled) return;
        setSearchProgress(run.progress_status);
        setMessage(
          run.status === "completed" || run.status === "partial"
            ? `Completed: ${run.jobs_added} new, ${run.jobs_updated} refreshed, ${run.error_count} source errors.`
            : run.status === "failed"
              ? run.safe_error_summary || "Search failed."
              : run.progress_status,
        );
        if (run.status === "pending" || run.status === "running") {
          timer = setTimeout(poll, 1500);
        } else {
          setSearching(false);
          setSearchRunId(null);
          await load();
        }
      } catch (error) {
        if (!cancelled) {
          setSearching(false);
          setSearchRunId(null);
          setMessage(error instanceof Error ? error.message : "Could not read search progress.");
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [load, searchRunId]);

  async function searchNow() {
    setSearching(true);
    try {
      const result = await api<SearchRun>(
        "/api/jobs/search",
        { method: "POST" },
      );
      setSearchRunId(result.id);
      setSearchProgress(result.progress_status);
      setMessage(result.progress_status);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Search failed.");
    }
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
          <h1>Welcome back</h1>
          <p className="page-subtitle">
            {stats.apply_today
              ? `${stats.apply_today} role${stats.apply_today === 1 ? "" : "s"} ready for a closer look.`
              : "Your radar is ready for the next search."}
          </p>
        </div>
        <button className="button primary" onClick={searchNow} disabled={searching}>
          <RefreshCw size={17} className={searching ? "spin" : ""} />
          {searching ? searchProgress : "Search now"}
        </button>
      </header>

      {message && <div className="notice" role="status">{message}</div>}

      <section className="stats-grid" aria-label="Pipeline statistics">
        {cards.map(({ label, value, icon: Icon, tone }) => (
          <div className="stat-card" key={label}>
            <span className={`stat-icon ${tone}`}><Icon size={18} /></span>
            <div>
              <strong>{loading ? "—" : value}</strong>
              <span>{label}</span>
            </div>
          </div>
        ))}
      </section>

      {priorityJobs.items.length > 0 && (
        <section className="content-section priority-section">
          <div className="section-heading">
            <div>
              <h2><Siren size={17} /> Important opportunities</h2>
              <p>Officially verified, high-fit roles that deserve prompt attention.</p>
            </div>
            <span className="priority-summary">{stats.urgent ? `${stats.urgent} urgent` : "Recently verified"}</span>
          </div>
          <JobTable jobs={priorityJobs.items} />
        </section>
      )}

      <section className="content-section">
        <div className="section-heading">
          <div>
            <h2>Priority queue</h2>
            <p>Ranked by fit, eligibility, level, logistics, and freshness.</p>
          </div>
          <Link href="/jobs" className="text-link">
            View all jobs <BriefcaseBusiness size={16} />
          </Link>
        </div>
        <div className="filter-row" aria-label="Company filters">
          {["", "Target companies", "Oracle", "Semiconductors", "Cloud and data", "Robotics and automotive", "Other companies"].map((group) => (
            <button
              key={group || "all"}
              className={`button ${companyGroup === group ? "primary" : "ghost"}`}
              onClick={() => setCompanyGroup(group)}
            >
              {group || "All companies"}
            </button>
          ))}
        </div>
        {loading ? <div className="empty-state">Loading your radar…</div> : <JobTable jobs={jobs.items} />}
      </section>

      <section className="dashboard-strip">
        <div>
          <CalendarClock size={18} />
          <span>Last source update</span>
          <strong>{formatDate(stats.last_update)}</strong>
          {stats.latest_search_errors && <small>{stats.latest_search_errors}</small>}
        </div>
        <div>
          <BriefcaseBusiness size={18} />
          <span>Total tracked</span>
          <strong>{stats.total_jobs} jobs</strong>
        </div>
        <Link href="/applications" className="button secondary">
          <Send size={16} /> Open application tracker
        </Link>
      </section>
    </>
  );
}
