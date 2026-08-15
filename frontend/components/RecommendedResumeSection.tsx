"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Clipboard, Download, ExternalLink, FileCode2, FileText, RefreshCw, Sparkles } from "lucide-react";

import { api, backendAssetUrl, formatDate } from "@/lib/api";
import type { GeneratedResume, Job } from "@/lib/types";

type Tab = "pdf" | "skills" | "changes" | "keywords" | "latex";

export default function RecommendedResumeSection({ job }: { job: Job }) {
  const canGenerate = job.status === "active" || job.status === "saved";
  const [resume, setResume] = useState<GeneratedResume | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("pdf");
  const [copied, setCopied] = useState(false);
  const [step, setStep] = useState("Analyzing job requirements...");

  useEffect(() => {
    api<GeneratedResume>(`/api/jobs/${job.id}/resume/latest`)
      .then(setResume)
      .catch(() => setResume(null))
      .finally(() => setLoading(false));
  }, [job.id]);

  useEffect(() => {
    if (!generating) return;
    setStep("Analyzing job requirements...");
    const first = window.setTimeout(() => setStep("Selecting relevant experience..."), 1800);
    const second = window.setTimeout(() => setStep("Generating and compiling resume..."), 3800);
    return () => { window.clearTimeout(first); window.clearTimeout(second); };
  }, [generating]);

  async function generate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError("");
    try {
      setResume(await api<GeneratedResume>(`/api/jobs/${job.id}/resume/generate`, { method: "POST" }));
      setTab("pdf");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Resume generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function copyLatex() {
    await navigator.clipboard.writeText(resume?.latex_source ?? "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  if (loading) return <section className="resume-card resume-loading"><div className="resume-skeleton" /></section>;

  if (!resume || generating) {
    return (
      <section className="resume-card">
        <div className="resume-empty-icon"><Sparkles size={24} /></div>
        <h2>Recommended Resume</h2>
        <p>{generating ? step : "Generate a tailored resume using the job description and your verified profile."}</p>
        {!canGenerate ? (
          <div className="notice">Resume generation is unavailable for {job.status.replaceAll("_", " ")} jobs.</div>
        ) : generating ? <div className="resume-spinner" aria-label="Generating resume" /> : (
          <button className="button primary" onClick={() => void generate()}>
            <FileText size={16} /> Generate Resume
          </button>
        )}
        <small>Only verified information from your profile will be used.</small>
        {error && <div className="resume-error" role="alert">{error}<button className="button secondary" onClick={() => void generate()}>Try Again</button></div>}
      </section>
    );
  }

  const pdfUrl = resume.pdf_url ? backendAssetUrl(resume.pdf_url) : null;
  const texUrl = backendAssetUrl(resume.tex_url);
  return (
    <section className="resume-card">
      <div className="resume-header">
        <div>
          <p className="eyebrow">Recommended Resume</p>
          <h2>{resume.target_role}</h2>
          <p>Generated {formatDate(resume.created_at)} · Version {resume.version}</p>
        </div>
        <div className="resume-score"><strong>{Math.round(resume.match_score)}</strong><span>Match</span></div>
        <div className="resume-actions">
          <button className="button secondary" onClick={() => void generate()} disabled={generating || !canGenerate}><RefreshCw size={15} /> Regenerate</button>
          {pdfUrl && <a className="button primary" href={pdfUrl} download><Download size={15} /> Download PDF</a>}
        </div>
      </div>
      {error && <div className="resume-error" role="alert">{error}</div>}
      {resume.warnings_json.length > 0 && (
        <div className="resume-warning"><AlertTriangle size={18} /><div><strong>Requirements to review</strong><ul>{resume.warnings_json.map((warning) => <li key={warning}>{warning}</li>)}</ul></div></div>
      )}
      <div className="resume-tabs" role="tablist">
        {([["pdf", "PDF Preview"], ["skills", "Selected Skills"], ["changes", "Changes"], ["keywords", "Keywords"], ["latex", "LaTeX Code"]] as const).map(([key, label]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)} role="tab">{label}</button>
        ))}
      </div>
      <div className="resume-tab-panel">
        {tab === "pdf" && pdfUrl && <><div className="resume-preview-actions"><a href={pdfUrl} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open in new tab</a></div><iframe title="Recommended resume PDF" src={pdfUrl} className="resume-pdf" /></>}
        {tab === "skills" && (
          <div className="resume-skill-match-list">
            <div className="resume-skill-verification">
              <Check size={17} /> All displayed skills were checked against {resume.skill_verification.registry_size} verified skills.
            </div>
            {resume.job_skill_matches.map((match) => (
              <article key={match.skill}>
                <div><h3>{match.skill}</h3><span>{match.category}</span></div>
                <p>{match.reason}</p>
                <small>{match.evidence.join(" · ")}</small>
              </article>
            ))}
          </div>
        )}
        {tab === "changes" && <div className="resume-change-list">{resume.changes_json.length ? resume.changes_json.map((change, index) => <article key={`${change.section}-${index}`}><h3>{change.section}</h3><p>{change.description}</p><small>{change.reason}</small></article>) : <p>No material changes were reported.</p>}</div>}
        {tab === "keywords" && <div className="resume-keyword-groups">{Object.entries(resume.keywords_json).map(([group, words]) => <div key={group}><h3>{group.replaceAll("_", " ")}</h3><div className="resume-chips">{(words ?? []).map((word) => <span key={word}>{word}</span>)}</div></div>)}</div>}
        {tab === "latex" && <div><div className="resume-code-actions"><button className="button secondary" onClick={() => void copyLatex()}>{copied ? <Check size={15} /> : <Clipboard size={15} />}{copied ? "Copied" : "Copy Code"}</button><a className="button secondary" href={texUrl} download><FileCode2 size={15} /> Download .tex</a></div><p className="resume-filename">{job.company}_{job.title}_Resume.tex</p><pre className="resume-code"><code>{resume.latex_source}</code></pre></div>}
      </div>
    </section>
  );
}
