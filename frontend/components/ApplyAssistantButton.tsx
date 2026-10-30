"use client";

import { AlertTriangle, Bot, CheckCircle2, ExternalLink, LoaderCircle, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { canStartApplication, extensionConnectionMessage, extensionProbeMessage, isAssistantAvailable, jobApplicationUrl, preliminaryPortalName } from "@/lib/apply-assistant";
import { prepareApplication } from "@/lib/prepare-application";
import type { ApplicationReadiness, ApplicationSessionLaunch, GeneratedResume, Job } from "@/lib/types";
import { checkLocalAssistant, localAssistant, startLocalApplication } from "@/lib/local-assistant";
import LocalApplicationControls from "@/components/LocalApplicationControls";

type Props = {
  job: Job;
  disabled?: boolean;
  forceApplyNow?: boolean;
};

type ExtensionStatus = "checking" | "available" | "missing";
type ExtensionPresentation = "side_panel" | "tab";

export function detectInstalledExtension(): Promise<ExtensionPresentation> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      window.removeEventListener("message", listener);
      reject(new Error("Apply Assistant browser extension was not detected."));
    }, 1800);
    const listener = (event: MessageEvent) => {
      if (
        event.source !== window
        || event.origin !== window.location.origin
        || event.data?.source !== "internship-radar-extension"
        || event.data?.type !== "APPLICATION_ASSISTANT_PONG"
      ) return;
      window.clearTimeout(timeout);
      window.removeEventListener("message", listener);
      if (event.data.ok) resolve(event.data.data?.presentation === "tab" ? "tab" : "side_panel");
      else reject(new Error(event.data.error || "The browser extension did not respond correctly."));
    };
    window.addEventListener("message", listener);
    window.postMessage(extensionProbeMessage(), window.location.origin);
  });
}

export function connectInstalledExtension(message: ReturnType<typeof extensionConnectionMessage>): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      window.removeEventListener("message", listener);
      reject(new Error("Internship Radar extension was not detected. Install or reload the unpacked extension, then try again."));
    }, 2200);
    const listener = (event: MessageEvent) => {
      if (
        event.source !== window
        || event.origin !== window.location.origin
        || event.data?.source !== "internship-radar-extension"
        || event.data?.type !== "APPLICATION_SESSION_CONNECTION_RESULT"
      ) return;
      window.clearTimeout(timeout);
      window.removeEventListener("message", listener);
      if (event.data.ok) resolve();
      else reject(new Error(event.data.error || "The extension rejected the Application Session."));
    };
    window.addEventListener("message", listener);
    window.postMessage(message, window.location.origin);
  });
}

export default function ApplyAssistantButton({ job, disabled = false, forceApplyNow = false }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [readiness, setReadiness] = useState<ApplicationReadiness | null>(null);
  const [savedResume, setSavedResume] = useState<GeneratedResume | null>(null);
  const [advancedOverride, setAdvancedOverride] = useState(forceApplyNow);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [extensionStatus, setExtensionStatus] = useState<ExtensionStatus>("checking");
  const [extensionPresentation, setExtensionPresentation] = useState<ExtensionPresentation>("side_panel");
  const [selectedProjectNames, setSelectedProjectNames] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [editingExperience, setEditingExperience] = useState(false);
  const [editingSkills, setEditingSkills] = useState(false);
  const [preparationStep, setPreparationStep] = useState("");
  const [mode, setMode] = useState<"local" | "extension">("local");
  const [localKey, setLocalKey] = useState("");
  const [localReady, setLocalReady] = useState(false);
  const [localConnection, setLocalConnection] = useState<{ id: string; key: string; jobId: number } | null>(null);
  const preparation = useRef<AbortController | null>(null);
  const activeJobId = useRef(job.id);
  const startAttempt = useRef(0);
  const mounted = useRef(true);
  activeJobId.current = job.id;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; startAttempt.current += 1; };
  }, []);

  useEffect(() => {
    setOpen(false);
    setReadiness(null);
    setSavedResume(null);
    setLocalConnection(null);
    setConnected(false);
    setStarting(false);
    return () => { preparation.current?.abort(); startAttempt.current += 1; };
  }, [job.id]);

  function closeModal() {
    preparation.current?.abort();
    setOpen(false);
  }

  const available = isAssistantAvailable(job) && !disabled;

  async function checkExtension() {
    setExtensionStatus("checking");
    try {
      setExtensionPresentation(await detectInstalledExtension());
      setExtensionStatus("available");
    } catch {
      setExtensionStatus("missing");
    }
  }

  async function loadReadiness(selectedResume?: GeneratedResume, checkSavedResume = true) {
    if (localConnection?.jobId === job.id) { setOpen(true); return; }
    preparation.current?.abort();
    const controller = new AbortController();
    preparation.current = controller;
    setOpen(true);
    setReadiness(null);
    setSavedResume(null);
    setLoading(true);
    setError("");
    setConnected(false);
    setAdvancedOverride(forceApplyNow);
    if (mode === "extension") void checkExtension();
    try {
      if (checkSavedResume) {
        const versions = await api<GeneratedResume[]>(`/api/jobs/${job.id}/resumes`, { signal: controller.signal });
        const existing = versions.find((version) => version.job_id === job.id && version.status === "compiled");
        if (existing) {
          if (controller.signal.aborted) return;
          setSavedResume(existing);
          return;
        }
      }
      const result = await prepareApplication(job.id, controller.signal, setPreparationStep, selectedResume);
      if (controller.signal.aborted) return;
      setReadiness(result);
      setSelectedProjectNames(result.selected_experience.map((project) => String(project.name || "")).filter(Boolean));
      setSelectedSkills(result.selected_skills);
      setEditingExperience(false);
      setEditingSkills(false);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : "Application readiness could not be prepared.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  async function startApplication() {
    if (!readiness?.resume) return;
    if (readiness.resume.job_id !== job.id) return;
    const startingJobId = job.id;
    const attempt = ++startAttempt.current;
    const isCurrent = () => mounted.current && activeJobId.current === startingJobId && startAttempt.current === attempt;
    if (mode === "extension" && extensionStatus !== "available") {
      setExtensionStatus("missing");
      return;
    }
    if (mode === "local" && !localReady) return;
    const portalWindow = mode === "extension" ? window.open("about:blank", "_blank") : null;
    setStarting(true);
    setError("");
    try {
      const launch = await api<ApplicationSessionLaunch>(`/api/jobs/${job.id}/application-sessions`, {
        method: "POST",
        body: JSON.stringify({
          resume_version_id: readiness.resume.id,
          portfolio_version_id: readiness.portfolio?.id ?? null,
          allow_ineligible_override: advancedOverride,
          selected_project_names: selectedProjectNames,
          selected_skills: selectedSkills,
        }),
      });
      if (!isCurrent()) { portalWindow?.close(); return; }
      if (mode === "local") {
        const result = await startLocalApplication(localKey, launch, window.location.origin, isCurrent);
        if (!result || !isCurrent()) return;
        setLocalConnection({ ...result, jobId: startingJobId });
        setConnected(true);
        return;
      }
      await connectInstalledExtension(extensionConnectionMessage(launch, window.location.origin));
      if (!isCurrent()) { portalWindow?.close(); return; }
      if (portalWindow) {
        portalWindow.opener = null;
        portalWindow.location.href = launch.session.application_url;
      } else {
        window.open(launch.session.application_url, "_blank", "noopener,noreferrer");
      }
      setConnected(true);
    } catch (caught) {
      portalWindow?.close();
      if (isCurrent()) setError(caught instanceof Error ? caught.message : "The application session could not be started.");
    } finally {
      if (isCurrent()) setStarting(false);
    }
  }

  return (
    <>
      <button
        className="button primary"
        onClick={() => void loadReadiness()}
        disabled={!available}
        title={!jobApplicationUrl(job) ? "No application URL is available" : !available ? "Apply Assistant requires an active job with a secure application URL" : undefined}
      >
        <Bot size={16} /> Apply with Assistant
      </button>
      {open && (!readiness?.resume || readiness.resume.job_id === job.id) && (
        <div className="assistant-modal-backdrop" role="presentation" onMouseDown={() => !starting && closeModal()}>
          <section
            className="assistant-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assistant-readiness-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="assistant-close" aria-label="Close" onClick={closeModal} disabled={starting}>
              <X size={18} />
            </button>
            <div className="assistant-modal-heading">
              <span className="assistant-icon"><ShieldCheck size={23} /></span>
              <div>
                <p className="eyebrow">{preliminaryPortalName(jobApplicationUrl(job))} Apply Assistant</p>
                <h2 id="assistant-readiness-title">Application Readiness</h2>
                <p>{job.company} · {job.title}</p>
              </div>
            </div>

            {!localConnection && <div className="assistant-selection-editor">
              <label>Apply using
                <select value={mode} disabled={starting} onChange={(event) => {
                  const next = event.target.value as "local" | "extension";
                  setMode(next);
                  if (next === "extension") void checkExtension();
                }}>
                  <option value="local">Local browser — no extension</option>
                  <option value="extension">Browser extension</option>
                </select>
              </label>
              {mode === "local" && <>
                <p>Run <code>.\start-local-assistant.ps1</code> on your computer and paste its connection code below. Allow local network access if your browser asks.</p>
                <label>Local connection code<input type="password" autoComplete="off" value={localKey} onChange={(event) => { setLocalKey(event.target.value); setLocalReady(false); }} /></label>
                <button className="button secondary" disabled={!localKey.trim() || starting} onClick={async () => {
                  setError("");
                  try {
                    await checkLocalAssistant(localKey);
                    setLocalReady(true);
                  } catch (caught) { setLocalReady(false); setError(caught instanceof Error && !(caught instanceof TypeError) ? caught.message : "Could not connect to the local assistant. Start it, check the code and allow local network access."); }
                }}>{localReady ? "Local assistant connected" : "Connect local assistant"}</button>
                {localReady && <button className="button secondary" disabled={starting} onClick={async () => {
                  try { await localAssistant(localKey, "/disconnect", {}); setError(""); }
                  catch (caught) { setError(caught instanceof Error ? caught.message : "Close the previous browser from the local assistant."); }
                }}>Close any previous local browser</button>}
              </>}
            </div>}

            {loading && <div className="assistant-loading" role="status"><LoaderCircle className="spin" size={22} /> {preparationStep}</div>}
            {savedResume && !loading && !readiness && (
              <div className="assistant-selection-editor" role="group" aria-label="Choose a resume for this application">
                <strong>Ya tienes un CV generado para este puesto.</strong>
                <p>Versión {savedResume.version} · {savedResume.target_role} · {new Date(savedResume.created_at).toLocaleDateString()}</p>
                {savedResume.is_stale && <p className="notice">Tu perfil o la vacante cambiaron desde que se generó este CV. Puedes usarlo de todos modos o generar una versión actualizada.</p>}
                <div className="local-application-actions">
                  <button className="button primary" disabled={loading} onClick={() => void loadReadiness(savedResume, false)}>Usar este CV</button>
                  <button className="button secondary" disabled={loading} onClick={() => void loadReadiness(undefined, false)}>Regenerar CV</button>
                </div>
              </div>
            )}
            {error && <div className="notice error" role="alert">{error}</div>}
            {mode === "extension" && !loading && extensionStatus === "checking" && (
              <div className="assistant-extension-check" role="status"><LoaderCircle className="spin" size={17} /> Checking the Apply Assistant browser extension…</div>
            )}
            {mode === "extension" && !loading && extensionStatus === "missing" && (
              <div className="notice error assistant-extension-error" role="alert">
                <span>The Apply Assistant browser extension is required. Load or reload <strong>extension/dist</strong> in your browser extensions page, then check again. No application page was opened.</span>
                <button className="button secondary" type="button" onClick={() => void checkExtension()}>Check again</button>
              </div>
            )}
            {readiness && !loading && (
              <>
                <div className="assistant-checks">
                  {readiness.checks.map((check) => (
                    <div key={check.key} className={check.ready ? "ready" : "missing"}>
                      {check.ready ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
                      <span>{check.label}</span>
                    </div>
                  ))}
                </div>
                <div className="assistant-safety-note">
                  <ShieldCheck size={18} />
                  <div><strong>You stay in control.</strong><p>{readiness.sensitive_confirmation_notice} Internship Radar never presses the final Submit button.</p></div>
                </div>
                <div className="assistant-selection-summary">
                  <p><strong>Resume selected</strong><span>{readiness.resume ? `Recommended Resume v${readiness.resume.version} — ${readiness.resume.target_role}` : "Not ready"}</span></p>
                  <p><strong>Project Portfolio</strong><span>{readiness.portfolio?.filename ?? "Optional — no portfolio prepared"}</span></p>
                </div>
                <div className="assistant-selection-editor">
                  <div className="assistant-editable-selection">
                    <div className="assistant-selection-heading">
                      <strong>Experience selected for this application</strong>
                      <button className="button-link" type="button" onClick={() => setEditingExperience((value) => !value)}>
                        {editingExperience ? "Use Experience" : "Edit"}
                      </button>
                    </div>
                    {readiness.selected_experience.map((project) => {
                      const name = String(project.name || "Verified project");
                      const checked = selectedProjectNames.includes(name);
                      if (!editingExperience && !checked) return null;
                      return (
                        <label className="assistant-selection-option" key={name}>
                          {editingExperience && (
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => setSelectedProjectNames((current) => checked ? current.filter((item) => item !== name) : [...current, name])}
                            />
                          )}
                          <span>
                            <b>{name}</b>
                            <small>{readiness.project_match_reasons[name] || String(project.relevance_reason || "Verified project selected by the Recommended Resume.")}</small>
                          </span>
                        </label>
                      );
                    })}
                    {!selectedProjectNames.length && <span className="assistant-empty-selection">Select at least one project.</span>}
                  </div>
                  <div className="assistant-editable-selection">
                    <div className="assistant-selection-heading">
                      <strong>Skills selected</strong>
                      <button className="button-link" type="button" onClick={() => setEditingSkills((value) => !value)}>
                        {editingSkills ? "Use Skills" : "Edit"}
                      </button>
                    </div>
                    <div className="assistant-skill-options">
                      {readiness.selected_skills.map((skill) => {
                        const checked = selectedSkills.includes(skill);
                        if (!editingSkills && !checked) return null;
                        return (
                          <label className="assistant-skill-option" key={skill} title={readiness.skill_match_reasons[skill]}>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={!editingSkills}
                              onChange={() => setSelectedSkills((current) => checked ? current.filter((item) => item !== skill) : [...current, skill])}
                            />
                            <span>{skill}</span>
                          </label>
                        );
                      })}
                    </div>
                    {!selectedSkills.length && <span className="assistant-empty-selection">Select at least one verified skill.</span>}
                  </div>
                </div>
                {readiness.hard_blocked && (
                  <div className="assistant-blocker">
                    <strong>{forceApplyNow ? "Manual Force Apply Now enabled" : "Apply Assistant unavailable"}</strong>
                    <p>{readiness.blocker_reason}</p>
                    {forceApplyNow
                      ? <p>The eligibility analysis remains unchanged; this manual Santiago-only override allows the application workflow to continue.</p>
                      : <label className="checkbox-row">
                        <input type="checkbox" checked={advancedOverride} onChange={(event) => setAdvancedOverride(event.target.checked)} />
                        Advanced: apply anyway after reviewing this eligibility blocker
                      </label>}
                  </div>
                )}
                {readiness.checks.some((item) => !item.ready && ["contact", "education", "location", "availability", "authorization", "skills", "projects"].includes(item.key)) && (
                  <p className="assistant-profile-link">Complete the missing verified fields in <Link href="/profile">Profile</Link>.</p>
                )}
                {readiness.resume && <p className="assistant-resume">Resume ready: version {readiness.resume.version} · {readiness.resume.target_role}</p>}
                {localConnection ? <LocalApplicationControls connection={localConnection} onClose={() => { setLocalConnection(null); setConnected(false); setReadiness(null); }} /> : connected ? (
                  <div className="notice success"><CheckCircle2 size={17} /> {extensionPresentation === "tab" ? "Application portal opened. On that page, click the Internship Radar extension icon to open the controls, then enable the portal." : "Application portal opened. Enable this portal in the extension side panel, then fill the page."}</div>
                ) : (
                  <button
                    className="button primary full"
                    onClick={() => void startApplication()}
                    disabled={starting || (mode === "local" ? !localReady : extensionStatus !== "available") || !selectedProjectNames.length || !selectedSkills.length || !canStartApplication(readiness, advancedOverride)}
                  >
                    {starting ? <LoaderCircle className="spin" size={17} /> : <ExternalLink size={17} />}
                    {starting ? "Starting secure session…" : "Start Application"}
                  </button>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
