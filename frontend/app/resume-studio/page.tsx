"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, FileCode2, FileText, RefreshCw, Sparkles } from "lucide-react";
import { api, backendAssetUrl, formatDate } from "@/lib/api";
import type { GeneratedResume, ResumeStudioAnalysis, ResumeStudioProfile } from "@/lib/types";

const dimensionLabels: Record<string, string> = {
  relevance: "Relevance", technical_depth: "Technical depth", project_scope: "Scope",
  system_integration: "Integration", ownership: "Ownership", outcome_completeness: "Outcome",
  differentiation: "Differentiation",
};

export default function ResumeStudioPage() {
  const [profiles, setProfiles] = useState<ResumeStudioProfile[]>([]);
  const [profileId, setProfileId] = useState("general");
  const [analysis, setAnalysis] = useState<ResumeStudioAnalysis | null>(null);
  const [history, setHistory] = useState<GeneratedResume[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");
  const selected = history.find((item) => item.id === selectedId) ?? null;
  const [bestAnalysis, setBestAnalysis] = useState<{ can_generate: boolean; description: string; plan: Record<string, unknown> } | null>(null);
  const [bestHistory, setBestHistory] = useState<GeneratedResume[]>([]);
  const [bestSelectedId, setBestSelectedId] = useState<number | null>(null);
  const [bestLoading, setBestLoading] = useState(true);
  const [bestGenerating, setBestGenerating] = useState(false);
  const [bestMessage, setBestMessage] = useState("");
  const [showBestLatex, setShowBestLatex] = useState(false);
  const [showBestContent, setShowBestContent] = useState(false);
  const [dismissedStaleId, setDismissedStaleId] = useState<number | null>(null);
  const bestSelected = bestHistory.find((item) => item.id === bestSelectedId) ?? null;
  const selectedBestId = bestSelected?.id ?? null;
  const selectedBestStatus = bestSelected?.status;
  const bestInProgress = selectedBestStatus === "queued" || selectedBestStatus === "generating";
  const bestProjectNames = Array.isArray(bestSelected?.tailored_content_json.projects)
    ? (bestSelected.tailored_content_json.projects as Array<{ name?: string }>).map((project) => project.name).filter(Boolean).join(" · ")
    : "";

  useEffect(() => {
    const controller = new AbortController();
    void api<ResumeStudioProfile[]>("/api/resume-studio/profiles", { signal: controller.signal })
      .then(setProfiles).catch((error: unknown) => {
        if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Could not load profiles.");
      });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setAnalysis(null);
    setHistory([]);
    setSelectedId(null);
    setMessage("");
    const query = `?profile_id=${encodeURIComponent(profileId)}`;
    void Promise.all([
      api<ResumeStudioAnalysis>(`/api/resume-studio/analysis${query}`, { signal: controller.signal }),
      api<GeneratedResume[]>(`/api/resume-studio/resumes${query}`, { signal: controller.signal }),
    ]).then(([fresh, versions]) => {
      if (controller.signal.aborted) return;
      setAnalysis(fresh);
      setHistory(versions);
      setSelectedId(versions.find((item) => item.status === "compiled")?.id ?? null);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Could not analyze this profile.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [profileId, revision]);

  useEffect(() => {
    const controller = new AbortController();
    setBestLoading(true);
    setBestMessage("");
    void Promise.all([
      api<{ can_generate: boolean; description: string; plan: Record<string, unknown> }>("/api/best-resume/analysis", { signal: controller.signal }),
      api<GeneratedResume[]>("/api/best-resume/versions", { signal: controller.signal }),
    ]).then(([analysis, versions]) => {
      if (controller.signal.aborted) return;
      setBestAnalysis(analysis);
      setBestHistory(versions);
      setBestSelectedId(versions[0]?.id ?? null);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setBestMessage(error instanceof Error ? error.message : "Could not load Best Resume.");
    }).finally(() => {
      if (!controller.signal.aborted) setBestLoading(false);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedBestId || !bestInProgress) return;
    const timer = window.setInterval(() => {
      void api<GeneratedResume[]>("/api/best-resume/versions").then((versions) => {
        setBestHistory(versions);
        const fresh = versions.find((version) => version.id === selectedBestId);
        if (fresh?.status === "compiled") setBestMessage(`Best Resume v${fresh.version} is ready.`);
        if (fresh?.status === "failed" || fresh?.status === "failed_retryable") {
          setBestMessage(fresh.generation_error || "Best Resume generation failed. Retry to continue.");
        }
      }).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [selectedBestId, bestInProgress]);

  async function generate() {
    if (!analysis?.can_generate || generating) return;
    setGenerating(true);
    setMessage("");
    try {
      const version = await api<GeneratedResume>(`/api/resume-studio/resumes?profile_id=${encodeURIComponent(profileId)}`, { method: "POST" });
      setHistory((current) => [version, ...current]);
      setSelectedId(version.id);
      setMessage("Your profile CV is ready. The PDF contains a snapshot of your verified profile.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "CV generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function generateBestResume() {
    if (!bestAnalysis?.can_generate || bestGenerating) return;
    setBestGenerating(true);
    setBestMessage("");
    try {
      const version = await api<GeneratedResume>("/api/best-resume/versions", { method: "POST" });
      setBestHistory((current) => [version, ...current]);
      setBestSelectedId(version.id);
      setDismissedStaleId(null);
      setShowBestLatex(false);
      setShowBestContent(false);
      setBestMessage(version.status === "compiled"
        ? `Best Resume v${version.version} is ready.`
        : `Best Resume v${version.version} is queued for generation.`);
    } catch (error) {
      setBestMessage(error instanceof Error ? error.message : "Best Resume generation failed.");
    } finally {
      setBestGenerating(false);
    }
  }

  return <>
    <header className="page-header">
      <div><p className="eyebrow">Your strongest portfolio</p><h1>Resume Studio</h1><p className="page-subtitle">Best CV by technical profile, plus a general CV with your strongest complementary projects.</p></div>
      <button className="button secondary" disabled={loading || generating} onClick={() => setRevision((value) => value + 1)}><RefreshCw size={16} /> Reanalyze</button>
    </header>

    <section className="resume-card" aria-labelledby="best-resume-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Candidate-wide · Independent from job tailoring</p><h2 id="best-resume-heading">Best Resume</h2></div>
        <button className="button primary" disabled={bestLoading || bestGenerating || bestInProgress || !bestAnalysis?.can_generate} onClick={() => void generateBestResume()}>
          <Sparkles size={16} /> {bestGenerating || selectedBestStatus === "generating" ? "Generating Best Resume…" : bestInProgress ? "Best Resume queued…" : selectedBestStatus === "failed_retryable" ? "Retry Best Resume" : bestHistory.length ? "Regenerate Best Resume" : "Generate Best Resume"}
        </button>
      </div>
      <p>Generate a resume using your strongest verified projects, experience, skills, and certifications.</p>
      {bestLoading && <p role="status">Loading the latest Best Resume…</p>}
      {bestMessage && <div className="notice" role="status">{bestMessage}</div>}
      {!bestLoading && bestAnalysis && <>
        <p className="studio-note">Evidence is selected dynamically for overall resume value. Opening this page loads the latest saved version and never regenerates it automatically.</p>
        {bestSelected?.is_stale && dismissedStaleId !== bestSelected.id && <div className="notice" role="status">
          <p>Your profile has changed since this resume was generated.</p>
          <div className="header-actions">
            <button className="button secondary" onClick={() => setDismissedStaleId(bestSelected.id)}>Keep Current Resume</button>
            <button className="button primary" disabled={bestGenerating} onClick={() => void generateBestResume()}>Regenerate Best Resume</button>
          </div>
        </div>}
        {bestSelected && <label className="resume-target-picker">Version<select value={bestSelectedId ?? ""} onChange={(event) => { setBestSelectedId(Number(event.target.value)); setDismissedStaleId(null); setShowBestLatex(false); setShowBestContent(false); }}>
          {bestHistory.map((version) => <option key={version.id} value={version.id}>v{version.version} · {formatDate(version.created_at)} · {version.status}</option>)}
        </select></label>}
        {(bestSelected?.status === "failed" || bestSelected?.status === "failed_retryable") && <div className="notice" role="alert">{bestSelected.generation_error || "This version failed. Retry Best Resume to continue."}</div>}
        {bestSelected?.status === "compiled" && <>
          <div className="header-actions">
            {bestSelected.pdf_url && <a className="button primary" href={backendAssetUrl(bestSelected.pdf_url)} download><Download size={16} /> Download PDF</a>}
            <button className="button secondary" onClick={() => setShowBestLatex((value) => !value)}><FileCode2 size={16} /> {showBestLatex ? "Hide LaTeX" : "View LaTeX"}</button>
            <button className="button secondary" onClick={() => setShowBestContent((value) => !value)}><FileText size={16} /> {showBestContent ? "Hide Selected Content" : "View Selected Content"}</button>
          </div>
          <p className="studio-note">Best Resume v{bestSelected.version}{bestProjectNames ? ` · ${bestProjectNames}` : ""}</p>
          {showBestLatex && <pre className="resume-latex-source">{bestSelected.latex_source}</pre>}
          {showBestContent && <BestResumeSelectedContent resume={bestSelected} />}
          {bestSelected.pdf_url && <iframe className="resume-pdf" title={`Best Resume version ${bestSelected.version}`} src={backendAssetUrl(bestSelected.pdf_url)} />}
        </>}
      </>}
    </section>

    <div className="studio-profile-grid" aria-label="Resume profiles">
      {profiles.map((profile) => <button key={profile.id} type="button" className={`studio-profile-card ${profileId === profile.id ? "selected" : ""}`} aria-pressed={profileId === profile.id} disabled={generating} onClick={() => setProfileId(profile.id)}><FileText size={20} /><strong>{profile.label}</strong><small>{profile.description}</small></button>)}
    </div>
    {message && <div className="notice" role="status">{message} {!loading && !analysis && <><Link href="/profile">Review Profile</Link> · <button className="button secondary" onClick={() => setRevision((value) => value + 1)}>Retry</button></>}</div>}
    {loading && <section className="resume-card" role="status"><p>Evaluating your project evidence…</p></section>}

    {analysis && <>
      <section className="resume-card">
        <div className="section-heading"><div><p className="eyebrow">{profileId === "general" ? "Overall strongest CV" : "Profile-specific recommendation"}</p><h2>{analysis.label}</h2></div><button className="button primary" disabled={!analysis.can_generate || generating} onClick={() => void generate()}><Sparkles size={16} /> {generating ? "Generating one CV…" : "Generate CV"}</button></div>
        <p>{analysis.description}</p>
        <div className="studio-summary"><strong>{analysis.headline}</strong><h3>Professional summary</h3><p>{analysis.summary}</p></div>
        <div className="resume-chips">{analysis.selected_skills.map((skill) => <span key={skill}>{skill}</span>)}</div>
        <p className="studio-note">{analysis.notice} CVs are generated one at a time, locally, without sending your profile to an AI provider.</p>
      </section>

      <section className="resume-card">
        <div className="section-heading"><div><p className="eyebrow">Evidence, not keyword count</p><h2>Projects selected for this CV</h2></div></div>
        <p>The portfolio balances relevance, depth, scope, integration, ownership, outcomes and differentiation. Short classroom exercises receive a penalty; repeated capabilities add less value.</p>
        <div className="studio-project-list">{analysis.projects.filter((item) => item.selected).map((item) => <article key={item.name}>
          <div className="kospie-status-row"><h3>{item.name}</h3><span>{item.score}/100 · Portfolio value</span></div>
          <p className="studio-note">{item.project_type.replaceAll("_", " ")} · {item.domains.join(" · ")}</p>
          <dl className="studio-dimensions">{Object.entries(analysis.weights).map(([key, weight]) => <div key={key}><dt>{dimensionLabels[key]} · {Math.round(weight * 100)}%</dt><dd>{item.components[key]}/100</dd></div>)}</dl>
          <ul>{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </article>)}</div>
        <details className="studio-alternatives"><summary>Alternatives and why they were not selected</summary>{analysis.projects.filter((item) => !item.selected).map((item) => <article key={item.name}><h3>{item.name} · {item.score}/100</h3><ul>{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}</details>
      </section>

      <section className="resume-card">
        <div className="section-heading"><div><p className="eyebrow">Immutable versions · This profile only</p><h2>Your generated CVs</h2></div></div>
        {!history.length && <p>Generate this profile to preview and download its CV. Changing a profile never overwrites an existing version.</p>}
        {history.length > 0 && <label className="resume-target-picker">Version<select value={selectedId ?? ""} onChange={(event) => setSelectedId(Number(event.target.value))}><option value="" disabled>Select a version</option>{history.map((version) => <option key={version.id} value={version.id}>v{version.version} · {formatDate(version.created_at)} · {version.status}</option>)}</select></label>}
        {selected && <>
          <p>Current recommendations use your latest profile. This PDF preserves the facts and project selection used when it was generated.</p>
          {selected.status === "failed" && <div className="notice" role="alert">{selected.generation_error || "This version failed. Generate a new version to retry."}</div>}
          {selected.status === "compiled" && selected.pdf_url && <>
            <div className="header-actions"><a className="button primary" href={backendAssetUrl(selected.pdf_url)} download><Download size={16} /> Download PDF</a><a className="button secondary" href={backendAssetUrl(selected.tex_url)} download><FileCode2 size={16} /> Download LaTeX</a></div>
            <p className="studio-note">Included projects: {(selected.tailored_content_json.projects as Array<{ name: string }> | undefined)?.map((project) => project.name).join(" · ")}</p>
            <iframe className="resume-pdf" title={`${analysis.label} CV version ${selected.version}`} src={backendAssetUrl(selected.pdf_url)} />
          </>}
        </>}
      </section>
    </>}
  </>;
}

function BestResumeSelectedContent({ resume }: { resume: GeneratedResume }) {
  const content = resume.tailored_content_json as Record<string, unknown>;
  const plan = (resume.company_profile?.best_resume_plan ?? {}) as Record<string, unknown>;
  const projects = Array.isArray(content.projects) ? content.projects as Array<{ name?: string; bullets?: string[]; technologies?: string[] }> : [];
  const experience = Array.isArray(content.experience) ? content.experience as Array<{ title?: string; organization?: string; bullets?: string[] }> : [];
  const certifications = Array.isArray(content.certifications) ? content.certifications as Array<{ name?: string; issuer?: string }> : [];
  const coursework = Array.isArray(content.coursework) ? content.coursework as Array<{ name?: string; institution?: string }> : [];
  const skills = Array.isArray(content.selected_skills) ? content.selected_skills as string[] : [];
  const excluded = Array.isArray(plan.excluded_projects) ? plan.excluded_projects as Array<{ name?: string; reason?: string }> : [];
  return <section className="resume-card" aria-label="Selected Best Resume evidence">
    <h3>Selected content</h3>
    {experience.length > 0 && <><h4>Experience</h4>{experience.map((item) => <article key={`${item.title}-${item.organization}`}><strong>{item.title} · {item.organization}</strong><ul>{(item.bullets ?? []).map((bullet) => <li key={bullet}>{bullet}</li>)}</ul></article>)}</>}
    <h4>Projects</h4>{projects.map((item) => <article key={item.name}><strong>{item.name}</strong><p>{(item.technologies ?? []).join(" · ")}</p><ul>{(item.bullets ?? []).map((bullet) => <li key={bullet}>{bullet}</li>)}</ul></article>)}
    <h4>Evidence-backed skills</h4><p>{skills.join(" · ") || "None selected"}</p>
    {certifications.length > 0 && <><h4>Verified certifications</h4><p>{certifications.map((item) => `${item.name}${item.issuer ? ` — ${item.issuer}` : ""}`).join(" · ")}</p></>}
    {coursework.length > 0 && <><h4>Coursework</h4><p>{coursework.map((item) => `${item.name}${item.institution ? ` — ${item.institution}` : ""}`).join(" · ")}</p></>}
    {excluded.length > 0 && <details><summary>Projects not selected and why</summary>{excluded.map((item) => <p key={item.name}>{item.name}: {item.reason}</p>)}</details>}
  </section>;
}
