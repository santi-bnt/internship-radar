"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Clipboard, Download, ExternalLink, FileCode2, FileText, RefreshCw, Sparkles } from "lucide-react";

import { ApiError, api, backendAssetUrl, formatDate } from "@/lib/api";
import type { GeneratedResume, Job, ResearchOpportunityAnalysis } from "@/lib/types";

type Tab = "pdf" | "skills" | "changes" | "keywords" | "latex";
type ResumeTarget = "recommended" | "software_engineering" | "embedded_firmware" | "electrical_validation" | "hardware_engineering" | "robotics_research" | "kospie_germany";

export default function RecommendedResumeSection({ job }: { job: Job }) {
  const activeJobId = useRef(job.id);
  activeJobId.current = job.id;
  const canGenerate = job.status === "active" || job.status === "saved";
  const [resume, setResume] = useState<GeneratedResume | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("pdf");
  const [copied, setCopied] = useState(false);
  const [step, setStep] = useState("Analyzing job requirements...");
  const [resumeTarget, setResumeTarget] = useState<ResumeTarget>(
    job.opportunity_type === "research" ? "robotics_research" : "recommended",
  );
  const [analysis, setAnalysis] = useState<ResearchOpportunityAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  async function analyzeResearch() {
    setAnalyzing(true);
    setError("");
    try {
      setAnalysis(await api<ResearchOpportunityAnalysis>(`/api/research-opportunities/${job.id}/analyze`, { method: "POST" }));
      setResumeTarget("robotics_research");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Research opportunity analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  const researchAnalysisPanel = job.opportunity_type === "research" && (
    <div className="research-analysis">
      <div className="resume-actions">
        <button className="button secondary" onClick={() => void analyzeResearch()} disabled={analyzing}>
          <Sparkles size={15} /> {analyzing ? "Analyzing..." : "Analyze Opportunity"}
        </button>
      </div>
      {analysis && <>
        <div><h3>Detected research focus</h3><div className="resume-chips">{analysis.research_focus.map((item) => <span key={item}>{item}</span>)}</div></div>
        <div><h3>Strong profile matches</h3><div className="resume-chips">{analysis.recommended_skills.strong_match.map((item) => <span key={item}>{item}</span>)}</div></div>
        <div><h3>Missing / not verified</h3><p className="page-subtitle">Mentioned by the opportunity; these will not be added to your resume.</p><div className="resume-chips warning-chips">{analysis.unverified_keywords.length ? analysis.unverified_keywords.map((item) => <span key={item}>{item}</span>) : <span>None detected</span>}</div></div>
        <div><h3>Recommended projects</h3><div className="resume-change-list">{analysis.recommended_projects.map((project, index) => <article key={project.name}><h3>{index + 1}. {project.name} · Match {project.match}%</h3><p>{project.why}</p></article>)}</div></div>
        <div><h3>Recommended skills</h3><p><strong>Strong Match:</strong> {analysis.recommended_skills.strong_match.join(", ") || "None"}</p><p><strong>Relevant:</strong> {analysis.recommended_skills.relevant.join(", ") || "None"}</p><p><strong>Not Selected:</strong> {analysis.recommended_skills.not_selected.join(", ") || "None"}</p></div>
        <div className="notice"><strong>Similarity: {analysis.similarity}%.</strong> {analysis.reuse_message}</div>
      </>}
    </div>
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setGenerating(false);
    setResume(null);
    setError("");
    setAnalysis(null);
    setTab("pdf");
    setResumeTarget(job.opportunity_type === "research" ? "robotics_research" : "recommended");

    api<GeneratedResume>(`/api/jobs/${job.id}/resume/latest`, { signal: controller.signal })
      .then((latest) => {
        if (!controller.signal.aborted && latest.job_id === job.id) setResume(latest);
      })
      .catch(() => {
        if (!controller.signal.aborted) setResume(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [job.id, job.opportunity_type]);

  useEffect(() => {
    if (!generating) return;
    setStep("Analyzing job requirements...");
    const first = window.setTimeout(() => setStep("Selecting relevant experience..."), 1800);
    const second = window.setTimeout(() => setStep("Generating and compiling resume..."), 3800);
    return () => { window.clearTimeout(first); window.clearTimeout(second); };
  }, [generating]);

  async function generate(regenerate = false) {
    if (!canGenerate) return;
    if (resumeTarget === "kospie_germany") {
      window.location.assign("/kospie");
      return;
    }
    const generationJobId = job.id;
    setGenerating(true);
    setError("");
    try {
      const generated = await api<GeneratedResume>(`/api/jobs/${generationJobId}/resume/generate`, {
        method: "POST",
        body: JSON.stringify({ resume_target: resumeTarget, regenerate }),
      });
      if (activeJobId.current !== generationJobId || generated.job_id !== generationJobId) return;
      setResume(generated);
      setTab("pdf");
    } catch (caught) {
      if (activeJobId.current === generationJobId) {
        if (caught instanceof ApiError && caught.status === 503) {
          setError("Resume service is temporarily busy. Your existing resumes remain available; try again shortly.");
        } else {
          setError(caught instanceof Error ? caught.message : "Resume generation failed.");
        }
      }
    } finally {
      if (activeJobId.current === generationJobId) setGenerating(false);
    }
  }

  useEffect(() => {
    if (!resume || !["queued", "generating"].includes(resume.status)) return;
    const timer = window.setInterval(() => {
      void api<GeneratedResume[]>(`/api/jobs/${job.id}/resumes`).then((versions) => {
        const fresh = versions.find((item) => item.id === resume.id);
        if (fresh) setResume(fresh);
      }).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job.id, resume]);

  async function copyLatex() {
    await navigator.clipboard.writeText(resume?.latex_source ?? "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  // Never render a previous job's resume during the render before the
  // job-change effect has had a chance to clear the old state.
  if (loading || (resume && resume.job_id !== job.id)) {
    return <section className="resume-card resume-loading"><div className="resume-skeleton" /></section>;
  }

  if (!resume || generating || resume.status !== "compiled") {
    return (
      <section className="resume-card">
        <label className="resume-target-picker">
          Resume Target
          <select value={resumeTarget} onChange={(event) => setResumeTarget(event.target.value as ResumeTarget)}>
            <option value="recommended">Recommended for opportunity</option>
            <option value="software_engineering">Software Engineering</option>
            <option value="embedded_firmware">Embedded / Firmware</option>
            <option value="electrical_validation">Electrical Validation</option>
            <option value="hardware_engineering">Hardware / Systems Integration</option>
            <option value="robotics_research">Robotics Research</option>
            <option value="kospie_germany">KOSPIE / Germany Engineering</option>
          </select>
        </label>
        {resumeTarget === "robotics_research" && (
          <p className="notice">Optimizes projects, skills, and wording for university laboratories, visiting research internships, and robotics research opportunities.</p>
        )}
        {resumeTarget === "kospie_germany" && (
          <p className="notice">KOSPIE uses a dedicated academic workflow with exactly three selected German universities and a separate eligibility checklist.</p>
        )}
        {researchAnalysisPanel}
        <div className="resume-empty-icon"><Sparkles size={24} /></div>
        <h2>Recommended Resume</h2>
        <p>{resume?.status === "queued" ? "Resume generation queued. It will start as soon as capacity is available." : resume?.status === "generating" || generating ? step : "Generate a tailored resume using the job description and your verified profile."}</p>
        {!canGenerate ? (
          <div className="notice">Resume generation is unavailable for {job.status.replaceAll("_", " ")} jobs.</div>
        ) : generating || resume?.status === "queued" || resume?.status === "generating" ? <div className="resume-spinner" aria-label="Generating resume" /> : (
          <button className="button primary" onClick={() => void generate()}>
            <FileText size={16} /> {resumeTarget === "kospie_germany" ? "Open KOSPIE Workspace" : "Generate Resume"}
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
      <label className="resume-target-picker">
        Resume Target
        <select value={resumeTarget} onChange={(event) => setResumeTarget(event.target.value as ResumeTarget)}>
          <option value="recommended">Recommended for opportunity</option>
          <option value="software_engineering">Software Engineering</option>
          <option value="embedded_firmware">Embedded / Firmware</option>
          <option value="electrical_validation">Electrical Validation</option>
          <option value="hardware_engineering">Hardware / Systems Integration</option>
          <option value="robotics_research">Robotics Research</option>
          <option value="kospie_germany">KOSPIE / Germany Engineering</option>
        </select>
      </label>
      {resumeTarget === "robotics_research" && <p className="notice">Academic-audience ranking uses only verified profile evidence.</p>}
      {resumeTarget === "kospie_germany" && <p className="notice">Use Regenerate to open the KOSPIE workspace and configure its three university targets.</p>}
      {researchAnalysisPanel}
      <div className="resume-header">
        <div>
          <p className="eyebrow">Recommended Resume</p>
          <h2>{resume.target_role}</h2>
          <p>Generated {formatDate(resume.created_at)} · Version {resume.version}</p>
        </div>
        <div className="resume-score"><strong>{Math.round(resume.match_score)}</strong><span>Match</span></div>
        <div className="resume-actions">
          <button className="button secondary" onClick={() => void generate(true)} disabled={generating || !canGenerate}><RefreshCw size={15} /> Regenerate Resume</button>
          {pdfUrl && <a className="button primary" href={pdfUrl} download><Download size={15} /> Download PDF</a>}
        </div>
      </div>
      {error && <div className="resume-error" role="alert">{error}</div>}
      {resume.is_stale && <div className="notice">Your profile or this job changed since this resume was generated. Regenerate when you are ready.</div>}
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
                <div><h3>{match.skill}</h3><span>{match.category}{match.match_kind ? ` · ${match.match_kind.replaceAll("_", " ").toLowerCase()}` : ""}</span></div>
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
