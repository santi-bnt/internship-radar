"use client";

import { ExternalLink, History, Save, Send, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, backendAssetUrl, formatDate } from "@/lib/api";
import type { Application, ApplicationSession } from "@/lib/types";

const statuses = ["Saved", "Applied", "Interview", "Offer", "Rejected", "Withdrawn", "Not interested"];

export default function ApplicationsPage() {
  const [items, setItems] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [sessions, setSessions] = useState<ApplicationSession[]>([]);

  const load = useCallback(async () => {
    try {
      const [applications, applicationSessions] = await Promise.all([
        api<Application[]>("/api/applications"),
        api<ApplicationSession[]>("/api/application-sessions"),
      ]);
      setItems(applications);
      setSessions(applicationSessions);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load applications.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function updateItem(id: number, changes: Partial<Application>) {
    try {
      const updated = await api<Application>(`/api/applications/${id}`, {
        method: "PUT",
        body: JSON.stringify(changes),
      });
      setItems((current) => current.map((item) => (item.id === id ? updated : item)));
      setMessage("Application updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Update failed.");
    }
  }

  async function removeItem(id: number) {
    if (!window.confirm("Permanently delete this application record and its status history? This does not delete the job.")) return;
    try {
      await api(`/api/applications/${id}?confirm=true`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== id));
      setMessage("Application removed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed.");
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Personal pipeline</p>
          <h1>Applications</h1>
          <p className="page-subtitle">{items.length} tracked submissions and saved roles.</p>
        </div>
        <Link href="/jobs" className="button primary"><Send size={16} /> Find a role</Link>
      </header>

      {message && <div className="notice" role="status">{message}</div>}
      <section className="content-section">
        {loading ? (
          <div className="empty-state">Loading your applications…</div>
        ) : items.length === 0 ? (
          <div className="empty-state tall">
            <Send size={24} />
            <strong>No applications tracked yet</strong>
            <span>Open a job and save or record it from the detail page.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Resume</th>
                  <th>Applied</th>
                  <th>Notes</th>
                  <th><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link className="job-link" href={item.job ? `/jobs/${item.job.id}` : "/talent-communities"}>{item.job?.title || "Talent Community"}</Link>
                      <span className="subtext">{item.job?.company || item.company}</span>
                    </td>
                    <td>
                      <select
                        className="table-select"
                        value={item.status}
                        onChange={(event) => void updateItem(item.id, { status: event.target.value })}
                      >
                        {statuses.map((status) => <option key={status}>{status}</option>)}
                      </select>
                    </td>
                    <td>
                      <span>{item.resume_type}</span>
                      {item.submitted_resume_id && (
                        <a
                          className="subtext"
                          href={backendAssetUrl(`/api/generated-resumes/${item.submitted_resume_id}/pdf`)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open submitted CV #{item.submitted_resume_id}
                        </a>
                      )}
                    </td>
                    <td>{formatDate(item.applied_at)}</td>
                    <td>
                      <div className="inline-edit">
                        <input
                          defaultValue={item.notes}
                          aria-label={`Notes for ${item.job?.title || item.company}`}
                          onBlur={(event) => {
                            if (event.target.value !== item.notes) {
                              void updateItem(item.id, { notes: event.target.value });
                            }
                          }}
                        />
                        <Save size={14} />
                      </div>
                    </td>
                    <td className="action-cell">
                      <a
                        className="icon-button"
                        href={item.job?.apply_url || item.talent_community_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label="Open application page"
                      >
                        <ExternalLink size={16} />
                      </a>
                      <button
                        className="icon-button danger"
                        onClick={() => void removeItem(item.id)}
                        title="Permanently delete application record"
                        aria-label="Remove application"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="content-section application-history-section">
        <div className="section-heading compact">
          <div><p className="eyebrow">Apply Assistant</p><h2>Application History</h2></div>
          <History size={20} />
        </div>
        {sessions.length === 0 ? (
          <div className="empty-state"><span>No assisted application sessions yet.</span></div>
        ) : (
          <div className="application-session-list">
            {sessions.map((session) => {
              const snapshot = session.job_snapshot_json as { title?: string; company?: string; resume_version?: number; description?: string };
              return (
                <details key={session.id} className="application-session-card">
                  <summary>
                    <div><strong>{snapshot.title || "Application"}</strong><span>{session.company || snapshot.company} · {session.portal_type}</span></div>
                    <div><span className={`session-status ${session.status.toLowerCase()}`}>{session.status.replaceAll("_", " ")}</span><time>{formatDate(session.completed_at || session.updated_at)}</time></div>
                  </summary>
                  <div className="application-session-details">
                    <dl>
                      <div><dt>Resume</dt><dd>Version {snapshot.resume_version ?? session.resume_version_id}</dd></div>
                      <div><dt>Current step</dt><dd>{session.current_step}</dd></div>
                      <div><dt>Fields filled</dt><dd>{session.fields_filled_count}</dd></div>
                      <div><dt>Confirmed answers</dt><dd>{session.fields_confirmed_count}</dd></div>
                      <div><dt>Portal job ID</dt><dd>{session.portal_job_id || "Not detected"}</dd></div>
                      <div><dt>Adapter</dt><dd>{session.adapter_version || "Not reported"}</dd></div>
                      <div><dt>Company policy</dt><dd>{session.company_policy_key || "GENERIC"}</dd></div>
                      <div><dt>Assessment</dt><dd>{session.assessment_type || "None detected"}</dd></div>
                      <div><dt>Started</dt><dd>{formatDate(session.started_at)}</dd></div>
                    </dl>
                    <div className="application-session-actions">
                      <a className="button secondary" href={backendAssetUrl(`/api/generated-resumes/${session.resume_version_id}/pdf`)} target="_blank" rel="noreferrer">Open resume used</a>
                      <a className="button secondary" href={session.application_url} target="_blank" rel="noreferrer">Open application <ExternalLink size={14} /></a>
                    </div>
                    {Object.keys(session.application_answers_json).length > 0 && (
                      <div className="confirmed-answer-summary"><ShieldCheck size={16} /><span>{Object.keys(session.application_answers_json).length} sensitive answer(s) explicitly confirmed for this application.</span></div>
                    )}
                    {session.consistency_issues_json.length > 0 && (
                      <div className="notice error">{session.consistency_issues_json.length} consistency issue(s) require review.</div>
                    )}
                    {session.error_code === "PORTAL_CHANGED" && (
                      <div className="notice error">This portal may have changed. Safe autofill was paused and the session requires manual completion.</div>
                    )}
                    {snapshot.description && <details className="job-snapshot"><summary>Job description snapshot</summary><p>{snapshot.description}</p></details>}
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
