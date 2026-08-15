"use client";

import {
  ArrowLeft,
  BadgeCheck,
  CalendarDays,
  ExternalLink,
  FileCheck2,
  MapPin,
  RefreshCw,
  Save,
  SearchCheck,
  Siren,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ScoreBar } from "@/components/ScoreBar";
import { JobDescription } from "@/components/JobDescription";
import { StatusBadge } from "@/components/StatusBadge";
import { EligibilityBadge } from "@/components/EligibilityBadge";
import RecommendedResumeSection from "@/components/RecommendedResumeSection";
import { api, formatDate } from "@/lib/api";
import type { Job, JobLifecycleAction } from "@/lib/types";

function isDemoJob(job: Job): boolean {
  const applicationUrl = job.official_apply_url ?? job.apply_url;
  return job.discovery_status === "demo"
    || /^https?:\/\/(?:[^/]+\.)?example\.(?:com|org|net)(?:\/|$)/i.test(applicationUrl);
}

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [undoStatus, setUndoStatus] = useState<"active" | "saved" | null>(null);
  const [application, setApplication] = useState({
    status: "Applied",
    resume_type: "",
    application_reference: "",
    notes: "",
  });

  const load = useCallback(async () => {
    try {
      const data = await api<Job>(`/api/jobs/${params.id}`);
      setJob(data);
      setApplication((current) => ({
        ...current,
        resume_type: data.analysis?.recommended_resume_type ?? "General Engineering",
      }));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load job.");
    }
  }, [params.id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!undoStatus) return;
    const handle = window.setTimeout(() => setUndoStatus(null), 8000);
    return () => window.clearTimeout(handle);
  }, [undoStatus]);

  async function analyzeAgain() {
    if (!job) return;
    setSaving(true);
    try {
      setJob(await api<Job>(`/api/jobs/${job.id}/analyze`, { method: "POST" }));
      setSaved("Analysis refreshed.");
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : "Analysis failed.");
    } finally {
      setSaving(false);
    }
  }

  async function saveApplication() {
    if (!job || isDemoJob(job)) return;
    setSaving(true);
    setError("");
    try {
      if (application.status === "Applied") {
        const result = await api<JobLifecycleAction>(`/api/jobs/${job.id}/mark-applied`, {
          method: "POST",
        });
        if (result.application) {
          await api(`/api/applications/${result.application.id}`, {
            method: "PUT",
            body: JSON.stringify({
              status: "Applied",
              resume_type: application.resume_type,
              application_reference: application.application_reference || null,
              notes: application.notes,
            }),
          });
        }
        router.push("/jobs?notice=applied");
      } else {
        await api("/api/applications", {
          method: "POST",
          body: JSON.stringify({ job_id: job.id, ...application }),
        });
        await load();
        setSaved("Job saved.");
      }
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save application.");
    } finally {
      setSaving(false);
    }
  }

  async function markApplied() {
    if (!job || isDemoJob(job)) return;
    setSaving(true);
    setError("");
    try {
      const result = await api<JobLifecycleAction>(`/api/jobs/${job.id}/mark-applied`, {
        method: "POST",
      });
      setJob(result.job);
      setUndoStatus(result.previous_status);
      setSaved(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not mark application.");
    } finally {
      setSaving(false);
    }
  }

  async function undoApplied() {
    if (!job || !undoStatus) return;
    setSaving(true);
    try {
      const result = await api<JobLifecycleAction>(`/api/jobs/${job.id}/undo-applied`, {
        method: "POST",
        body: JSON.stringify({ previous_status: undoStatus }),
      });
      setJob(result.job);
      setUndoStatus(null);
      setSaved(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not undo application.");
    } finally {
      setSaving(false);
    }
  }

  if (error && !job) return <div className="notice error">{error}</div>;
  if (!job) return <div className="empty-state">Loading job analysis…</div>;

  const analysis = job.analysis;
  const demoJob = isDemoJob(job);
  const verifiedOfficialApplication = Boolean(
    job.official_apply_url
    && job.official_status === "open"
    && job.verification_status === "verified",
  );
  const primaryApplicationUrl = verifiedOfficialApplication && job.official_apply_url
    ? job.official_apply_url
    : job.original_source_url || job.apply_url;
  return (
    <>
      <Link href="/jobs" className="back-link"><ArrowLeft size={16} /> Back to jobs</Link>
      <header className="detail-header">
        <div>
          <div className="detail-status">
            <StatusBadge value={analysis?.recommendation ?? "Review"} />
            {analysis && <EligibilityBadge value={analysis.eligibility_status} />}
            <span>{job.source_name}</span>
            <StatusBadge value={job.status.replaceAll("_", " ")} />
            {job.is_priority_alert && <span className="priority-pill"><Siren size={12} />Priority</span>}
            <span className="urgency-pill">{job.urgency}</span>
          </div>
          <h1>{job.title}</h1>
          <p className="detail-company">{job.company}</p>
          <div className="detail-meta">
            <span><MapPin size={15} />{job.location}</span>
            <span><CalendarDays size={15} />Posted {formatDate(job.posted_at)}</span>
            {(job.application_deadline || job.expires_at) && <span><CalendarDays size={15} />Deadline {formatDate(job.application_deadline || job.expires_at)}</span>}
            <span>{job.remote_type}</span>
            <span>Remote scope: {job.remote_scope.replaceAll("_", " ")}</span>
            <span>Can work from Mexico: {job.can_work_from_mexico}</span>
            {job.duration && <span>{job.duration}</span>}
          </div>
        </div>
        <div className="header-actions">
          <button className="button secondary" onClick={analyzeAgain} disabled={saving}>
            <RefreshCw size={16} /> Reanalyze
          </button>
          {(job.status === "active" || job.status === "saved") && !demoJob && (
            <button className="button primary" onClick={() => void markApplied()} disabled={saving}>
              <FileCheck2 size={16} /> Mark as Applied
            </button>
          )}
          {!demoJob && verifiedOfficialApplication && job.original_source_url && job.original_source_url !== job.official_apply_url && (
            <a className="button secondary" href={job.original_source_url} target="_blank" rel="noreferrer">
              Discovery source <ExternalLink size={16} />
            </a>
          )}
          {demoJob ? (
            <button className="button primary" disabled title="This fixture has no real application page">
              Demo listing
            </button>
          ) : (
            <a className="button primary" href={primaryApplicationUrl} target="_blank" rel="noreferrer">
              {verifiedOfficialApplication ? "Open official application" : "Open discovery listing"} <ExternalLink size={16} />
            </a>
          )}
        </div>
      </header>

      {demoJob && (
        <div className="notice">
          This is a test fixture used to validate scoring. It has no real external application page.
        </div>
      )}
      {error && <div className="notice error">{error}</div>}
      {analysis?.eligibility_status === "NOT_ELIGIBLE" && (
        <div className="notice error"><strong>Not eligible:</strong> {analysis.blocker_reasons[0] ?? "A hard work-authorization requirement is not met."}</div>
      )}
      {saved && (
        <div className="notice success">
          {saved}
          {undoStatus && (
            <button className="button ghost" onClick={() => void undoApplied()} disabled={saving}>
              Undo
            </button>
          )}
        </div>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          <section className="content-section prose-section">
            <h2>Role summary</h2>
            <JobDescription content={job.description} />
          </section>
          <section className="content-section prose-section">
            <h2>Requirements</h2>
            <JobDescription
              content={job.requirements}
              emptyText="No separate requirements section was published."
            />
            <h3>Preferred qualifications</h3>
            <JobDescription
              content={job.preferred_qualifications}
              emptyText="No preferred qualifications were separated by the source."
            />
          </section>
          <section className="content-section">
            <div className="section-heading compact"><h2>Decision rationale</h2></div>
            {analysis?.blocker_reasons.length ? (
              <div className="reason-group blockers">
                <h3>Eligibility blockers</h3>
                {analysis.blocker_reasons.map((reason) => <p key={reason}>{reason}</p>)}
              </div>
            ) : null}
            <div className="reason-columns">
              <div className="reason-group positives">
                <h3>Positive signals</h3>
                {analysis?.positive_reasons.map((reason) => <p key={reason}>{reason}</p>)}
              </div>
              <div className="reason-group risks">
                <h3>Risks to verify</h3>
                {analysis?.risk_flags.length
                  ? analysis.risk_flags.map((reason) => <p key={reason}>{reason}</p>)
                  : <p>No material risk flags detected.</p>}
              </div>
            </div>
          </section>
        </div>

        <aside className="detail-aside">
          <section className="side-panel verification-panel">
            <div className="panel-title"><BadgeCheck size={18} /><h2>Education eligibility</h2></div>
            <dl className="verification-list">
              <div><dt>Status</dt><dd>{analysis?.education_eligibility_status.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Degree level</dt><dd>{analysis?.degree_level_match.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Field of study</dt><dd>{analysis?.degree_field_match.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Degree completion</dt><dd>{analysis?.degree_completion_match === "NO_MATCH" ? "Does not meet requirement" : analysis?.degree_completion_match.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Graduation window</dt><dd>{analysis?.graduation_window_match.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Student status</dt><dd>{analysis?.student_status_match.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
            </dl>
            <p className="status-reason">{analysis?.education_eligibility_reason || "Education requirements have not been analyzed yet."}</p>
            {job.degree_requirement_evidence && <p className="status-reason"><strong>Posting evidence:</strong> {job.degree_requirement_evidence}</p>}
          </section>

          <section className="side-panel verification-panel">
            <div className="panel-title"><BadgeCheck size={18} /><h2>Special Program Eligibility</h2></div>
            <dl className="verification-list">
              <div><dt>Status</dt><dd>{analysis?.special_program_eligibility_status.replaceAll("_", " ") ?? "UNKNOWN"}</dd></div>
              <div><dt>Program type</dt><dd>{job.special_program_type.replaceAll("_", " ")}</dd></div>
              <div><dt>Membership required</dt><dd>{job.special_program_required ? "Yes" : "No"}</dd></div>
            </dl>
            <p className="status-reason">{analysis?.special_program_eligibility_reason || "Special-program requirements have not been analyzed yet."}</p>
            {job.special_program_evidence && <p className="status-reason"><strong>Posting evidence:</strong> {job.special_program_evidence}</p>}
          </section>

          <section className="side-panel verification-panel">
            <div className="panel-title">
              {job.verification_status === "verified" ? <BadgeCheck size={18} /> : <SearchCheck size={18} />}
              <h2>Official verification</h2>
            </div>
            <dl className="verification-list">
              <div><dt>Official status</dt><dd>{job.official_status}</dd></div>
              <div><dt>Verification</dt><dd>{job.verification_status.replaceAll("_", " ")}</dd></div>
              <div><dt>Last checked</dt><dd>{formatDate(job.last_verified_at)}</dd></div>
              <div><dt>Method</dt><dd>{job.verification_method.replaceAll("_", " ")}</dd></div>
              <div><dt>Physical work country</dt><dd>{job.physical_work_country_required}</dd></div>
              <div><dt>Remote scope</dt><dd>{job.remote_scope.replaceAll("_", " ")}</dd></div>
              <div><dt>Can work from Mexico</dt><dd>{job.can_work_from_mexico}</dd></div>
              <div><dt>Sponsorship</dt><dd>{job.sponsorship_status.replaceAll("_", " ")}</dd></div>
            </dl>
            {job.sponsorship_evidence_text && <p className="status-reason"><strong>Evidence:</strong> {job.sponsorship_evidence_text}</p>}
            {job.sponsorship_source_url && <a href={job.sponsorship_source_url} target="_blank" rel="noreferrer">Open evidence source <ExternalLink size={13} /></a>}
            <p className="status-reason">{job.status_reason || "No verification detail is available."}</p>
          </section>

          <section className="side-panel verification-panel">
            <div className="panel-title"><SearchCheck size={18} /><h2>Sources</h2></div>
            <dl className="verification-list">
              <div><dt>Discovered via</dt><dd>{job.discovered_from_source || job.source_name}</dd></div>
              <div><dt>Verified via</dt><dd>{job.verified_from_source || "Not officially verified"}</dd></div>
              <div><dt>Last verified</dt><dd>{formatDate(job.last_verified_at)}</dd></div>
              <div><dt>Seen on</dt><dd>{Math.max(1, job.discovery_sources.length)} source{job.discovery_sources.length === 1 ? "" : "s"}</dd></div>
              <div><dt>Source confidence</dt><dd>{Math.round(job.source_confidence_score)}/100</dd></div>
            </dl>
            {job.discovery_sources.length > 0 && <p className="status-reason">{job.discovery_sources.join(" · ")}</p>}
            {job.community_sponsorship_signal !== "UNKNOWN" && (
              <p className="status-reason">Community sponsorship hint: {job.community_sponsorship_signal.replaceAll("_", " ")}. This is not treated as an official fact.</p>
            )}
          </section>

          <section className="side-panel score-panel">
            <div className="overall-score">
              <span>Effective score</span>
              <strong>{Math.round(analysis?.effective_score ?? analysis?.overall_score ?? 0)}</strong>
            </div>
            <ScoreBar label="Technical" value={analysis?.technical_score ?? 0} />
            <ScoreBar label="Academic" value={analysis?.academic_score ?? 0} />
            <ScoreBar label="Eligibility" value={analysis?.eligibility_score ?? 0} />
            <ScoreBar label="Level" value={analysis?.level_score ?? 0} />
            <ScoreBar label="Logistics" value={analysis?.logistics_score ?? 0} />
            <ScoreBar label="Freshness" value={analysis?.freshness_score ?? 0} />
            {Boolean(analysis?.remote_eligibility_bonus) && <p className="score-explanation">Eligible remote/logistics bonus: +{analysis?.remote_eligibility_bonus}</p>}
            <p className="score-explanation">{analysis?.explanation}</p>
          </section>

          <section className="side-panel application-panel">
            <div className="panel-title"><FileCheck2 size={18} /><h2>Track this role</h2></div>
            <label>
              Status
              <select
                value={application.status}
                onChange={(event) => setApplication({ ...application, status: event.target.value })}
              >
                <option>Saved</option>
                <option>Applied</option>
                <option>Interview</option>
                <option>Offer</option>
                <option>Rejected</option>
                <option>Not interested</option>
              </select>
            </label>
            <label>
              Resume used
              <select
                value={application.resume_type}
                onChange={(event) => setApplication({ ...application, resume_type: event.target.value })}
              >
                <option>Software / SDE</option>
                <option>Firmware / Embedded</option>
                <option>FPGA / RTL / Digital Design</option>
                <option>Hardware Test / Validation</option>
                <option>Robotics / Controls</option>
                <option>General Engineering</option>
              </select>
            </label>
            <label>
              Application ID
              <input
                value={application.application_reference}
                onChange={(event) => setApplication({ ...application, application_reference: event.target.value })}
                placeholder="Optional"
              />
            </label>
            <label>
              Notes
              <textarea
                rows={3}
                value={application.notes}
                onChange={(event) => setApplication({ ...application, notes: event.target.value })}
              />
            </label>
            <button className="button primary full" onClick={saveApplication} disabled={saving || demoJob}>
              {application.status === "Applied" ? <FileCheck2 size={16} /> : <Save size={16} />}
              {demoJob
                ? "Demo job cannot be applied"
                : application.status === "Applied"
                  ? "Record application"
                  : "Save to tracker"}
            </button>
          </section>
        </aside>
      </div>
      {analysis?.eligibility_status !== "NOT_ELIGIBLE" && <RecommendedResumeSection job={job} />}
    </>
  );
}
