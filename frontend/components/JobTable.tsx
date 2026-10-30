import { Archive, ArrowUpRight, BadgeCheck, FileCheck2, MapPin, RotateCcw, Siren } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import { EligibilityBadge } from "@/components/EligibilityBadge";
import type { Job } from "@/lib/types";
import { formatDate } from "@/lib/api";
import { primaryEligibilityReason } from "@/lib/eligibility";
import { displayedJobAction } from "@/lib/job-action";
import { jobDetailHref } from "@/lib/job-navigation";

const gdlMetro = /guadalajara|zapopan|tlaquepaque|tlajomulco|el salto|jalisco|\bgdl\b/i;

export function JobTable({
  jobs,
  empty = "No jobs match these filters.",
  lifecycle = "active",
  pendingJobId,
  onMarkApplied,
  onRemoveApplied,
  onArchive,
  onRestore,
  returnTo,
}: {
  jobs: Job[];
  empty?: string;
  lifecycle?: string;
  pendingJobId?: number | null;
  onMarkApplied?: (job: Job) => void;
  onRemoveApplied?: (job: Job) => void;
  onArchive?: (job: Job) => void;
  onRestore?: (job: Job) => void;
  returnTo?: string;
}) {
  if (!jobs.length) {
    return <div className="empty-state">{empty}</div>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Location</th>
            <th>Recommendation</th>
            {lifecycle === "applied" && <th>Applied / Resume</th>}
            {lifecycle === "expired" && <th>Deadline</th>}
            <th className="number-cell">Score</th>
            <th><span className="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <div className="job-title-line">
                  <Link className="job-link" href={jobDetailHref(job.id, returnTo)}>{job.title}</Link>
                  {job.is_priority_alert && <span className="priority-pill"><Siren size={12} />{job.is_priority_pinned ? "Pinned high priority" : "Priority"}</span>}
                  {job.is_target_company && <span className="priority-pill">Target company</span>}
                </div>
                <span className="subtext">{job.company}</span>
                <div className="job-source-badges">
                  {gdlMetro.test(`${job.location} ${job.city} ${job.region}`) && <span>Guadalajara Metro</span>}
                  {job.remote_scope === "MEXICO" && <span>Remote Mexico</span>}
                  {job.remote_scope === "LATAM" && <span>Remote LATAM</span>}
                  {job.remote_type === "Hybrid" && <span>Hybrid</span>}
                  {job.remote_type === "On-site" && <span>On-site</span>}
                  {job.official_domain && <span>Official source</span>}
                  {job.official_status === "open" && job.verification_status === "verified" && <span>Verified open</span>}
                  {job.analysis?.risk_flags.some((risk) => /sponsor|work permit/i.test(risk)) && <span>Sponsorship unclear</span>}
                  {job.analysis?.risk_flags.some((risk) => /location restriction|remote location/i.test(risk)) && <span>Location restriction</span>}
                </div>
              </td>
              <td>
                <span className="location"><MapPin size={14} />{job.location}</span>
                <span className="subtext">{job.remote_type} · {job.area}</span>
                <span className="subtext">Scope: {job.remote_scope.replaceAll("_", " ")} · From Mexico: {job.can_work_from_mexico}</span>
              </td>
              <td>
                <StatusBadge value={displayedJobAction(job)} />
                {job.analysis && <EligibilityBadge value={job.analysis.eligibility_status} />}
                {job.force_apply_now_available && (
                  <span className="priority-pill">Apply Now · manual override</span>
                )}
                {job.analysis?.eligibility_status === "NOT_ELIGIBLE" && (
                  <span className="eligibility-blocker">{primaryEligibilityReason(job)}</span>
                )}
                <span className="verification-line">
                  {job.verification_status === "verified" && job.official_status === "open"
                    ? <><BadgeCheck size={12} /> Officially verified</>
                    : job.urgency}
                </span>
                <span className="subtext">Last verified: {job.last_verified_at ? formatDate(job.last_verified_at) : "Pending"}</span>
              </td>
              {lifecycle === "applied" && (
                <td>
                  <span>{formatDate(job.applied_at)}</span>
                  <span className="subtext">
                    {job.submitted_resume_id
                      ? `${job.submitted_resume_type ?? "Submitted CV"} · CV #${job.submitted_resume_id}`
                      : "No CV associated"}
                  </span>
                  {job.application_status && <span className="subtext">Process: {job.application_status}</span>}
                </td>
              )}
              {lifecycle === "expired" && <td>{formatDate(job.application_deadline)}</td>}
              <td className="number-cell score-number">{Math.round(job.analysis?.effective_score ?? job.analysis?.overall_score ?? 0)}</td>
              <td className="icon-cell">
                {(lifecycle === "active" || lifecycle === "saved") && onMarkApplied && (
                  <button
                    className="icon-button"
                    disabled={pendingJobId === job.id}
                    onClick={() => onMarkApplied(job)}
                    aria-label={`Mark ${job.title} as applied`}
                  >
                    <FileCheck2 size={17} />
                  </button>
                )}
                {lifecycle === "applied" && job.application_status === "Applied" && onRemoveApplied && (
                  <button className="icon-button" disabled={pendingJobId === job.id} onClick={() => onRemoveApplied(job)} aria-label={`Remove Applied from ${job.title}`} title="Remove Applied">
                    <RotateCcw size={17} />
                  </button>
                )}
                {onArchive && (
                  <button className="icon-button" disabled={pendingJobId === job.id} onClick={() => onArchive(job)} aria-label={`Archive ${job.title}`} title="Archive job (reversible)">
                    <Archive size={17} />
                  </button>
                )}
                {onRestore && (
                  <button className="icon-button" disabled={pendingJobId === job.id} onClick={() => onRestore(job)} aria-label={`Restore ${job.title}`}>
                    <RotateCcw size={17} />
                  </button>
                )}
                <Link href={jobDetailHref(job.id, returnTo)} className="icon-button" aria-label={`Open ${job.title}`}>
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
