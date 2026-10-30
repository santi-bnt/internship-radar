import type { ApplicationPortalAdapter } from "../ApplicationPortalAdapter";
import { validateConsistency } from "../../../shared/consistency";
import { detectAssessmentText, fieldPolicy, genericSafeFieldPatterns, isFinalSubmitText } from "../../../shared/policies";
import { matchQuestion, normalizeQuestion } from "../../../shared/questionMatcher";
import type {
  AdapterDiagnostics,
  AgentFieldResolution,
  ApplicationStage,
  AssistantPageState,
  AssessmentType,
  ConsistencyIssue,
  DetectedField,
  ExtensionPayload,
  PendingQuestion,
  PreparedApplicationFile,
  PortalSupportStatus,
  PortalType,
  PortalValueConflict
} from "../../../shared/types";

type FormControl = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

export interface SemanticAdapterConfig {
  portalType: PortalType;
  adapterVersion: string;
  supportStatus: PortalSupportStatus;
  fieldSelector: string;
  containerSelector: string;
  optionSelector: string;
  fingerprintSelectors: string[];
  preserveSavedValues?: boolean;
  genericSafeOnly?: boolean;
  structuredSkills?: boolean;
  structuredLanguages?: boolean;
  pageName: string;
}

const skillAliases: Record<string, string[]> = {
  "C++": ["C Plus Plus", "Cplusplus"], "C#": ["C Sharp"],
  "REST APIs": ["REST API", "RESTful APIs"], "Embedded Systems": ["Embedded Software", "Embedded Development"],
  SystemVerilog: ["System Verilog"]
};

export function visible(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  return style.display !== "none" && style.visibility !== "hidden" && !element.hasAttribute("hidden");
}

export function elementLabel(element: HTMLElement, containerSelector: string): string {
  const visionLabel = element.getAttribute("data-internship-radar-vision-label");
  if (visionLabel) return visionLabel.trim();
  const ariaLabel = element.getAttribute("aria-label");
  if (ariaLabel) return ariaLabel.trim();
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const labelled = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ").trim();
    if (labelled) return labelled;
  }
  if (element instanceof HTMLInputElement && element.type === "file") {
    if (element.id === "resume" || /resume|cv/i.test(element.id || element.getAttribute("name") || "")) return "Resume / CV";
    const group = element.closest<HTMLElement>("[role='group'][aria-labelledby]");
    const groupLabelId = group?.getAttribute("aria-labelledby");
    const groupLabel = groupLabelId ? document.getElementById(groupLabelId)?.textContent?.trim() : "";
    if (groupLabel) return groupLabel;
  }
  if (element.id) {
    const escaped = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(element.id) : element.id.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
    const explicit = document.querySelector<HTMLLabelElement>(`label[for='${escaped}']`);
    if (explicit?.textContent) return explicit.textContent.trim();
  }
  const wrapping = element.closest("label");
  if (wrapping?.textContent) return wrapping.textContent.trim();
  const container = element.closest(containerSelector);
  const heading = container?.querySelector("legend, label, [data-automation-id*='label'], [data-testid*='label'], [class*='label'], h2, h3");
  if (heading?.textContent) return heading.textContent.trim();
  return element.getAttribute("name") || element.getAttribute("placeholder") || "Unknown field";
}

export function nativeSetValue(element: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(element, value);
  try {
    element.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, inputType: "insertText", data: value }));
  } catch {
    element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  }
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function resolvedJobCountry(payload: ExtensionPayload): string {
  const physical = String(payload.session.job_snapshot_json.physical_work_country_required || "");
  if (physical && normalizeQuestion(physical) !== "unknown") return physical;
  return String(payload.session.job_snapshot_json.country || "");
}

function canonicalValue(field: DetectedField, payload: ExtensionPayload): unknown {
  const key = normalizeQuestion(field.label);
  const { contact, education, links, languages } = payload.profile;
  const authorization = payload.profile.work_authorization;
  const preferences = payload.profile.application_preferences;
  const names = String(contact.full_name || "").trim().split(/\s+/);
  if (field.normalizedKey === "JOB_DISCOVERY_SOURCE") return preferences.confirmed_at ? "Google" : undefined;
  if (field.normalizedKey === "FULL_TIME_SUMMER_AVAILABILITY") return preferences.confirmed_at ? (preferences.full_time_summer_availability ? "Yes" : "No") : undefined;
  if (field.normalizedKey === "SPRING_SUMMER_COMBINED_AVAILABILITY") return preferences.confirmed_at ? (preferences.spring_summer_combined_availability ? "Yes" : "No") : undefined;
  if (field.normalizedKey === "CITIZENSHIP") return authorization.citizenship_country;
  if (field.normalizedKey === "US_WORK_AUTHORIZATION") {
    if (resolvedJobCountry(payload) && !/united states|\bus\b|\bu s\b/i.test(resolvedJobCountry(payload))) return undefined;
    return /not currently authorized/.test(key) ? !authorization.us_work_authorized : authorization.us_work_authorized;
  }
  if (field.normalizedKey === "US_SPONSORSHIP_REQUIRED") {
    if (resolvedJobCountry(payload) && !/united states|\bus\b|\bu s\b/i.test(resolvedJobCountry(payload))) return undefined;
    return authorization.requires_us_employment_sponsorship;
  }
  if (field.normalizedKey === "MEXICO_WORK_AUTHORIZATION") {
    if (resolvedJobCountry(payload) && !/mexico/i.test(resolvedJobCountry(payload))) return undefined;
    return authorization.work_authorized_countries.some((country) => /mexico/i.test(country));
  }
  if (field.normalizedKey === "WORK_AUTHORIZATION_CURRENT_COUNTRY") {
    const country = resolvedJobCountry(payload);
    if (!country) return undefined;
    return authorization.work_authorized_countries.some((value) => normalizeQuestion(value) === normalizeQuestion(country));
  }
  if (field.normalizedKey === "SPONSORSHIP_CURRENT_COUNTRY") {
    const country = resolvedJobCountry(payload);
    if (!country) return undefined;
    if (/united states|\bus\b|\bu s\b/i.test(country)) return authorization.requires_us_employment_sponsorship;
    if (authorization.work_authorized_countries.some((value) => normalizeQuestion(value) === normalizeQuestion(country))) return false;
    return undefined;
  }
  if (/preferred location/.test(key)) return undefined;
  if (/current location|location city|^location(?: |$)/.test(key)) return contact.current_location || [contact.city, contact.state, contact.country].filter(Boolean).join(", ");
  if (/\bfirst name|given name\b/.test(key)) return names[0] || "";
  if (/\blast name|family name|surname\b/.test(key)) return names.slice(1).join(" ");
  if (/\bfull name|legal name|preferred name\b/.test(key)) return contact.full_name;
  if (/email/.test(key)) return contact.professional_email;
  if (/phone|mobile/.test(key)) return contact.phone;
  if (/address line 2|address 2/.test(key)) return contact.address_line2;
  if (/street|address line 1|address 1/.test(key)) return contact.address_line1;
  if (/\bcity\b/.test(key)) return contact.city;
  if (/^(?:state|province|region)(?:\/| |$)/.test(key) || /address.*(?:state|province|region)/.test(key)) return contact.state;
  if (/postal|zip/.test(key)) return contact.postal_code;
  if (/\bcountry\b/.test(key)) return contact.country;
  const graduation = String(education.expected_graduation_date || "");
  const graduationMonth = Number(graduation.slice(5, 7));
  const graduationYear = graduation.slice(0, 4);
  if (/end date month|graduation month/.test(key)) return graduationMonth ? new Date(2000, graduationMonth - 1, 1).toLocaleString("en-US", { month: "long" }) : undefined;
  if (/end date year|graduation year/.test(key)) return graduationYear || undefined;
  const educationStart = String(education.start_date || "");
  if (/start date year|education start year/.test(key)) return educationStart.slice(0, 4) || undefined;
  if (/university|school|institution/.test(key)) return education.university;
  if (/field of study|major|discipline/.test(key)) return education.field_of_study;
  if (/\bdegree\b/.test(key)) return education.degree;
  if (/gpa|grade point/.test(key)) return education.gpa;
  if (/education start|school start|start date/.test(key)) return education.start_date;
  if (/graduation|expected completion|education end|end date/.test(key)) {
    if (field.element instanceof HTMLInputElement && field.element.type === "month") return graduation.slice(0, 7);
    return graduationMonth && graduationYear ? `${new Date(2000, graduationMonth - 1, 1).toLocaleString("en-US", { month: "long" })} ${graduationYear}` : graduation;
  }
  if (/linked ?in/.test(key)) return links.linkedin;
  if (/github/.test(key)) return links.github;
  if (/website|portfolio/.test(key)) return links.github || links.linkedin;
  if (/language/.test(key)) return languages[0] || "";
  if (/student status|currently enrolled/.test(key)) return education.expected_graduation_date ? "Yes" : undefined;
  if (/project|academic experience|relevant experience/.test(key)) {
    return (payload.session.project_experience_json || payload.session.selected_projects_json || []).map((project) => {
      const selected = project.resume_selection && typeof project.resume_selection === "object" ? project.resume_selection as Record<string, unknown> : {};
      const bullets = Array.isArray(selected.bullets) ? selected.bullets : Array.isArray(project.bullets) ? project.bullets : [];
      return `${String(project.name || "Verified project")}: ${bullets.length ? bullets.join(" ") : String(project.details || project.description || "")}`.trim();
    }).filter(Boolean).join("\n\n");
  }
  if (/work experience|employment experience/.test(key)) {
    if (payload.profile.verified_work_experience.length) {
      return payload.profile.verified_work_experience.map((experience) => {
        const title = String(experience.title || "Verified experience");
        const organization = String(experience.organization || experience.company || "");
        const details = Array.isArray(experience.bullets) ? experience.bullets.join(" ") : String(experience.description || "");
        return `${title}${organization ? ` — ${organization}` : ""}: ${details}`.trim();
      }).join("\n\n");
    }
    if (payload.session.generated_experience_text) {
      return [
        "Student Software Developer — Academic & Personal Projects",
        "Tecnológico de Monterrey / Personal Projects",
        payload.session.generated_experience_text,
      ].join("\n");
    }
  }
  return undefined;
}

function optionAliases(field: DetectedField, value: unknown, payload: ExtensionPayload): string[] {
  const aliases = [String(value)];
  if (typeof value === "boolean") aliases.push(value ? "Yes" : "No");
  if (field.normalizedKey === "JOB_DISCOVERY_SOURCE") aliases.push("Google Search", "Web Search", "Search Engine", "Online Search");
  if (["FULL_TIME_SUMMER_AVAILABILITY", "SPRING_SUMMER_COMBINED_AVAILABILITY"].includes(field.normalizedKey)) aliases.push(Boolean(value) || normalizeQuestion(String(value)) === "yes" ? "Yes" : "No");
  const label = normalizeQuestion(field.label);
  if (/current location|location city|^location(?: |$)/.test(label)) {
    const { city, state, country } = payload.profile.contact;
    aliases.push([city, state, country].filter(Boolean).join(", "), [city, country].filter(Boolean).join(", "), city);
  }
  if (/end date month|graduation month/.test(label)) {
    const month = String(value);
    const monthNumber = String(new Date(`${month} 1, 2000`).getMonth() + 1).padStart(2, "0");
    aliases.push(month.slice(0, 3), monthNumber, String(Number(monthNumber)));
  }
  return [...new Set(aliases.filter(Boolean))];
}

export function comparePortalValue(portalValue: unknown, verifiedValue: unknown, label: string): PortalValueConflict {
  const portal = String(portalValue ?? "").trim();
  const verified = String(verifiedValue ?? "").trim();
  if (normalizeQuestion(portal) === normalizeQuestion(verified)) return { classification: "SAME", portalValue: portal, verifiedValue: verified };
  if (normalizeQuestion(portal).replace(/\s/g, "") === normalizeQuestion(verified).replace(/\s/g, "")) return { classification: "FORMAT_DIFFERENCE", portalValue: portal, verifiedValue: verified };
  const critical = /email|graduation|education start|university|school|degree|gpa/.test(normalizeQuestion(label));
  return { classification: critical ? "CRITICAL_CONFLICT" : "POTENTIAL_CONFLICT", portalValue: portal, verifiedValue: verified };
}

export abstract class SemanticApplicationAdapter implements ApplicationPortalAdapter {
  readonly portalType: PortalType;
  readonly adapterVersion: string;
  readonly supportStatus: PortalSupportStatus;
  protected fields: DetectedField[] = [];
  protected failed = 0;
  protected filled = 0;
  protected detectionEvidence: string[] = [];
  protected conflictMemory = new Map<string, PortalValueConflict>();
  protected acceptedPortalValues = new Set<string>();
  protected attachedFiles = new Map<"RESUME" | "PORTFOLIO", { filename: string; versionId: number }>();

  protected constructor(protected readonly config: SemanticAdapterConfig) {
    this.portalType = config.portalType;
    this.adapterVersion = config.adapterVersion;
    this.supportStatus = config.supportStatus;
  }

  protected companyAliases(payload?: ExtensionPayload): Record<string, string[]> {
    return payload?.company_policy.known_question_aliases || {};
  }

  protected fingerprintFound(): boolean {
    const found = this.config.fingerprintSelectors.filter((selector) => document.querySelector(selector));
    this.detectionEvidence = found.map((selector) => `DOM:${selector}`);
    return found.length > 0;
  }

  detectPortalMetadata(): { companyHost: string; jobTitle: string; portalJobId: string } {
    const page = `${window.location.pathname} ${document.title} ${document.querySelector("main")?.textContent || ""}`.slice(0, 10000);
    const requisition = /\b(?:JR|REQ|R)[-_]?\d{4,}\b/i.exec(page);
    const jobTitle = document.querySelector<HTMLElement>("h1, [data-automation-id='jobPostingHeader'], [data-testid*='job-title']")?.textContent?.trim() || "";
    return { companyHost: window.location.hostname.toLocaleLowerCase(), jobTitle, portalJobId: requisition?.[0].toUpperCase() || "" };
  }

  detectFields(payload?: ExtensionPayload): DetectedField[] {
    this.fingerprintFound();
    const elements = [...document.querySelectorAll<HTMLElement>(this.config.fieldSelector)]
      .filter((element) => (visible(element) || (element instanceof HTMLInputElement && element.type === "file")) && !element.hasAttribute("disabled"))
      .filter((element) => element.getAttribute("aria-hidden") !== "true")
      .filter((element) => !(element instanceof HTMLInputElement && element.type === "hidden"));
    const signatureOccurrences = new Map<string, number>();
    this.fields = elements.map((element) => {
      const label = elementLabel(element, this.config.containerSelector);
      const inputType = element instanceof HTMLInputElement ? element.type : element.getAttribute("role") || element.tagName.toLocaleLowerCase();
      const container = element.closest<HTMLElement>(this.config.containerSelector);
      const nearbyText = (container?.textContent || label).replace(/\s+/g, " ").trim().slice(0, 4000);
      const availableOptions = element instanceof HTMLSelectElement
        ? [...element.options].map((option) => (option.textContent || option.value).trim()).filter(Boolean)
        : [...(container?.querySelectorAll<HTMLElement>(this.config.optionSelector) || [])]
            .filter(visible).map((option) => (option.textContent || option.getAttribute("aria-label") || "").trim()).filter(Boolean);
      // Do not use the element's global DOM index as its identity. React-based
      // portals frequently insert validation or helper controls while the
      // backend is analyzing the page, which used to invalidate every planned
      // decision before it could be executed.
      const identity = element.id
        ? `id=${element.id}`
        : element.getAttribute("name")
          ? `name=${element.getAttribute("name")}`
          : element.getAttribute("data-automation-id")
            ? `automation=${element.getAttribute("data-automation-id")}`
            : `semantic=${normalizeQuestion(label)}|${inputType}`;
      const occurrence = signatureOccurrences.get(identity) || 0;
      signatureOccurrences.set(identity, occurrence + 1);
      const fieldId = `${identity}|occurrence=${occurrence}`.slice(0, 240);
      const required = element.hasAttribute("required") || element.getAttribute("aria-required") === "true" || element.closest("[aria-required='true']") != null;
      const maxlength = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement
        ? (element.maxLength > 0 ? element.maxLength : undefined)
        : undefined;
      const matched = matchQuestion(label, this.companyAliases(payload));
      const baseClassification = fieldPolicy(label, inputType);
      const classification = matched.questionKey !== "UNKNOWN"
        ? { normalizedKey: matched.questionKey, policy: matched.policy, confidence: matched.confidence }
        : baseClassification;
      let policy = classification.policy;
      const provisionalField: DetectedField = {
        element, fieldId, nearbyText, controlType: inputType, availableOptions,
        currentValue: this.currentValue(element), required, maxlength,
        label,
        normalizedKey: classification.normalizedKey,
        policy,
        confidence: classification.confidence,
      };
      if (policy === "AUTO_FILL_REVIEW_REQUIRED" && payload && canonicalValue(provisionalField, payload) === undefined) {
        policy = "CONFIRM_REQUIRED";
      }
      if (this.config.genericSafeOnly && !genericSafeFieldPatterns.some((pattern) => pattern.test(normalizeQuestion(label)))) policy = "MANUAL_ONLY";
      const answerSource = policy === "AUTO_FILL_REVIEW_REQUIRED"
        ? classification.normalizedKey === "JOB_DISCOVERY_SOURCE" || classification.normalizedKey.includes("AVAILABILITY")
          ? payload?.profile.application_preferences.answer_source || "USER_CONFIRMED"
          : "PREVIOUSLY_CONFIRMED_CANDIDATE_PROFILE"
        : undefined;
      return { element, fieldId, label, nearbyText, controlType: inputType, availableOptions, currentValue: this.currentValue(element), required, maxlength, normalizedKey: classification.normalizedKey, policy, confidence: classification.confidence, answerSource, conflict: this.conflictMemory.get(classification.normalizedKey) };
    });
    return this.fields;
  }

  protected currentValue(element: HTMLElement): string {
    if (element instanceof HTMLInputElement && (element.type === "password" || /one-time-code|current-password|new-password/.test(element.autocomplete))) return "";
    if (element instanceof HTMLInputElement && element.type === "file") return element.files?.[0]?.name || "";
    if (element instanceof HTMLInputElement && ["checkbox", "radio"].includes(element.type)) return element.checked ? (element.labels?.[0]?.textContent?.trim() || element.value) : "";
    if (element instanceof HTMLInputElement && element.getAttribute("role") === "combobox") {
      const selected = element.closest(".select__container, .select-shell, .field-wrapper, .input-wrapper")?.querySelector<HTMLElement>(".select__single-value, [class*='singleValue']")?.textContent?.trim();
      return selected || element.value;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) return element.value;
    return element.getAttribute("aria-valuetext") || element.textContent?.trim() || "";
  }

  protected async waitForExactOption(
    values: string[],
    timeoutMs = 1200,
    scope?: Element | null,
    allowTrailingDialCode = false
  ): Promise<HTMLElement | null> {
    const normalized = values.map(normalizeQuestion);
    const matchingOption = (root: ParentNode) => [...root.querySelectorAll<HTMLElement>(this.config.optionSelector)]
      .find((option) => {
        if (!visible(option)) return false;
        const optionValue = normalizeQuestion(option.textContent || option.getAttribute("aria-label") || "");
        return normalized.some((value) =>
          optionValue === value ||
          (allowTrailingDialCode && optionValue.startsWith(`${value} `) && /^\d{1,4}$/.test(optionValue.slice(value.length + 1)))
        );
      }) || null;
    const find = () => matchingOption(scope || document) || (scope ? matchingOption(document) : null);
    const immediate = find();
    if (immediate) return immediate;
    return new Promise((resolve) => {
      const observer = new MutationObserver(() => {
        const option = find();
        if (option) { observer.disconnect(); window.clearTimeout(timer); resolve(option); }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      const timer = window.setTimeout(() => { observer.disconnect(); resolve(null); }, timeoutMs);
    });
  }

  protected selectedOption(element: HTMLElement): HTMLElement | null {
    const container = element.closest(this.config.containerSelector) || element.parentElement;
    return container?.querySelector<HTMLElement>(
      ".select__single-value, [class*='singleValue'], .select__multi-value, [class*='multiValue']"
    ) || null;
  }

  protected activateOption(option: HTMLElement): void {
    const eventOptions: MouseEventInit = { bubbles: true, cancelable: true };
    option.dispatchEvent(new MouseEvent("mousedown", eventOptions));
    option.dispatchEvent(new MouseEvent("mouseup", eventOptions));
    option.click();
  }

  protected async optionSelectionCommitted(element: HTMLInputElement, values: string[], timeoutMs = 450): Promise<boolean> {
    const desired = values.map(normalizeQuestion);
    const committed = () => {
      if (this.selectedOption(element)) return true;
      return element.getAttribute("aria-expanded") === "false" && desired.includes(normalizeQuestion(this.currentValue(element)));
    };
    if (committed()) return true;
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      await new Promise((resolve) => window.setTimeout(resolve, 25));
      if (committed()) return true;
    }
    return false;
  }

  protected async fillControl(field: DetectedField, value: unknown, force = false, aliases: string[] = []): Promise<boolean> {
    if (value == null || value === "" || field.policy === "MANUAL_ONLY" || field.policy === "CONFIRM_REQUIRED") return false;
    const element = field.element;
    if (element instanceof HTMLInputElement && ["file", "password", "hidden"].includes(element.type)) return false;
    if (element instanceof HTMLInputElement && element.type === "radio") {
      if (typeof value !== "boolean") return false;
      const group = element.name
        ? [...document.querySelectorAll<HTMLInputElement>("input[type='radio']")].filter((item) => item.name === element.name)
        : [element];
      const desired = normalizeQuestion(value ? "Yes" : "No");
      const target = group.find((item) => {
        const label = elementLabel(item, this.config.containerSelector);
        return normalizeQuestion(label) === desired || normalizeQuestion(item.value) === desired;
      });
      if (!target) return false;
      if (!target.checked) target.click();
      return target.checked;
    }
    if (element instanceof HTMLInputElement && element.type === "checkbox") {
      if (typeof value !== "boolean") return false;
      if (element.checked !== value) element.click();
      return element.checked === value;
    }
    const existing = this.currentValue(element);
    if (existing && this.config.preserveSavedValues && !force) {
      if (this.acceptedPortalValues.has(field.normalizedKey)) return false;
      const conflict = comparePortalValue(existing, value, field.label);
      field.conflict = conflict;
      if (["POTENTIAL_CONFLICT", "CRITICAL_CONFLICT"].includes(conflict.classification)) this.conflictMemory.set(field.normalizedKey, conflict);
      if (["POTENTIAL_CONFLICT", "CRITICAL_CONFLICT"].includes(conflict.classification)) return false;
    }
    if (element instanceof HTMLSelectElement) {
      const desired = new Set([String(value), ...aliases, ...(typeof value === "boolean" ? [value ? "Yes" : "No"] : [])].map(normalizeQuestion));
      const option = [...element.options].find((item) => desired.has(normalizeQuestion(item.textContent || item.value)));
      if (!option) return false;
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set?.call(element, option.value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return element.value === option.value;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const rawExisting = element.value;
      if (aliases.some((alias) => normalizeQuestion(alias) === normalizeQuestion(existing))) return true;
      element.focus();
      element.click();
      nativeSetValue(element, String(value));
      if (element instanceof HTMLInputElement && element.getAttribute("role") === "combobox") {
        element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
        const optionScope = element.closest(this.config.containerSelector) || element.parentElement;
        const optionValues = aliases.length ? aliases : [String(value)];
        const option = await this.waitForExactOption(
          optionValues,
          1200,
          optionScope,
          /\bcountry\b/.test(normalizeQuestion(field.label))
        );
        if (!option) { nativeSetValue(element, rawExisting); return false; }
        this.activateOption(option);
        if (!(await this.optionSelectionCommitted(element, optionValues))) {
          element.focus();
          element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
          element.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        }
        if (!(await this.optionSelectionCommitted(element, optionValues))) {
          nativeSetValue(element, rawExisting);
          return false;
        }
      } else {
        // Controlled React/Vue inputs can restore their previous value after
        // the first event cycle. Verify the write and retry once through the
        // native setter so a reported fill always corresponds to a real value.
        await new Promise((resolve) => window.setTimeout(resolve, 0));
        if (element.value !== String(value)) {
          nativeSetValue(element, String(value));
          await new Promise((resolve) => window.setTimeout(resolve, 0));
        }
        if (element.value !== String(value)) return false;
      }
      return true;
    }
    return false;
  }

  protected async attachPreparedFiles(files: PreparedApplicationFile[]): Promise<number> {
    if (!files.length || typeof DataTransfer === "undefined") return 0;
    let attached = 0;
    for (const field of this.fields) {
      if (!(field.element instanceof HTMLInputElement) || field.element.type !== "file") continue;
      const label = normalizeQuestion(field.label);
      const kind: "RESUME" | "PORTFOLIO" | null = field.element.id === "resume" || /resume|curriculum|\bcv\b/.test(label)
        ? "RESUME"
        : /project portfolio|portfolio pdf|additional project materials|supporting documents/.test(label)
        ? "PORTFOLIO"
        : null;
      if (!kind) continue;
      const prepared = files.find((file) => file.kind === kind);
      if (!prepared || !prepared.filename.toLocaleLowerCase().endsWith(".pdf")) continue;
      try {
        // The local assistant uses Playwright's native file-input API. Treat
        // that browser-verified upload as attached instead of replacing it
        // through DataTransfer (which some employer frameworks ignore).
        if (field.element.files?.[0]?.name === prepared.filename) {
          this.attachedFiles.set(kind, { filename: prepared.filename, versionId: prepared.versionId });
          attached += 1;
          continue;
        }
        const binary = atob(prepared.base64);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        const transfer = new DataTransfer();
        transfer.items.add(new File([bytes], prepared.filename, { type: prepared.mimeType }));
        try {
          field.element.files = transfer.files;
        } catch {
          Object.defineProperty(field.element, "files", { configurable: true, value: transfer.files });
        }
        field.element.dispatchEvent(new Event("input", { bubbles: true }));
        field.element.dispatchEvent(new Event("change", { bubbles: true }));
        if (field.element.files?.[0]?.name !== prepared.filename) {
          this.failed += 1;
          continue;
        }
        this.attachedFiles.set(kind, { filename: prepared.filename, versionId: prepared.versionId });
        attached += 1;
      } catch {
        this.failed += 1;
      }
    }
    return attached;
  }

  protected async addItems(labelPattern: RegExp, items: string[], aliases: Record<string, string[]> = {}): Promise<number> {
    const field = this.fields.find((item) => labelPattern.test(normalizeQuestion(item.label)) && item.element instanceof HTMLInputElement);
    if (!field || !(field.element instanceof HTMLInputElement)) return 0;
    let added = 0;
    for (const rawItem of items) {
      const item = rawItem.split(/[\u2014\u2013|]/, 1)[0].trim();
      if (!item) continue;
      nativeSetValue(field.element, item);
      const option = await this.waitForExactOption([item, ...(aliases[item] || [])]);
      if (!option) { this.failed += 1; continue; }
      this.activateOption(option);
      const add = [...document.querySelectorAll<HTMLElement>("button, [role='button']")].find((button) => visible(button) && /^add$/i.test((button.textContent || "").trim()));
      add?.click();
      added += 1;
    }
    nativeSetValue(field.element, "");
    return added;
  }

  async fillThisPage(payload: ExtensionPayload, preparedFiles: PreparedApplicationFile[] = [], resolutions: AgentFieldResolution[] = []): Promise<{ filled: number; reviewed: number }> {
    // review() already captured the exact controls sent for analysis. Keep
    // those connected controls instead of assigning new IDs after an API
    // round-trip. Re-scan only if the portal actually replaced the form.
    if (!this.fields.length || this.fields.some((field) => !field.element.isConnected)) {
      this.detectFields(payload);
    }
    if (this.detectAssessment()) return { filled: 0, reviewed: 0 };
    let filled = 0;
    let reviewed = 0;
    const decisions = new Map(resolutions.map((resolution) => [resolution.field_id, resolution]));
    const decisionByIdentity = new Map<string, AgentFieldResolution>();
    for (const resolution of resolutions) {
      const identity = resolution.field_id.replace(/\|occurrence=\d+$/, "").replace(/:\d+$/, "");
      if (!decisionByIdentity.has(identity)) decisionByIdentity.set(identity, resolution);
    }
    const agentMode = resolutions.length > 0;
    for (const field of this.fields) {
      if (/\b(?:skills?|languages?)\b/.test(normalizeQuestion(field.label))) continue;
      const identity = field.fieldId.replace(/\|occurrence=\d+$/, "").replace(/:\d+$/, "");
      const decision = decisions.get(field.fieldId) || decisionByIdentity.get(identity);
      if (agentMode && (!decision || !["AUTO_FILL", "AUTO_FILL_REVIEW", "GENERATE_REVIEW"].includes(decision.action) || decision.confidence < 0.8)) continue;
      const value = agentMode ? (decision?.selected_option ?? decision?.selected_value) : canonicalValue(field, payload);
      const effectiveField = decision ? {
        ...field,
        normalizedKey: decision.canonical_field,
        policy: decision.requires_review ? "AUTO_FILL_REVIEW_REQUIRED" as const : "AUTO_FILL" as const,
        confidence: decision.confidence,
      } : field;
      const aliases = decision?.selected_option ? [decision.selected_option] : optionAliases(field, value, payload);
      if (!Array.isArray(value) && await this.fillControl(effectiveField, value, false, aliases)) {
        filled += 1;
        if (decision?.requires_review || ["REVIEW_RECOMMENDED", "AUTO_FILL_REVIEW_REQUIRED"].includes(effectiveField.policy)) reviewed += 1;
      } else if (value != null && value !== "" && effectiveField.policy !== "MANUAL_ONLY" && effectiveField.policy !== "CONFIRM_REQUIRED" && !effectiveField.conflict) {
        this.failed += 1;
      }
    }
    const verifiedSkills = payload.resume.selected_skills.filter((skill) => payload.profile.verified_skills.includes(skill));
    const decisionAllows = (pattern: RegExp) => !agentMode || this.fields.some((field) => {
      const decision = decisions.get(field.fieldId);
      return pattern.test(normalizeQuestion(field.label)) && Boolean(decision && ["AUTO_FILL", "AUTO_FILL_REVIEW", "GENERATE_REVIEW"].includes(decision.action) && decision.confidence >= 0.8);
    });
    if (this.config.structuredSkills && decisionAllows(/\bskills?\b/)) filled += await this.addItems(/\bskills?\b/, verifiedSkills, skillAliases);
    if (this.config.structuredLanguages && decisionAllows(/\blanguages?\b/)) filled += await this.addItems(/\blanguages?\b/, payload.profile.languages);
    filled += await this.attachPreparedFiles(preparedFiles);
    this.filled += filled;
    return { filled, reviewed };
  }

  async fillReviewedText(fieldId: string, answer: string): Promise<boolean> {
    const field = this.fields.find((item) => item.fieldId === fieldId && item.element.isConnected);
    if (!field || !answer.trim()) return false;
    const element = field.element;
    if (!(element instanceof HTMLTextAreaElement)
      && !(element instanceof HTMLInputElement && element.type === "text")) return false;
    if (element.maxLength > 0 && answer.length > element.maxLength) {
      throw new Error(`This answer exceeds the ${element.maxLength} character limit.`);
    }
    return this.fillControl({ ...field, policy: "AUTO_FILL_REVIEW_REQUIRED" }, answer, true);
  }

  async fillConfirmedAnswer(questionKey: string, answer: unknown): Promise<boolean> {
    const field = this.fields.find((item) => item.normalizedKey === questionKey && item.policy === "CONFIRM_REQUIRED");
    if (!field) return false;
    const element = field.element;
    if (element instanceof HTMLSelectElement) {
      const desired = normalizeQuestion(String(answer));
      const option = [...element.options].find((item) => normalizeQuestion(item.textContent || item.value) === desired);
      if (!option) return false;
      element.value = option.value;
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    const container = element.closest(this.config.containerSelector) || element.parentElement;
    const desired = normalizeQuestion(String(answer));
    const controls = [...(container?.querySelectorAll<HTMLInputElement>("input[type='radio'], input[type='checkbox']") || [])];
    const control = controls.find((input) => normalizeQuestion(elementLabel(input, this.config.containerSelector)).includes(desired) || normalizeQuestion(input.value) === desired);
    if (control) { control.click(); return true; }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) { nativeSetValue(element, String(answer)); return true; }
    return false;
  }

  async resolveFieldConflict(normalizedKey: string, useVerified: boolean, payload: ExtensionPayload): Promise<boolean> {
    const field = this.fields.find((item) => item.normalizedKey === normalizedKey && item.conflict);
    if (!field) return false;
    if (!useVerified) {
      field.conflict = undefined;
      this.conflictMemory.delete(normalizedKey);
      this.acceptedPortalValues.add(normalizedKey);
      return true;
    }
    const value = canonicalValue(field, payload);
    const filled = await this.fillControl(field, value, true);
    if (filled) {
      field.conflict = undefined;
      this.conflictMemory.delete(normalizedKey);
      this.acceptedPortalValues.delete(normalizedKey);
    }
    return filled;
  }

  protected pendingQuestions(payload: ExtensionPayload): PendingQuestion[] {
    const suggestionMap = new Map(payload.answer_suggestions.map((item) => [item.question_key, item]));
    return this.fields.filter((field) => field.policy === "CONFIRM_REQUIRED").map((field) => {
      const suggestion = suggestionMap.get(field.normalizedKey);
      return { questionKey: field.normalizedKey, question: field.label, confidence: field.confidence, policy: field.policy, suggestedAnswer: suggestion?.answer_json.value, previouslyConfirmedAt: suggestion?.last_confirmed_at };
    });
  }

  detectAssessment(): AssessmentType {
    const text = [...document.querySelectorAll<HTMLElement>("h1, h2, h3, [role='heading'], main p, button")]
      .filter(visible).map((item) => item.textContent || "").join(" ").slice(0, 12000);
    return detectAssessmentText(text);
  }

  isReviewPage(): boolean {
    const headings = normalizeQuestion([...document.querySelectorAll("h1, h2, [role='heading']")].map((item) => item.textContent || "").join(" "));
    const hasFinal = [...document.querySelectorAll<HTMLElement>("button, [role='button'], input[type='submit']")]
      .some((button) => visible(button) && isFinalSubmitText(button instanceof HTMLInputElement ? button.value : button.textContent || ""));
    return hasFinal && /review|application summary|review your application/.test(headings);
  }

  detectConfirmation(): { confirmed: boolean; text: string } {
    const text = [...document.querySelectorAll<HTMLElement>("h1, h2, [role='heading'], [role='alert'], main p")]
      .filter(visible).map((item) => (item.textContent || "").trim()).filter(Boolean).join(" ");
    const normalized = normalizeQuestion(text);
    const confirmed = ["application submitted", "thank you for applying", "application has been received", "application received", "thanks for applying", "thank you for your application"].some((phrase) => normalized.includes(phrase));
    return { confirmed, text: confirmed ? text.slice(0, 1000) : "" };
  }

  observedValues(): Record<string, unknown> {
    const observed: Record<string, unknown> = {};
    const languages: string[] = [];
    const skills: string[] = [];
    const authorizationAnswers: Record<string, string[]> = {};
    for (const field of this.fields) {
      const label = normalizeQuestion(field.label);
      const element = field.element as FormControl;
      const value = this.currentValue(field.element);
      if (/email/.test(label)) observed.email = value;
      if (/current location|location city|^location(?: |$)/.test(label)) observed.current_location = value;
      if (/^city(?: |$)/.test(label)) observed.city = value;
      if (/gpa|grade point/.test(label)) observed.gpa = value;
      if (/degree status|education status/.test(label)) observed.degree_status = value;
      if (/graduation|expected completion/.test(label)) observed.graduation_date = value;
      if (/education start|start year/.test(label)) observed.education_start_year = value;
      if (/end date year|education end year|graduation year/.test(label)) observed.education_end_year = value;
      if (/end date month|graduation month/.test(label)) observed.education_end_month = value;
      if (/address line 1|address 1|street/.test(label)) observed.address_line1 = value;
      if (/address line 2|address 2/.test(label)) observed.address_line2 = value;
      if (/language/.test(label) && value) languages.push(value);
      if (/\bskills?\b/.test(label) && value) skills.push(value);
      if (field.normalizedKey === "JOB_DISCOVERY_SOURCE" && value) observed.job_discovery_source = value;
      if (field.normalizedKey === "FULL_TIME_SUMMER_AVAILABILITY" && value) observed.full_time_summer_availability = value;
      if (field.normalizedKey === "SPRING_SUMMER_COMBINED_AVAILABILITY" && value) observed.spring_summer_combined_availability = value;
      if (["US_WORK_AUTHORIZATION", "US_SPONSORSHIP_REQUIRED", "MEXICO_WORK_AUTHORIZATION", "WORK_AUTHORIZATION_CURRENT_COUNTRY"].includes(field.normalizedKey) && value) {
        if (element instanceof HTMLInputElement && ["radio", "checkbox"].includes(element.type) && !element.checked) continue;
        (authorizationAnswers[field.normalizedKey] ||= []).push(value);
      }
    }
    if (languages.length) observed.languages = languages;
    if (skills.length) observed.skills = skills;
    if (Object.keys(authorizationAnswers).length) observed.work_authorization_answers = authorizationAnswers;
    const resume = this.attachedFiles.get("RESUME");
    const portfolio = this.attachedFiles.get("PORTFOLIO");
    if (resume) {
      observed.resume_version_id = resume.versionId;
      observed.uploaded_resume_filename = resume.filename;
    }
    if (portfolio) {
      observed.portfolio_version_id = portfolio.versionId;
      observed.uploaded_portfolio_filename = portfolio.filename;
    }
    observed.required_missing_fields = this.requiredMissingFields();
    return observed;
  }

  protected requiredMissingFields(): string[] {
    const missing = new Set<string>();
    for (const field of this.fields) {
      const element = field.element;
      const required = element.hasAttribute("required") || element.getAttribute("aria-required") === "true" || element.closest("[aria-required='true']") != null;
      if (!required) continue;
      if (element instanceof HTMLInputElement && element.type === "checkbox") {
        const group = element.name
          ? [...document.querySelectorAll<HTMLInputElement>("input[type='checkbox']")].filter((input) => input.name === element.name)
          : [element];
        if (!group.some((input) => input.checked)) missing.add(field.label);
        continue;
      }
      if (!this.currentValue(element).trim()) missing.add(field.label);
    }
    return [...missing];
  }

  protected legalReview(payload: ExtensionPayload): Array<{ key: string; label: string; value: string; source: string }> {
    const auth = payload.profile.work_authorization;
    const preferences = payload.profile.application_preferences;
    const yesNo = (value: boolean) => value ? "Yes" : "No";
    const jobCountry = resolvedJobCountry(payload);
    const isUnitedStates = /united states|\bus\b|\bu s\b/i.test(jobCountry);
    const authorizedInJobCountry = isUnitedStates
      ? auth.us_work_authorized
      : auth.work_authorized_countries.some((country) => normalizeQuestion(country) === normalizeQuestion(jobCountry));
    const sponsorshipRequired = isUnitedStates ? auth.requires_us_employment_sponsorship : !authorizedInJobCountry;
    const countryLabel = isUnitedStates ? "U.S." : jobCountry || "Current-country";
    return [
      { key: "CURRENT_LOCATION", label: "Current location", value: payload.profile.contact.current_location || [payload.profile.contact.city, payload.profile.contact.state, payload.profile.contact.country].filter(Boolean).join(", "), source: "Verified candidate profile" },
      { key: "WORK_AUTHORIZATION", label: `${countryLabel} work authorized`, value: yesNo(authorizedInJobCountry), source: "Previously confirmed candidate profile" },
      { key: "SPONSORSHIP_REQUIRED", label: `${countryLabel} sponsorship required`, value: yesNo(sponsorshipRequired), source: "Previously confirmed candidate profile" },
      { key: "CITIZENSHIP", label: "Citizenship", value: auth.citizenship_country, source: "Verified candidate profile" },
      { key: "FULL_TIME_SUMMER_AVAILABILITY", label: "Summer full-time availability", value: yesNo(preferences.full_time_summer_availability), source: preferences.answer_source },
      { key: "SPRING_SUMMER_COMBINED_AVAILABILITY", label: "Spring + Summer availability", value: yesNo(preferences.spring_summer_combined_availability), source: preferences.answer_source },
      { key: "JOB_DISCOVERY_SOURCE", label: "Source", value: preferences.job_discovery_source === "GOOGLE_SEARCH" ? "Google Search" : preferences.job_discovery_source, source: preferences.answer_source },
    ];
  }

  protected applicationChecks(payload: ExtensionPayload, issues: ConsistencyIssue[]): Array<{ key: string; label: string; ready: boolean; blocking: boolean }> {
    const fieldFor = (predicate: (field: DetectedField) => boolean) => this.fields.find(predicate);
    const valueFor = (predicate: (field: DetectedField) => boolean) => {
      const field = fieldFor(predicate);
      return field ? this.currentValue(field.element) : "";
    };
    const normalizedLabel = (field: DetectedField) => normalizeQuestion(field.label);
    const location = valueFor((field) => /current location|location city|^location(?: |$)/.test(normalizedLabel(field)));
    const endYear = valueFor((field) => /end date year|education end year|graduation year/.test(normalizedLabel(field)));
    const source = valueFor((field) => field.normalizedKey === "JOB_DISCOVERY_SOURCE");
    const summer = valueFor((field) => field.normalizedKey === "FULL_TIME_SUMMER_AVAILABILITY");
    const combined = valueFor((field) => field.normalizedKey === "SPRING_SUMMER_COMBINED_AVAILABILITY");
    const resumeField = fieldFor((field) => field.element instanceof HTMLInputElement && field.element.type === "file" && (field.element.id === "resume" || /resume|\bcv\b/.test(normalizedLabel(field))));
    const portfolioField = fieldFor((field) => field.element instanceof HTMLInputElement && field.element.type === "file" && /portfolio|project materials|supporting documents/.test(normalizedLabel(field)));
    const authorizationFields = this.fields.filter((field) => ["US_WORK_AUTHORIZATION", "MEXICO_WORK_AUTHORIZATION", "WORK_AUTHORIZATION_CURRENT_COUNTRY"].includes(field.normalizedKey));
    const sponsorshipFields = this.fields.filter((field) => ["US_SPONSORSHIP_REQUIRED", "SPONSORSHIP_CURRENT_COUNTRY"].includes(field.normalizedKey));
    const requiredMissing = this.requiredMissingFields();
    const resume = this.attachedFiles.get("RESUME");
    const portfolio = this.attachedFiles.get("PORTFOLIO");
    return [
      { key: "LOCATION", label: "Location", ready: Boolean(location), blocking: Boolean(fieldFor((field) => /current location|location city|^location(?: |$)/.test(normalizedLabel(field)))) },
      { key: "RESUME", label: "Recommended Resume", ready: !resumeField || Boolean(resume && resume.filename === payload.session.resume_filename && resume.versionId === payload.session.resume_version_id), blocking: Boolean(resumeField) },
      { key: "PORTFOLIO", label: "Project Portfolio", ready: !payload.portfolio || !portfolioField || Boolean(portfolio && portfolio.filename === payload.portfolio.filename && portfolio.versionId === payload.portfolio.id), blocking: Boolean(payload.portfolio && portfolioField) },
      { key: "EDUCATION_END_DATE", label: "Education End Date", ready: Boolean(endYear), blocking: Boolean(fieldFor((field) => /end date year|education end year|graduation year/.test(normalizedLabel(field)))) },
      { key: "SOURCE", label: "How Did You Hear", ready: Boolean(source), blocking: Boolean(fieldFor((field) => field.normalizedKey === "JOB_DISCOVERY_SOURCE")) },
      { key: "SUMMER_AVAILABILITY", label: "Summer Availability", ready: Boolean(summer), blocking: Boolean(fieldFor((field) => field.normalizedKey === "FULL_TIME_SUMMER_AVAILABILITY")) },
      { key: "COMBINED_AVAILABILITY", label: "Spring + Summer Availability", ready: Boolean(combined), blocking: Boolean(fieldFor((field) => field.normalizedKey === "SPRING_SUMMER_COMBINED_AVAILABILITY")) },
      { key: "WORK_AUTHORIZATION", label: "Work Authorization", ready: !authorizationFields.length || authorizationFields.some((field) => Boolean(this.currentValue(field.element))), blocking: Boolean(authorizationFields.length) },
      { key: "SPONSORSHIP", label: "Sponsorship", ready: !sponsorshipFields.length || sponsorshipFields.some((field) => Boolean(this.currentValue(field.element))), blocking: Boolean(sponsorshipFields.length) },
      { key: "EXPERIENCE", label: "Job-specific Experience", ready: Boolean((payload.session.project_experience_json || payload.session.selected_projects_json).length), blocking: true },
      { key: "SKILLS", label: "Job-specific Skills", ready: payload.resume.selected_skills.every((skill) => payload.profile.verified_skills.includes(skill)), blocking: true },
      { key: "REQUIRED_FIELDS", label: "Required Fields", ready: requiredMissing.length === 0, blocking: true },
      { key: "CONSISTENCY", label: "Consistency Check", ready: issues.length === 0, blocking: true },
    ];
  }

  protected stage(): ApplicationStage {
    const text = normalizeQuestion([...document.querySelectorAll("h1, h2, [role='heading']")].map((item) => item.textContent || "").join(" "));
    if (this.detectConfirmation().confirmed) return "CONFIRMATION";
    if (this.isReviewPage()) return "REVIEW";
    if (/voluntary|demographic|diversity/.test(text)) return "VOLUNTARY";
    if (/legal|compliance|authorization|sponsorship/.test(text)) return "LEGAL";
    if (/question/.test(text)) return "QUESTIONS";
    if (/skill/.test(text)) return "SKILLS";
    if (/education/.test(text)) return "EDUCATION";
    if (/experience/.test(text)) return "EXPERIENCE";
    if (/resume|document/.test(text)) return "RESUME";
    if (/contact|information|profile/.test(text)) return "CONTACT";
    return "PROFILE";
  }

  diagnostics(): AdapterDiagnostics {
    const unknown = this.fields.filter((field) => field.normalizedKey === "UNKNOWN").length;
    const expectedFingerprint = this.config.fingerprintSelectors.length === 0 || this.detectionEvidence.length > 0;
    return {
      adapterVersion: this.adapterVersion,
      lastSuccessfulDetection: expectedFingerprint && this.fields.length ? new Date().toISOString() : null,
      fieldsDetected: this.fields.length, fieldsFilled: this.filled, fieldsFailed: this.failed, unknownFields: unknown,
      confidence: expectedFingerprint ? (this.fields.length ? 0.95 : 0.65) : 0.35,
      evidence: [...this.detectionEvidence]
    };
  }

  review(payload: ExtensionPayload): AssistantPageState {
    this.detectFields(payload);
    const confirmation = this.detectConfirmation();
    const assessment = this.detectAssessment();
    const diagnostics = this.diagnostics();
    const observed = {
      ...this.observedValues(),
      expected_resume_filename: payload.session.resume_filename,
    };
    const issues = validateConsistency(payload.profile, observed, payload.resume.id);
    for (const field of this.fields.filter((item) => item.conflict && ["POTENTIAL_CONFLICT", "CRITICAL_CONFLICT"].includes(item.conflict.classification))) {
      issues.push({ code: `PORTAL_${field.conflict!.classification}`, field: field.normalizedKey, message: `Saved portal value differs for ${field.label}. Keep it or replace it manually after review.`, observed: field.conflict!.portalValue, expected: field.conflict!.verifiedValue });
    }
    const metadata = this.detectPortalMetadata();
    const headings = [...document.querySelectorAll("h1, h2, [role='heading']")].map((item) => (item.textContent || "").trim()).filter(Boolean);
    const completedSafe = this.fields.filter((field) => ["AUTO_FILL", "AUTO_FILL_REVIEW_REQUIRED"].includes(field.policy) && Boolean(this.currentValue(field.element))).length;
    const portalChanged = this.config.fingerprintSelectors.length > 0 && diagnostics.confidence < 0.5;
    const pendingQuestions = this.pendingQuestions(payload);
    const applicationChecks = this.applicationChecks(payload, issues);
    const finalActionVisible = [...document.querySelectorAll<HTMLElement>("button, [role='button'], input[type='submit']")]
      .some((button) => visible(button) && isFinalSubmitText(button instanceof HTMLInputElement ? button.value : button.textContent || ""));
    const readyForSinglePageReview = this.portalType === "GREENHOUSE"
      && finalActionVisible
      && pendingQuestions.length === 0
      && this.fields
        .filter((field) => ["AUTO_FILL", "AUTO_FILL_REVIEW_REQUIRED"].includes(field.policy))
        .filter((field) => !(field.element instanceof HTMLInputElement && field.element.type === "file"))
        .every((field) => {
          const expected = canonicalValue(field, payload);
          if (expected === undefined || expected === null || expected === "") return true;
          if (field.element instanceof HTMLInputElement && ["checkbox", "radio"].includes(field.element.type) && typeof expected === "boolean") {
            return field.element.checked === expected;
          }
          return Boolean(this.currentValue(field.element));
        })
      && applicationChecks.filter((check) => check.blocking).every((check) => check.ready);
    const reviewPage = this.isReviewPage() || readyForSinglePageReview;
    return {
      connected: true, lastActionMessage: "", paused: Boolean(assessment) || portalChanged, portal: this.portalType,
      supportStatus: portalChanged ? "PORTAL_CHANGED" : this.supportStatus,
      company: payload.session.company, jobTitle: metadata.jobTitle || payload.resume.target_role,
      currentSection: headings[0] || `${this.config.pageName} application`,
      progress: this.fields.length ? Math.min(95, Math.round(completedSafe / this.fields.length * 100)) : 0,
      fields: this.fields.map((field) => ({ fieldId: field.fieldId, label: field.label, nearbyText: field.nearbyText, controlType: field.controlType, availableOptions: field.availableOptions, currentValue: this.currentValue(field.element), required: field.required, maxlength: field.maxlength, normalizedKey: field.normalizedKey, policy: field.policy, confidence: field.confidence, value: this.currentValue(field.element), answerSource: field.answerSource, conflict: field.conflict })), pendingQuestions,
      consistencyIssues: issues, isReviewPage: reviewPage, isConfirmationPage: confirmation.confirmed,
      confirmationText: confirmation.text, assessmentType: assessment,
      safeAutofillPausedReason: assessment ? "Assessment detected. Complete this section manually." : portalChanged ? "This application portal may have changed. Safe autofill paused." : "",
      stage: reviewPage ? "REVIEW" : this.stage(), adapterDiagnostics: diagnostics, resume: payload.resume, portfolio: payload.portfolio,
      legalReview: this.legalReview(payload), applicationChecks,
      counts: { filled: completedSafe, reviewed: 0, confirmed: 0 }, agentDecisions: [], aiMode: payload.ai_settings.ai_mode, debugEnabled: false
    };
  }

  async continuePage(pendingConfirmationCount: number): Promise<boolean> {
    if (pendingConfirmationCount > 0 || this.isReviewPage() || this.detectAssessment()) return false;
    const button = [...document.querySelectorAll<HTMLElement>("button, [role='button'], input[type='button'], input[type='submit']")]
      .find((item) => visible(item) && /^(?:save and continue|continue|next|save)$/i.test((item instanceof HTMLInputElement ? item.value : item.textContent || "").trim()));
    if (!button) return false;
    const text = button instanceof HTMLInputElement ? button.value : button.textContent || "";
    if (isFinalSubmitText(text)) return false;
    button.click();
    return true;
  }

  observe(onChange: () => void): () => void {
    let timer = 0;
    const observer = new MutationObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(onChange, 120);
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-expanded", "disabled", "value"] });
    return () => { observer.disconnect(); window.clearTimeout(timer); };
  }
}
