"use client";

import { ArrowLeft, BadgeCheck, Bot, BriefcaseBusiness, Building2, CalendarDays, Download, ExternalLink, FileText, Plus, RefreshCw, Save, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { connectInstalledExtension, detectInstalledExtension } from "@/components/ApplyAssistantButton";
import { api, backendAssetUrl, formatDate } from "@/lib/api";
import { extensionConnectionMessage } from "@/lib/apply-assistant";
import type { ApplicationSessionLaunch, GeneratedResume } from "@/lib/types";

type Company = {
  company_id: string; company_name: string; company_summary: string;
  technical_areas: string[]; common_role_categories: string[];
  preferred_project_categories: string[]; preferred_skill_categories: string[];
  source_url: string; last_verified_at: string | null;
  talent_community_url: string; talent_community_description: string;
};
type Preview = {
  strategy: string[]; headline: string;
  projects: { name: string; relevance_score: number }[];
  skills: string[];
  courses: { name: string; institution: string; issued: string }[];
};

function normalizePreview(value: Partial<Preview>): Preview {
  return {
    strategy: Array.isArray(value.strategy) ? value.strategy : [],
    headline: typeof value.headline === "string" ? value.headline : "",
    projects: Array.isArray(value.projects) ? value.projects : [],
    skills: Array.isArray(value.skills) ? value.skills : [],
    courses: Array.isArray(value.courses) ? value.courses : [],
  };
}

const defaultAreas = ["Robotics", "Embedded Systems", "Software Engineering", "Controls", "Autonomous Systems", "FPGA / Digital Systems"];
const blankCompany = (): Company => ({ company_id: "", company_name: "", company_summary: "", technical_areas: [], common_role_categories: defaultAreas, preferred_project_categories: [], preferred_skill_categories: [], source_url: "", last_verified_at: null, talent_community_url: "", talent_community_description: "" });

export default function TalentCommunitiesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [company, setCompany] = useState<Company | null>(null);
  const [areas, setAreas] = useState<string[]>(defaultAreas);
  const [extraArea, setExtraArea] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [versions, setVersions] = useState<GeneratedResume[]>([]);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState(false);

  async function loadVersions(item: Company) {
    const history = await api<GeneratedResume[]>(`/api/talent-communities/${item.company_id}/resumes`);
    setVersions(history);
    setResumeId(history.find(version => version.status === "compiled")?.id ?? null);
  }

  async function choose(item: Company) {
    setBusy("loading");
    setCompany({ ...item });
    setAreas(item.common_role_categories.length ? item.common_role_categories : defaultAreas);
    setPreview(null); setVersions([]); setResumeId(null); setMessage(""); setEditing(false);
    try { await loadVersions(item); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Could not load resume versions."); }
    finally { setBusy(""); }
  }

  useEffect(() => {
    setBusy("loading");
    api<Company[]>("/api/talent-communities")
      .then(async items => {
        setCompanies(items);
        const first = items[0];
        if (!first) return;
        setCompany({ ...first });
        setAreas(first.common_role_categories.length ? first.common_role_categories : defaultAreas);
        const history = await api<GeneratedResume[]>(`/api/talent-communities/${first.company_id}/resumes`);
        setVersions(history);
        setResumeId(history.find(version => version.status === "compiled")?.id ?? null);
      })
      .catch(caught => setMessage(caught instanceof Error ? caught.message : "Could not load Talent Communities."))
      .finally(() => setBusy(""));
  }, []);

  async function act(action: "preview" | "resumes") {
    if (!company) return;
    setBusy(action); setMessage("");
    try {
      const path = `/api/talent-communities/${company.company_id}/${action}`;
      const options = { method: "POST", body: JSON.stringify({ target_role_categories: areas }) };
      if (action === "preview") setPreview(normalizePreview(await api<Partial<Preview>>(path, options)));
      else {
        const resume = await api<GeneratedResume>(path, options);
        setVersions(current => [resume, ...current]); setResumeId(resume.id);
        setMessage("Company resume generated. Review the PDF before applying.");
      }
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "Resume preparation failed."); }
    finally { setBusy(""); }
  }

  async function saveCompany() {
    if (!company) return;
    setBusy("save"); setMessage("");
    try {
      const saved = await api<Company>(`/api/talent-communities/${company.company_id}`, { method: "PUT", body: JSON.stringify(company) });
      setCompanies(current => [...current.filter(item => item.company_id !== saved.company_id), saved]);
      setCompany(saved); setAreas(saved.common_role_categories.length ? saved.common_role_categories : defaultAreas);
      setPreview(null); setEditing(false); setMessage("Company profile saved for your account.");
      await loadVersions(saved);
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "Could not save company."); }
    finally { setBusy(""); }
  }

  async function apply() {
    if (!company || !resumeId) return;
    const portal = window.open("about:blank", "_blank");
    setBusy("assistant"); setMessage("");
    try {
      await detectInstalledExtension();
      const launch = await api<ApplicationSessionLaunch>(`/api/talent-communities/${company.company_id}/application-sessions`, { method: "POST", body: JSON.stringify({ resume_version_id: resumeId }) });
      await connectInstalledExtension(extensionConnectionMessage(launch, window.location.origin));
      if (portal) { portal.opener = null; portal.location.href = launch.session.application_url; }
      else window.open(launch.session.application_url, "_blank", "noopener,noreferrer");
      setMessage("Assistant connected. Review every field and submit manually on the company site.");
    } catch (caught) { portal?.close(); setMessage(caught instanceof Error ? caught.message : "Could not connect Apply Assistant."); }
    finally { setBusy(""); }
  }

  const selectedResume = versions.find(version => version.id === resumeId) ?? null;
  const pdfUrl = selectedResume?.pdf_url ? backendAssetUrl(selectedResume.pdf_url) : null;

  if (!company) return <>
    <header className="page-header"><div><p className="eyebrow">Future opportunities</p><h1>Talent Communities</h1><p>Prepare company resumes without a specific requisition.</p></div><button className="button secondary" disabled={!!busy} onClick={() => { setCompany(blankCompany()); setEditing(true); }}><Plus size={16} /> Add Company</button></header>
    {message && <div className="notice error" role="alert">{message}</div>}
    <section className="content-section talent-card"><div className="target-company-grid">{companies.map(item => <button className="talent-company-choice" key={item.company_id} onClick={() => void choose(item)}><Building2 size={20} /><span><strong>{item.company_name}</strong><small>Talent Community · No specific role</small></span></button>)}</div></section>
  </>;

  return <>
    <button className="back-link" onClick={() => { setCompany(null); setPreview(null); }}><ArrowLeft size={16} /> Back to Talent Communities</button>
    <header className="detail-header">
      <div><div className="detail-status"><span className="priority-pill"><Sparkles size={12} /> Talent Community</span><span>Company profile</span><span className="urgency-pill">FUTURE OPPORTUNITIES</span></div><h1>{company.company_name || "New Company"} Talent Community</h1><p className="detail-company">{company.company_name || "Configure company profile"}</p><div className="detail-meta"><span><BriefcaseBusiness size={15} />No specific role</span><span><ShieldCheck size={15} />Verified profile evidence only</span>{company.last_verified_at && <span><CalendarDays size={15} />Profile checked {formatDate(company.last_verified_at)}</span>}</div></div>
      <div className="header-actions"><button className="button secondary" disabled={!!busy} onClick={() => setEditing(true)}><RefreshCw size={16} /> Edit Profile</button>{company.source_url && <a className="button secondary" href={company.source_url} target="_blank" rel="noreferrer">Company Source <ExternalLink size={16} /></a>}{company.talent_community_url && <a className="button secondary" href={company.talent_community_url} target="_blank" rel="noreferrer">Open Community <ExternalLink size={16} /></a>}<button className="button primary" disabled={!!busy || !resumeId} onClick={() => void apply()}><Bot size={16} /> Apply with Assistant</button></div>
    </header>
    {message && <div className="notice success" role="status">{message}</div>}

    {editing ? <section className="form-section talent-editor">
      <div className="section-heading compact"><div><p className="eyebrow">Company targeting</p><h2>Edit Company Profile</h2></div></div>
      <div className="settings-fields">{([ ["company_id", "Company identifier"], ["company_name", "Company name"], ["company_summary", "Company technical focus"], ["talent_community_description", "Talent Community description"], ["talent_community_url", "Talent Community URL"], ["source_url", "Profile source URL"] ] as const).map(([key, label]) => <label key={key}>{label}<input value={company[key]} onChange={event => setCompany({ ...company, [key]: event.target.value })} /></label>)}{(["technical_areas", "common_role_categories", "preferred_project_categories", "preferred_skill_categories"] as const).map(key => <label key={key}>{key.replaceAll("_", " ")}<input value={company[key].join(", ")} onChange={event => setCompany({ ...company, [key]: event.target.value.split(",").map(value => value.trim()) })} /></label>)}</div>
      <div className="header-actions"><button className="button primary" disabled={!!busy} onClick={() => void saveCompany()}><Save size={16} /> Save Company Profile</button><button className="button secondary" onClick={() => setEditing(false)}>Cancel</button></div>
    </section> : <div className="detail-grid talent-detail-grid">
      <div className="detail-main">
        <section className="content-section prose-section"><h2>Company focus</h2><p>{company.company_summary}</p><h3>Talent Community</h3><p>{company.talent_community_description}</p><div className="resume-chips talent-focus-chips">{company.technical_areas.map(area => <span key={area}>{area}</span>)}</div></section>
        <section className="content-section prose-section"><div className="section-heading compact"><div><p className="eyebrow">Resume target</p><h2>Target Areas</h2></div></div><p>Choose the technical areas this company resume should emphasize.</p><div className="talent-area-grid">{Array.from(new Set([...defaultAreas, ...company.common_role_categories, ...areas])).map(area => <label className="talent-area-option" key={area}><input type="checkbox" disabled={!!busy} checked={areas.includes(area)} onChange={() => { setAreas(current => current.includes(area) ? current.filter(item => item !== area) : [...current, area]); setPreview(null); }} /><span>{area}</span></label>)}</div><div className="talent-extra-area"><input aria-label="Additional target area" placeholder="Additional target area" value={extraArea} onChange={event => setExtraArea(event.target.value)} /><button className="button secondary" disabled={!!busy || !extraArea.trim()} onClick={() => { setAreas(current => [...new Set([...current, extraArea.trim()])]); setExtraArea(""); setPreview(null); }}><Plus size={15} /> Add Area</button></div><button className="button primary" disabled={!!busy || !areas.length} onClick={() => void act("preview")}><Sparkles size={16} />{busy === "preview" ? "Preparing strategy…" : "Generate Company Resume"}</button></section>

        {preview && <section className="resume-card"><div className="resume-header"><div><p className="eyebrow">Company Resume Preview</p><h2>{company.company_name} Talent Community</h2><p>{preview.strategy.join(" + ")}</p></div><div className="resume-actions"><button className="button secondary" disabled={!!busy} onClick={() => setPreview(null)}>Edit Strategy</button><button className="button primary" disabled={!!busy} onClick={() => void act("resumes")}><FileText size={16} />{busy === "resumes" ? "Generating one-page PDF…" : versions.length ? "Regenerate Resume" : "Generate Resume"}</button></div></div><div className="resume-tabs talent-preview-labels"><span>Verified projects</span><span>Verified skills</span><span>Relevant coursework</span></div><div className="talent-preview-grid"><div className="resume-change-list">{preview.projects.map((project, index) => <article key={project.name}><h3>{index + 1}. {project.name}</h3><small>Company relevance {Math.round(project.relevance_score)}%</small></article>)}</div><div className="resume-chips">{preview.skills.map(skill => <span key={skill}>{skill}</span>)}</div><div className="resume-change-list">{preview.courses.length ? preview.courses.map(course => <article key={course.name}><h3>{course.name}</h3><p>{course.institution}</p><small>{course.issued}</small></article>) : <p>No verified coursework is stored for this profile.</p>}</div></div></section>}

        {selectedResume && <section className="resume-card"><div className="resume-header"><div><p className="eyebrow">Selected Company Resume</p><h2>{selectedResume.target_role}</h2><p>Generated {formatDate(selectedResume.created_at)} · Version {selectedResume.version}</p></div><div className="resume-actions"><button className="button secondary" disabled={!!busy} onClick={() => void act("preview")}><RefreshCw size={15} /> New Strategy</button>{pdfUrl && <a className="button primary" href={pdfUrl} download><Download size={15} /> Download PDF</a>}</div></div>{pdfUrl && <><div className="resume-preview-actions"><a href={pdfUrl} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open in new tab</a></div><iframe title={`${company.company_name} company resume PDF`} src={pdfUrl} className="resume-pdf" /></>}</section>}
      </div>

      <aside className="detail-aside">
        <section className="side-panel verification-panel"><div className="panel-title"><BadgeCheck size={18} /><h2>Application readiness</h2></div><dl className="verification-list"><div><dt>Type</dt><dd>Talent Community</dd></div><div><dt>Specific role</dt><dd>None</dd></div><div><dt>Resume</dt><dd>{selectedResume ? `Version ${selectedResume.version}` : "Generate first"}</dd></div><div><dt>Evidence</dt><dd>Verified only</dd></div><div><dt>Final submit</dt><dd>Manual</dd></div></dl><p className="status-reason">Apply Assistant uses the selected company resume and your own profile.</p><button className="button primary full" disabled={!!busy || !resumeId} onClick={() => void apply()}><Bot size={16} /> Apply with Assistant</button></section>
        <section className="side-panel verification-panel"><div className="panel-title"><FileText size={18} /><h2>Resume versions</h2></div><div className="talent-version-list">{versions.length ? versions.map(version => <label key={version.id} className={resumeId === version.id ? "active" : ""}><input type="radio" name="resume" disabled={!!busy || version.status !== "compiled"} checked={resumeId === version.id} onChange={() => setResumeId(version.id)} /><span><strong>Version {version.version}</strong><small>{version.target_role}</small><small>{formatDate(version.created_at)} · {version.status}</small></span></label>) : <p className="status-reason">No company resume has been generated yet.</p>}</div></section>
        <section className="side-panel verification-panel"><div className="panel-title"><Building2 size={18} /><h2>Company communities</h2></div><div className="talent-company-list">{companies.map(item => <button key={item.company_id} className={item.company_id === company.company_id ? "active" : ""} disabled={!!busy} onClick={() => void choose(item)}>{item.company_name}<small>Talent Community</small></button>)}</div><button className="button secondary full" disabled={!!busy} onClick={() => { setCompany(blankCompany()); setEditing(true); setPreview(null); setVersions([]); setResumeId(null); }}><Plus size={15} /> Add Company</button></section>
      </aside>
    </div>}
    <p className="talent-manual-note"><ShieldCheck size={15} /> Final submission always remains under your control.</p>
  </>;
}
