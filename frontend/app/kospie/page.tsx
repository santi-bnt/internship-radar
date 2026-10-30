"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, BookOpen, Check, Download, ExternalLink, FileCode2,
  FileText, GraduationCap, RefreshCw, Sparkles, TriangleAlert,
} from "lucide-react";

import { api, backendAssetUrl, formatDate } from "@/lib/api";
import type {
  GeneratedResume, KospieAnalysis, KospieProfile, KospieResumeContent,
} from "@/lib/types";

const interests = ["Robotics", "Embedded Systems", "Control", "Automation", "Computer Vision", "Digital Systems"];
type Tab = "pdf" | "skills" | "projects" | "coursework" | "languages" | "eligibility" | "why" | "changes" | "keywords" | "latex";

export default function KospiePage() {
  const [profile, setProfile] = useState<KospieProfile | null>(null);
  const [analysis, setAnalysis] = useState<KospieAnalysis | null>(null);
  const [resumes, setResumes] = useState<GeneratedResume[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("pdf");
  const [busy, setBusy] = useState<"analyze" | "generate" | "">("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [configuration, history] = await Promise.all([
          api<KospieProfile>("/api/kospie/profile"),
          api<GeneratedResume[]>("/api/kospie/resumes"),
        ]);
        setProfile(configuration);
        setResumes(history);
        setSelectedId(history.find((item) => item.status === "compiled")?.id ?? null);
        setAnalysis(await api<KospieAnalysis>("/api/kospie/analyze", { method: "POST" }));
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not load the KOSPIE workspace.");
      }
    }
    void load();
  }, []);

  const selected = useMemo(
    () => resumes.find((item) => item.id === selectedId) ?? null,
    [resumes, selectedId],
  );
  const content = (selected?.tailored_content_json ?? {}) as KospieResumeContent;
  const pdfUrl = selected?.pdf_url ? backendAssetUrl(selected.pdf_url) : null;
  const texUrl = selected ? backendAssetUrl(selected.tex_url) : null;
  const currentEnglishVerified = analysis?.language_status.some(
    (item) => item.language === "English" && item.status === "VERIFIED",
  ) ?? false;
  const selectedEnglishVerified = (content.language_verification ?? []).some(
    (item) => item.language === "English" && item.status === "VERIFIED",
  );
  const selectedUsesOlderLanguageEvidence = Boolean(
    selected && currentEnglishVerified && !selectedEnglishVerified,
  );

  async function saveConfiguration(): Promise<KospieProfile> {
    if (!profile) throw new Error("KOSPIE configuration is not loaded.");
    const saved = await api<KospieProfile>("/api/kospie/profile", {
      method: "PUT",
      body: JSON.stringify({
        selected_universities_json: profile.selected_universities_json,
        primary_interests_json: profile.primary_interests_json,
      }),
    });
    setProfile(saved);
    return saved;
  }

  async function analyze() {
    setBusy("analyze");
    setMessage("");
    try {
      await saveConfiguration();
      setAnalysis(await api<KospieAnalysis>("/api/kospie/analyze", { method: "POST" }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "KOSPIE analysis failed.");
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    setBusy("generate");
    setMessage("");
    try {
      await saveConfiguration();
      const freshAnalysis = await api<KospieAnalysis>("/api/kospie/analyze", { method: "POST" });
      setAnalysis(freshAnalysis);
      const resume = await api<GeneratedResume>("/api/kospie/resumes", { method: "POST" });
      setResumes((current) => [resume, ...current]);
      setSelectedId(resume.id);
      setTab("pdf");
      setMessage("KOSPIE CV generated from verified profile evidence.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "KOSPIE CV generation failed.");
    } finally {
      setBusy("");
    }
  }

  function updateUniversity(index: number, value: string) {
    if (!profile) return;
    const universities = [...profile.selected_universities_json] as [string, string, string];
    universities[index] = value;
    setProfile({ ...profile, selected_universities_json: universities });
    setAnalysis(null);
  }

  function toggleInterest(interest: string) {
    if (!profile) return;
    const values = profile.primary_interests_json.includes(interest)
      ? profile.primary_interests_json.filter((item) => item !== interest)
      : [...profile.primary_interests_json, interest];
    setProfile({ ...profile, primary_interests_json: values });
    setAnalysis(null);
  }

  if (!profile) {
    return <section className="resume-card resume-loading"><div className="resume-skeleton" />{message && <p>{message}</p>}</section>;
  }

  return <>
    <header className="page-header">
      <div>
        <p className="eyebrow">Resume · New Resume Target</p>
        <h1>KOSPIE / Germany Engineering</h1>
        <p className="page-subtitle">Academic-technical CV for KOSPIE 2027-2028 · DAAD + Tecnológico de Monterrey</p>
      </div>
      <button className="button primary" disabled={!!busy} onClick={() => void generate()}>
        <FileText size={16} /> {busy === "generate" ? "Generating 1-2 page CV…" : resumes.length ? "Generate New Version" : "Generate KOSPIE CV"}
      </button>
    </header>

    {message && <div className="notice" role="status">{message}</div>}

    <section className="content-section kospie-context">
      <div className="section-heading compact">
        <div><p className="eyebrow">Program context</p><h2>Selected German Universities</h2></div>
        <span className="priority-summary">Exactly 3 required</span>
      </div>
      <p>University context changes relevance ranking only. It never creates candidate skills or facts.</p>
      <div className="settings-fields kospie-universities">
        {profile.selected_universities_json.map((university, index) => (
          <label key={index}>University {index + 1}
            <input value={university} onChange={(event) => updateUniversity(index, event.target.value)} />
          </label>
        ))}
      </div>
      <h3>Primary Engineering Interests</h3>
      <div className="kospie-interest-grid">
        {interests.map((interest) => <label key={interest} className="talent-area-option">
          <input type="checkbox" checked={profile.primary_interests_json.includes(interest)} onChange={() => toggleInterest(interest)} />
          <span>{interest}</span>
        </label>)}
      </div>
      <div className="header-actions">
        <button className="button secondary" disabled={!!busy} onClick={() => void analyze()}>
          <Sparkles size={16} /> {busy === "analyze" ? "Analyzing verified profile…" : "Analyze Profile"}
        </button>
      </div>
    </section>

    {analysis && <section className="resume-card">
      <div className="resume-header"><div><p className="eyebrow">Pre-generation review</p><h2>KOSPIE Profile Analysis</h2><p>Candidate facts are separate from program requirements.</p></div></div>
      <div className="kospie-analysis-grid">
        <AnalysisList title="Academic Strengths" icon={<GraduationCap size={18} />} items={analysis.academic_strengths} />
        <AnalysisList title="Technical Strengths" icon={<BadgeCheck size={18} />} items={analysis.technical_strengths} chips />
        <div className="kospie-analysis-panel"><h3><FileText size={18} /> KOSPIE Project Ranking</h3>{analysis.recommended_projects.map((item) => <article key={item.name}><div className="kospie-status-row"><strong>{item.rank}. {item.name}</strong><span>{item.selected ? "SELECTED" : "NOT SELECTED"} · {item.match}%</span></div><p>{item.domains.join(" · ") || "General engineering"} · {item.project_type.replaceAll("_", " ")}</p><ul className="kospie-project-reasons">{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}</div>
        <div className="kospie-analysis-panel"><h3><BookOpen size={18} /> Recommended Coursework</h3><strong>Strong</strong><ul>{analysis.recommended_coursework.strong.map((item) => <li key={item.name}>{item.name}</li>)}</ul><strong>Relevant</strong><ul>{analysis.recommended_coursework.relevant.map((item) => <li key={item.name}>{item.name}</li>)}</ul></div>
        <StatusPanel title="Language Status" items={analysis.language_status} />
        <StatusPanel title="KOSPIE Eligibility Checklist" items={analysis.eligibility} />
      </div>
    </section>}

    {selected && <section className="resume-card">
      <div className="resume-header">
        <div><p className="eyebrow">Generated KOSPIE CV</p><h2>{selected.target_role}</h2><p>Version {selected.version} · {formatDate(selected.created_at)} · natural 1-2 page target</p></div>
        <div className="resume-score"><strong>{Math.round(selected.match_score)}</strong><span>Engineering fit</span></div>
        <div className="resume-actions"><button className="button secondary" disabled={!!busy} onClick={() => void generate()}><RefreshCw size={15} /> New Version</button>{pdfUrl && <a className="button primary" href={pdfUrl} download><Download size={15} /> Download PDF</a>}</div>
      </div>
      {selectedUsesOlderLanguageEvidence && <div className="notice"><strong>This immutable version predates your current verified IELTS evidence.</strong> Generate a new version to include IELTS Academic 6.5 in the CV and eligibility snapshot.</div>}
      {selected.warnings_json.length > 0 && <div className="resume-warning"><TriangleAlert size={18} /><div><strong>Eligibility item to complete</strong><ul>{selected.warnings_json.map((warning) => <li key={warning}>{warning}</li>)}</ul></div></div>}
      <div className="resume-tabs" role="tablist">
        {([[
          "pdf", "PDF Preview"], ["skills", "Selected Skills"], ["projects", "Selected Projects"],
          ["coursework", "Selected Coursework"], ["languages", "Language Verification"],
          ["eligibility", "KOSPIE Eligibility"], ["why", "Why this version?"],
          ["changes", "Changes"], ["keywords", "Keywords"], ["latex", "LaTeX"],
        ] as Array<[Tab, string]>).map(([key, label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}
      </div>
      <div className="resume-tab-panel">
        {tab === "pdf" && pdfUrl && <><div className="resume-preview-actions"><a href={pdfUrl} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open in new tab</a></div><iframe title="KOSPIE CV PDF" src={pdfUrl} className="resume-pdf" /></>}
        {tab === "skills" && <div className="resume-skill-match-list"><div className="resume-skill-verification"><Check size={17} /> All displayed skills were checked against verified profile evidence.</div>{selected.job_skill_matches.map((item) => <article key={item.skill}><div><h3>{item.skill}</h3><span>{item.category}</span></div><p>{item.reason}</p><small>{item.evidence.join(" · ")}</small></article>)}</div>}
        {tab === "projects" && <SimpleCards items={(content.projects ?? []).map((item) => ({ title: item.name, text: item.technologies.join(", "), detail: `Engineering relevance ${Math.round(item.relevance_score)}%` }))} />}
        {tab === "coursework" && <SimpleCards items={(content.coursework ?? []).map((item) => ({ title: item.name, text: item.institution || "Verified profile coursework" }))} empty="No verified coursework is stored for this profile." />}
        {tab === "languages" && <StatusPanel title="Verified candidate language evidence" items={content.language_verification ?? []} />}
        {tab === "eligibility" && <StatusPanel title="Program requirements (not CV claims)" items={content.program_eligibility ?? []} />}
        {tab === "why" && <ul className="kospie-why-list">{(content.why_this_version ?? []).map((item) => <li key={item}>{item}</li>)}</ul>}
        {tab === "changes" && <SimpleCards items={selected.changes_json.map((item) => ({ title: item.section, text: item.description, detail: item.reason }))} />}
        {tab === "keywords" && <div className="resume-keyword-groups">{Object.entries(selected.keywords_json).map(([group, words]) => <div key={group}><h3>{group.replaceAll("_", " ")}</h3><div className="resume-chips">{(words ?? []).map((word) => <span key={word}>{word}</span>)}</div></div>)}</div>}
        {tab === "latex" && texUrl && <div><div className="resume-code-actions"><a className="button secondary" href={texUrl} download><FileCode2 size={15} /> Download .tex</a></div><pre className="resume-code"><code>{selected.latex_source}</code></pre></div>}
      </div>
    </section>}

    <section className="side-panel verification-panel kospie-history">
      <div className="panel-title"><FileText size={18} /><h2>Immutable Resume Versions</h2></div>
      <div className="talent-version-list">{resumes.length ? resumes.map((item) => <label key={item.id} className={selectedId === item.id ? "active" : ""}><input type="radio" checked={selectedId === item.id} disabled={item.status !== "compiled"} onChange={() => setSelectedId(item.id)} /><span><strong>Version {item.version}</strong><small>{formatDate(item.created_at)} · {item.status}</small></span></label>) : <p>No KOSPIE CV exists yet.</p>}</div>
    </section>
  </>;
}

function AnalysisList({ title, icon, items, chips = false }: { title: string; icon: React.ReactNode; items: string[]; chips?: boolean }) {
  return <div className="kospie-analysis-panel"><h3>{icon} {title}</h3>{chips ? <div className="resume-chips">{items.map((item) => <span key={item}>{item}</span>)}</div> : <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>}</div>;
}

function StatusPanel({ title, items }: { title: string; items: Array<Record<string, string>> }) {
  return <div className="kospie-analysis-panel"><h3><BadgeCheck size={18} /> {title}</h3>{items.map((item, index) => <article key={`${item.requirement ?? item.language}-${index}`}><div className="kospie-status-row"><strong>{item.language ?? item.requirement}</strong><span>{[item.status, item.language ? item.requirement : ""].filter(Boolean).join(" · ")}</span></div><p>{item.evidence ?? [item.exam, item.score].filter(Boolean).join(" · ")}</p>{item.minimum && <small>Minimum: {item.minimum}</small>}{item.action_required && <small>{item.action_required}</small>}</article>)}</div>;
}

function SimpleCards({ items, empty = "No items selected." }: { items: Array<{ title: string; text: string; detail?: string }>; empty?: string }) {
  return <div className="resume-change-list">{items.length ? items.map((item) => <article key={item.title}><h3>{item.title}</h3><p>{item.text}</p>{item.detail && <small>{item.detail}</small>}</article>) : <p>{empty}</p>}</div>;
}
