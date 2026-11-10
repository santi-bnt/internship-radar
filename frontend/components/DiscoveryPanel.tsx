"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, formatDate } from "@/lib/api";
import { Opportunity, safeWebsite } from "@/lib/opportunities";

type Result = {
  id: number; title: string; company: string; location: string; country: string;
  canonicalUrl: string; sourceUrl: string; sourceName: string; discoveredFrom: string;
  postedAt: string | null; firstSeenAt: string; fitScore: number | null; eligibilityScore: number | null;
  canApplyFromMexico: string; internationalEligibility: string; visaSponsorship: string; fundingType: string; deadline: string | null;
  researchAreas: string[]; skills: string[]; verificationStatus: string; isNew: boolean;
  applicationStatus: string; opportunityType: string; studentLevel: string; status: string; duplicateCandidateId: number | null; eligibilityEvidence: string[];
  rawMetadata: { attribution?: string | null };
};
type Run = {id: number; status: string; progress: string; rawResults: number; newJobs: number; updatedJobs: number; errors: number; startedAt: string; cached?: boolean; results?: Result[]; summary?: {duplicates_removed?: number}};
type Health = {sources: {id: number; source: string; company: string; health: string; enabled: boolean; lastSuccessfulRun: string | null; jobsFetched: number; errors: number; averageRuntimeMs: number | null; message: string}[]};

export default function DiscoveryPanel({ onSaved }: {onSaved: (value: Opportunity) => void}) {
  const readOnly = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
  const [query, setQuery] = useState("");
  const [countries, setCountries] = useState("United States, Canada");
  const [newDays, setNewDays] = useState(3);
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function refreshHealth() {
    const [healthData, historyData] = await Promise.all([api<Health>("/api/discovery/health"), api<Run[]>("/api/discovery/runs")]);
    setHealth(healthData); setHistory(historyData);
  }
  useEffect(() => {let active = true; api<Result[]>(`/api/discovery/results?new_days=${newDays}`).then(data => {if (active) setResults(data);}).catch(() => {}); return () => {active = false;};}, [newDays]);
  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api<Run>(`/api/discovery/runs/${runId}`);
        if (cancelled) return;
        setRun(current);
        if (["completed", "failed"].includes(current.status)) {
          setResults(current.results || []); setBusy(false); setRunId(null);
          await refreshHealth();
        } else timer = setTimeout(() => void poll(), 2000);
      } catch (err) {if (!cancelled) {setError(err instanceof Error ? err.message : "Search status unavailable"); setBusy(false); setRunId(null);}}
    }
    void poll();
    return () => {cancelled = true; clearTimeout(timer);};
  }, [runId]);

  async function search(mode: "quick" | "deep") {
    setBusy(true); setError(""); setRun(null);
    try {
      const started = await api<{runId: number}>("/api/discovery/search", {method: "POST", body: JSON.stringify({mode, query, countries: countries.split(",").map(s => s.trim()).filter(Boolean), new_days: newDays})});
      setRunId(started.runId);
    } catch (err) {setError(err instanceof Error ? err.message : "Discovery failed"); setBusy(false);}
  }
  const score = (value: number | null) => value === null ? "Unknown" : `${Math.round(value)}/100`;

  return <div className="discovery-panel">
    <h3>Search configured sources</h3>
    {readOnly && <p className="notice">Read-only demo: live search and saving are available in a configured private installation.</p>}
    <p className="opportunity-caption">Quick Search checks fast ATS and enabled discovery sources. Deep Search also includes configured web, research and experimental sources. Each source keeps its own cadence; recent results can be cached.</p>
    <div className="form-grid"><label>Interests or keywords<input placeholder="Use my profile, or enter robotics, firmware, AI…" value={query} onChange={e => setQuery(e.target.value)} maxLength={600} /></label><label>Countries<input value={countries} onChange={e => setCountries(e.target.value)} /></label><label>Newly discovered within<select value={newDays} onChange={e => setNewDays(Number(e.target.value))}><option value={1}>24 hours</option><option value={3}>3 days</option><option value={7}>7 days</option></select></label></div>
    <div className="header-actions"><button className="button" disabled={readOnly || busy} onClick={() => void search("quick")}>Quick Search</button><button className="button secondary" disabled={readOnly || busy} onClick={() => void search("deep")}>Deep Search</button><button className="button secondary" onClick={() => void refreshHealth().catch(err => setError(err instanceof Error ? err.message : "Source status unavailable"))}>Source Health &amp; History</button></div>
    {error && <p className="notice" role="alert">{error}</p>}
    {busy && <p role="status">{run?.progress || "Starting discovery…"}</p>}
    {run && !busy && <p className="notice" role="status">{run.progress}. Found: {run.rawResults}; new: {run.newJobs}; updated: {run.updatedJobs}; duplicates: {run.summary?.duplicates_removed || 0}; source errors: {run.errors}.{run.cached ? " Showing cached opportunities." : ""}</p>}
    <p className="opportunity-caption">Fit measures technical interests; eligibility is a separate rules-based assessment, not a visa or admission guarantee. Unknown facts remain Unknown. Search does not apply, upload a CV or send messages.</p>
    <div className="opportunity-grid">{results.map(r => <article className="opportunity-card" key={r.id}>
      <div className="opportunity-tags">{r.isNew && <span className="opportunity-badge">NEW</span>}{r.verificationStatus === "verified" && <span className="opportunity-badge">VERIFIED</span>}{r.internationalEligibility === "confirmed" && <span className="opportunity-badge">INTERNATIONAL</span>}{["Fully funded", "Paid", "Stipend"].some(f => r.fundingType.includes(f)) && <span className="opportunity-badge">FUNDED</span>}{r.opportunityType === "research" && <span className="opportunity-badge">RESEARCH</span>}{r.researchAreas.filter(a => ["Robotics", "Artificial Intelligence", "Embedded Systems"].includes(a)).map(a => <span className="opportunity-badge" key={a}>{a === "Artificial Intelligence" ? "AI" : a === "Embedded Systems" ? "EMBEDDED" : "ROBOTICS"}</span>)}<span className="opportunity-badge">{r.country}</span></div>
      <h3>{r.title}</h3><p>{r.company} · {r.location}</p>
      <dl><div><dt>Fit</dt><dd>{score(r.fitScore)}</dd></div><div><dt>Eligibility</dt><dd>{score(r.eligibilityScore)}</dd></div><div><dt>International</dt><dd>{r.internationalEligibility}</dd></div><div><dt>Mexican applicant</dt><dd>{r.canApplyFromMexico}</dd></div><div><dt>Visa sponsorship</dt><dd>{r.visaSponsorship}</dd></div><div><dt>Funding</dt><dd>{r.fundingType}</dd></div><div><dt>Published</dt><dd>{r.postedAt ? formatDate(r.postedAt) : "Unknown"}</dd></div><div><dt>Discovered</dt><dd>{formatDate(r.firstSeenAt)}</dd></div><div><dt>Deadline</dt><dd>{r.deadline ? formatDate(r.deadline) : "Unknown"}</dd></div><div><dt>Source</dt><dd>{r.discoveredFrom || r.sourceName}</dd></div><div><dt>Availability</dt><dd>{r.status}</dd></div></dl>
      <p>{r.researchAreas.join(", ") || r.skills.slice(0, 6).join(", ") || "Research areas: Unknown"}</p>
      {!!r.eligibilityEvidence.length && <p className="opportunity-caption">{r.eligibilityEvidence.join("; ")}</p>}
      {r.duplicateCandidateId && <p className="notice">Possible duplicate of opportunity #{r.duplicateCandidateId}. Review before merging.</p>}
      {r.rawMetadata.attribution && <p className="opportunity-caption">{r.rawMetadata.attribution}</p>}
      <div className="header-actions"><a className="button secondary" href={safeWebsite(r.canonicalUrl)} target="_blank" rel="noopener noreferrer">{r.verificationStatus === "verified" ? "Official source" : "Review source"}</a><a href={safeWebsite(r.sourceUrl)} target="_blank" rel="noopener noreferrer">Discovery source</a><Link href={`/jobs/${r.id}`}>View Details</Link><button className="button" disabled={saving === r.id || r.status === "CLOSED" || ["saved", "applied"].includes(r.applicationStatus)} onClick={async () => {setSaving(r.id); setError(""); try {onSaved(await api<Opportunity>(`/api/discovery/${r.id}/save`, {method: "POST"})); setResults(values => values.map(value => value.id === r.id ? {...value, applicationStatus: "saved"} : value));} catch (err) {setError(err instanceof Error ? err.message : "Save failed");} finally {setSaving(null);}}}>{r.applicationStatus === "applied" ? "Already Applied" : r.applicationStatus === "saved" ? "Saved" : "Add to Opportunities"}</button></div>
    </article>)}</div>
    {health && <details open><summary>Source Health</summary><div className="table-wrap"><table><thead><tr><th>Company / Source</th><th>Health</th><th>Last success</th><th>Fetched</th><th>Errors</th><th>Average runtime</th></tr></thead><tbody>{health.sources.filter(s => s.enabled).map(s => <tr key={s.id}><td>{s.company} / {s.source}</td><td>{s.health}</td><td>{s.lastSuccessfulRun ? formatDate(s.lastSuccessfulRun) : "Not run"}</td><td>{s.jobsFetched}</td><td>{s.errors}</td><td>{s.averageRuntimeMs === null ? "Unknown" : `${s.averageRuntimeMs} ms`}</td></tr>)}</tbody></table></div><p className="opportunity-caption">Scheduled cadence: fast ATS and optional Freehire 6h, experimental Workday 12h, configured web/research 24h. The server checks a bounded queue hourly.</p></details>}
    {!!history.length && <details><summary>Search Run History</summary>{history.map(h => <p key={h.id}>#{h.id} · {h.status} · {formatDate(h.startedAt)} · {h.rawResults} found · {h.newJobs} new · {h.updatedJobs} updated · {h.errors} errors</p>)}</details>}
  </div>;
}
