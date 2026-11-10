"use client";
import { useState } from "react";
import { areas, emptyOpportunity, eligibility, funding, letters, OpportunityInput, priorities, statuses, types } from "@/lib/opportunities";

export function OpportunityEditor({initial = emptyOpportunity, onSave, onCancel}: {initial?: OpportunityInput; onSave: (value: OpportunityInput) => Promise<void>; onCancel?: () => void}) {
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = (key: keyof OpportunityInput, entry: unknown) => setValue(v => ({...v, [key]: entry}));
  const text = (key: keyof OpportunityInput, label: string, required = false, type = "text") => <label key={key}>{label}<input aria-label={label} type={type} required={required} value={String(value[key] ?? "")} onChange={e => update(key, e.target.value)} /></label>;
  const select = (key: keyof OpportunityInput, label: string, options: string[]) => <label key={key}>{label}<select aria-label={label} value={String(value[key])} onChange={e => update(key, e.target.value)}>{options.map(o => <option key={o}>{o}</option>)}</select></label>;
  const textarea = (key: keyof OpportunityInput, label: string) => <label key={key}>{label}<textarea aria-label={label} rows={3} value={String(value[key])} onChange={e => update(key, e.target.value)} /></label>;
  const lines = (key: "required_documents" | "supporting_urls", label: string) => <label key={key}>{label} (one per line)<textarea aria-label={label} rows={3} value={value[key].join("\n")} onChange={e => update(key, e.target.value.split("\n"))} /></label>;
  return <form className="opportunity-editor" onSubmit={async e => {e.preventDefault(); setBusy(true); setError(""); try {await onSave({...value, required_documents: value.required_documents.filter(Boolean), supporting_urls: value.supporting_urls.filter(Boolean)});} catch (err) {setError(err instanceof Error ? err.message : "Save failed");} finally {setBusy(false);}}}>
    <div className="form-grid">
      {text("program", "Program name", true)}{text("organization", "University / organization", true)}
      {text("country", "Country", true)}{text("city", "City")}
      {text("official_url", "Official website", true, "url")}{text("application_url", "Application link", false, "url")}
      {select("program_type", "Opportunity type", types)}{select("priority", "Priority", priorities)}
      {text("employment_type", "Employment")}{select("compatibility_level", "Compatibility assessment", ["Unknown", "Partial", "Strong", "Low"])}
      {select("status", "Application status", statuses)}{select("international_eligibility", "International eligibility", eligibility)}
      {select("undergraduate_eligible", "Undergraduates eligible", ["Unknown", "Yes", "No"])}{select("citizenship_restriction", "Citizenship restriction", ["Unknown", "Yes", "No"])}
      {select("recommendation_letters", "Recommendation letters", letters)}{select("host_required", "Host professor required", ["Unknown", "Yes", "No"])}
      {text("lab", "Laboratory")}{text("professor", "Professor / supervisor")}
      <label>Deadline (date only)<input type="date" value={value.deadline || ""} onChange={e => setValue(v => ({...v, deadline: e.target.value || null, deadline_at: null}))} /></label>
      <label>Exact deadline with timezone, if published<input placeholder="2026-11-01T23:55:00+01:00" value={value.deadline_at || ""} onChange={e => update("deadline_at", e.target.value || null)} /></label>
    </div>
    <fieldset><legend>Research areas</legend><div className="opportunity-checks">{Array.from(new Set([...areas, ...value.research_areas])).map(a => <label key={a}><input type="checkbox" checked={value.research_areas.includes(a)} onChange={e => update("research_areas", e.target.checked ? [...value.research_areas, a] : value.research_areas.filter(x => x !== a))} />{a}</label>)}</div><label>Additional research areas (comma separated)<input value={value.research_areas.filter(a => !areas.includes(a)).join(", ")} onChange={e => update("research_areas", [...value.research_areas.filter(a => areas.includes(a)), ...e.target.value.split(",").map(a => a.trim())])} /></label></fieldset>
    <fieldset><legend>Funding</legend><div className="opportunity-checks">{funding.map(f => <label key={f}><input type="checkbox" checked={value.funding.includes(f)} onChange={e => {const list = e.target.checked ? [...value.funding.filter(x => x !== "Unknown"), f] : value.funding.filter(x => x !== f); update("funding", f === "Unknown" && e.target.checked ? ["Unknown"] : list.length ? list : ["Unknown"]);}} />{f}</label>)}</div></fieldset>
    <div className="form-grid">{textarea("description", "Overview")}{textarea("eligibility_notes", "Eligibility details")}{textarea("funding_notes", "Funding details")}{textarea("recommendation_notes", "Recommendation details")}{textarea("deadline_notes", "Deadline details")}{textarea("notes", "Notes")}{lines("required_documents", "Required documents")}{lines("supporting_urls", "Supporting official sources")}</div>
    {textarea("compatibility_notes", "Compatibility evidence and concerns")}
    <label className="opportunity-inline"><input type="checkbox" checked={value.favorite} onChange={e => update("favorite", e.target.checked)} />Favorite</label>
    {error && <p className="notice" role="alert">{error}</p>}
    <div className="header-actions"><button className="button" disabled={busy}>{busy ? "Saving…" : "Save Opportunity"}</button>{onCancel && <button className="button secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button>}</div>
  </form>;
}
