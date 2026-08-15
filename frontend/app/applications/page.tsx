"use client";

import { ExternalLink, Save, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, backendAssetUrl, formatDate } from "@/lib/api";
import type { Application } from "@/lib/types";

const statuses = ["Saved", "Applied", "Interview", "Offer", "Rejected", "Withdrawn", "Not interested"];

export default function ApplicationsPage() {
  const [items, setItems] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api<Application[]>("/api/applications"));
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
    try {
      await api(`/api/applications/${id}`, { method: "DELETE" });
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
                      <Link className="job-link" href={`/jobs/${item.job.id}`}>{item.job.title}</Link>
                      <span className="subtext">{item.job.company}</span>
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
                          aria-label={`Notes for ${item.job.title}`}
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
                        href={item.job.apply_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label="Open application page"
                      >
                        <ExternalLink size={16} />
                      </a>
                      <button
                        className="icon-button danger"
                        onClick={() => void removeItem(item.id)}
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
    </>
  );
}
