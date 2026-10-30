import type { AgentFieldResolution, AssistantPageState, ExtensionPayload } from "../../extension/src/shared/types";
import { fieldPolicy } from "../../extension/src/shared/policies";

export type LocalEvidence = { id: string; kind: "FACT" | "SKILL" | "PROJECT" | "WORK"; label: string; text: string };
export type LocalQuestion = {
  label: string; dom_field_id: string; control_type: string; options: string[]; required: boolean;
  confidence: number; canonical_field: string; evidence_ids: string[];
};
export const LOCAL_INTENTS = ["FACT", "SKILLS", "PROJECTS", "WORK", "MOTIVATION", "SENSITIVE", "UNKNOWN"] as const;

/** Only the authenticated session's facts and resume-selected evidence are offered to the model. */
export function localCandidateEvidence(payload: ExtensionPayload): LocalEvidence[] {
  const result: LocalEvidence[] = [];
  const add = (id: string, kind: LocalEvidence["kind"], label: string, value: unknown) => {
    if (result.some((item) => item.id === id)) return;
    if ((typeof value === "string" || typeof value === "number") && String(value).trim()) {
      result.push({ id, kind, label, text: String(value).trim().slice(0, 3000) });
    }
  };
  for (const group of ["contact", "education", "links"] as const) {
    for (const [key, value] of Object.entries(payload.profile[group])) add(`${group}.${key}`, "FACT", `${group}: ${key}`, value);
  }
  const names = String(payload.profile.contact.full_name || "").trim().split(/\s+/);
  add("contact.first_name", "FACT", "First / given name", payload.profile.contact.first_name || names[0]);
  add("contact.last_name", "FACT", "Last / family name", payload.profile.contact.last_name || names.slice(1).join(" "));
  const graduation = String(payload.profile.education.expected_graduation_date || "");
  if (/^\d{4}-\d{2}-\d{2}/.test(graduation)) {
    add("education.graduation_year", "FACT", "Expected graduation year", graduation.slice(0, 4));
    const date = new Date(`${graduation.slice(0, 7)}-01T12:00:00Z`);
    if (Number.isFinite(date.getTime())) add("education.graduation_month", "FACT", "Expected graduation month", date.toLocaleString("en-US", { month: "long", timeZone: "UTC" }));
  }
  payload.profile.languages.forEach((value, index) => add(`language:${index}`, "FACT", "Verified language", value));
  const verified = new Set(payload.profile.verified_skills.map((value) => value.toLowerCase()));
  payload.resume.selected_skills.filter((value) => verified.has(value.toLowerCase())).slice(0, 60)
    .forEach((value, index) => add(`skill:${index}`, "SKILL", value, value));
  const projects = payload.session.project_experience_json?.length ? payload.session.project_experience_json : payload.session.selected_projects_json;
  const canonicalProjects = payload.profile.verified_projects || [];
  const normalizedName = (value: unknown) => String(value || "").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  (projects || []).slice(0, 12).forEach((project, index) => {
    const canonical = canonicalProjects.find((item) => normalizedName(item.name || item.title) === normalizedName(project.name || project.title));
    if (canonicalProjects.length && !canonical) return;
    if ([project, canonical].some((item) => item && (item.resume_eligible === false || item.is_resume_eligible === false
      || item.verified === false || item.is_verified === false
      || [item.evidence_strength, item.status, item.verification_status].some((value) => /^(?:PLANNED_ONLY|PLANNED|NOT_VERIFIED|REJECTED)$/i.test(String(value || "")))))) return;
    const selected = project.resume_selection && typeof project.resume_selection === "object" ? project.resume_selection as Record<string, unknown> : {};
    // Positive evidence: immutable bullets from the resume bound to this scoped
    // application, already validated by the existing application selector.
    const bullets = Array.isArray(selected.bullets) ? selected.bullets : [];
    const description = bullets.filter((value) => typeof value === "string" && value.trim()).join(" ");
    if (description) add(`project:${index}`, "PROJECT", String(project.name || project.title || "Verified project"), `${project.name || project.title || "Project"}: ${description}`);
  });
  payload.profile.verified_work_experience.slice(0, 8).forEach((work, index) => {
    const bullets = Array.isArray(work.bullets) ? work.bullets.filter((value) => typeof value === "string").join(" ") : String(work.description || "");
    add(`work:${index}`, "WORK", String(work.title || "Verified work experience"), `${work.title || ""} — ${work.organization || work.company || ""}: ${bullets}`);
  });
  return result;
}

/** The model selects evidence IDs, never writes candidate accomplishments or sensitive answers. */
export function evidenceAnswer(question: LocalQuestion, fieldId: string, evidence: LocalEvidence[], model: string): AgentFieldResolution {
  const policy = fieldPolicy(question.label, question.control_type);
  const sensitive = question.canonical_field === "SENSITIVE" || policy.policy === "CONFIRM_REQUIRED"
    || policy.normalizedKey === "SECURITY_OR_ATTESTATION"
    || /authoriz|sponsor|visa|salary|compensat|disabil|gender|ethnic|veteran|criminal|signature|consent|certify|password|captcha|salario|autorizaci[oó]n|patrocinio/i.test(question.label);
  const expectedKind = ({ FACT: "FACT", SKILLS: "SKILL", PROJECTS: "PROJECT", WORK: "WORK", MOTIVATION: "PROJECT" } as Record<string, string>)[question.canonical_field];
  const matched = evidence.filter((item) => question.evidence_ids.includes(item.id) && item.kind === expectedKind);
  const supported = !sensitive && question.confidence >= 0.65 && matched.length > 0 && (question.canonical_field !== "FACT" || matched.length === 1);
  const text = supported ? matched.map((item) => item.text).join(question.canonical_field === "SKILLS" ? ", " : "\n\n") : "";
  const answer = text && ["PROJECTS", "MOTIVATION"].includes(question.canonical_field)
    ? `My relevant experience comes from academic and personal projects:\n\n${text}` : text;
  return {
    field_id: fieldId, canonical_field: question.canonical_field, question_category: ["PROJECTS", "WORK", "MOTIVATION"].includes(question.canonical_field) ? "EXPERIENCE_QUESTION" : "PROFILE_FACT",
    action: sensitive ? "CONFIRM" : supported ? "GENERATE_REVIEW" : "MANUAL_ONLY", selected_value: answer,
    confidence: question.confidence, match_type: supported ? "VERIFIED_SESSION_EVIDENCE" : "UNKNOWN",
    reason_summary: sensitive ? "Responde personalmente: esta pregunta requiere tu confirmación."
      : supported ? `Evidencia de tu perfil/CV: ${matched.map((item) => item.label).join(", ")}`
      : "No hay evidencia verificada suficiente para sugerir una respuesta. No se infieren cualificaciones.",
    requires_review: true, evidence_ids: supported ? matched.map((item) => item.id) : [], privacy_level: sensitive ? "SENSITIVE" : "PERSONAL",
    provider: `ollama-local:${model}`, execution_location: "LOCAL",
  };
}

export function mergeLocalQuestions(fields: AssistantPageState["fields"], questions: LocalQuestion[], key: string) {
  const merged = [...fields];
  const seen = new Set<string>();
  const mapped: Array<{ question: LocalQuestion; fieldId: string }> = [];
  for (const [index, question] of questions.entries()) {
    const normalized = question.label.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    const existing = question.dom_field_id ? fields.find((field) => field.fieldId === question.dom_field_id)
      : fields.find((field) => field.label.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "") === normalized);
    const fieldId = existing?.fieldId || `vision:${key.slice(0, 16)}:${index}`;
    if (seen.has(fieldId)) continue;
    seen.add(fieldId);
    if (!existing) merged.push({ fieldId, label: question.label, nearbyText: "Pregunta leída en la captura local; revisar el texto visualmente.",
      controlType: question.control_type, availableOptions: question.options, currentValue: "", required: question.required,
      normalizedKey: "UNKNOWN", policy: "MANUAL_ONLY", confidence: question.confidence });
    mapped.push({ question: existing ? { ...question, label: existing.label, control_type: existing.controlType } : question, fieldId });
  }
  return { fields: merged, mapped };
}
