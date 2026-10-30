"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";

type ImportResult = {
  job_id: number;
  created: boolean;
  existing_job_reused: boolean;
  verified: boolean;
  official_status: string;
  candidate_analysis_created: boolean;
  force_apply_now: boolean;
  force_apply_error: string | null;
};

export function AddJobByUrl() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [forceApply, setForceApply] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim() || busy) return;
    setBusy(true);
    setStatus("Fetching the posting, checking its source and duplicates, then analyzing it for your profile...");
    try {
      const result = await api<ImportResult>("/api/jobs/import-url", {
        method: "POST",
        body: JSON.stringify({ url: url.trim(), force_apply_now: forceApply }),
      });
      setStatus(result.force_apply_error || (
        result.created ? "Job imported successfully." : "Existing job found and reused."
      ));
      const imported = new URLSearchParams({
        import_result: result.created ? "created" : "reused",
        import_verified: result.verified ? "true" : "false",
      });
      if (result.force_apply_error) imported.set("import_warning", result.force_apply_error);
      router.push(`/jobs/${result.job_id}?${imported.toString()}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to extract this job.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="button primary" type="button" onClick={() => { setStatus(""); setOpen(true); }}>+ Add Job</button>
      {open && (
        <div className="assistant-modal-backdrop" role="presentation" onClick={() => { if (!busy) setOpen(false); }}>
          <section className="assistant-modal add-job-dialog" role="dialog" aria-modal="true" aria-label="Add job by URL" onClick={(event) => event.stopPropagation()}>
            <h2>Add Job by URL</h2>
            <p>Paste an official job posting or a supported job-board link. Existing jobs will be reused.</p>
            <form onSubmit={(event) => void submit(event)}>
              <label htmlFor="new-job-url">Job URL</label>
              <input id="new-job-url" type="url" required autoFocus value={url} disabled={busy} onChange={(event) => setUrl(event.target.value)} placeholder="https://company.com/jobs/123" />
              <label className="toggle-label">
                <input type="checkbox" checked={forceApply} disabled={busy} onChange={(event) => setForceApply(event.target.checked)} />
                Mark as Apply Now for me
              </label>
              <p className="muted">Manual Apply Now does not change eligibility, score, or blockers. Closed applications cannot be overridden.</p>
              {status && <p role="status" aria-live="polite">{status}</p>}
              <div className="header-actions">
                <button className="button secondary" type="button" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
                <button className="button primary" type="submit" disabled={busy || !url.trim()}>{busy ? "Adding job..." : forceApply ? "Add Job + Apply Now" : "Add Job"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
