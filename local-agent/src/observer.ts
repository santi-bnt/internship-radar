import type { Page } from "playwright";
import { createHash } from "node:crypto";
import type { AssistantPageState, ExtensionPayload } from "../../extension/src/shared/types";
import { validatePortalUrl } from "./security";
import { detectAssessmentText } from "../../extension/src/shared/policies";

type Field = AssistantPageState["fields"][number];
export type PageObservation = {
  url: string; title: string; fields: Field[]; framesScanned: number; unreadableFrames: number;
  assessmentType: AssistantPageState["assessmentType"];
};

/** Read labels and options only. Candidate data and existing answers never enter this script. */
export async function observeApplicationPage(page: Page): Promise<PageObservation> {
  const url = page.url();
  await validatePortalUrl(url);
  const observation: PageObservation = { url, title: await page.title(), fields: [], framesScanned: 0, unreadableFrames: 0, assessmentType: "" };
  const frames = page.frames().slice(0, 20);
  for (const [frameIndex, frame] of frames.entries()) {
    try {
      if (frame !== page.mainFrame()) {
        if (!(await (await frame.frameElement()).isVisible())) continue;
        if (/captcha|recaptcha|hcaptcha|challenges\.cloudflare/i.test(frame.url())) continue;
        if (!/^(about:blank|about:srcdoc)$/.test(frame.url())) await validatePortalUrl(frame.url());
      }
      observation.assessmentType ||= detectAssessmentText(await frame.title());
      const fields = await frame.locator("input, textarea, select, [role='combobox'], [role='textbox'], [contenteditable='true']").evaluateAll((elements) => {
        function text(element: Element | null): string {
          if (!element) return "";
          const copy = element.cloneNode(true) as Element;
          copy.querySelectorAll("input, textarea, select, [contenteditable], script, style").forEach((node) => node.remove());
          return (copy.textContent || "").replace(/\s+/g, " ").trim();
        }
        const results = [];
        const occurrences = new Map<string, number>();
        for (const element of elements.slice(0, 600)) {
          const input = element as HTMLInputElement;
          const type = input.type || element.getAttribute("role") || element.tagName.toLowerCase();
          const identity = `${input.id || ""} ${input.name || ""} ${input.autocomplete || ""}`;
          if (["hidden", "password", "submit", "button", "reset", "image"].includes(type)
            || /password|one-time-code|csrf|authenticity.token|captcha/i.test(identity)
            || /(?:^|[\s_-])(?:otp|token)(?:$|[\s_-])/i.test(identity)
            || element.hasAttribute("disabled") || element.closest("[aria-hidden='true'], [hidden]")) continue;
          if (type !== "file" && (!(element as HTMLElement).getClientRects().length || getComputedStyle(element).visibility === "hidden")) continue;
          const root = element.getRootNode() as Document | ShadowRoot;
          const byIds = (element.getAttribute("aria-labelledby") || "").split(/\s+/)
            .map((id) => text(root.getElementById(id))).join(" ").trim();
          const labels = [...(input.labels || [])].map(text).join(" ");
          const container = element.closest(".field, .form-group, [class*='field'], [class*='question'], fieldset, [role='group']");
          const heading = container?.querySelector("legend, label, [class*='label']") || null;
          const label = (element.getAttribute("aria-label") || byIds || labels || text(heading)
            || input.placeholder || input.name || input.id || "Unknown field").trim().slice(0, 2000);
          const key = `${input.id || input.name || element.tagName}|${label}`;
          const occurrence = occurrences.get(key) || 0;
          occurrences.set(key, occurrence + 1);
          const context = container ? [...container.querySelectorAll("legend, label, [class*='label'], [class*='description'], [class*='help']")]
            .slice(0, 10).map(text).join(" ") : label;
          const options = element instanceof HTMLSelectElement
            ? [...element.options].map((option) => (option.textContent || "").trim()).filter(Boolean).slice(0, 150)
            : [];
          results.push({ key, occurrence, label, nearbyText: context.slice(0, 3000),
            filename: type === "file" ? input.files?.[0]?.name || "" : "",
            controlType: element instanceof HTMLTextAreaElement || element.getAttribute("role") === "textbox" || element.hasAttribute("contenteditable") ? "textarea" : type,
            availableOptions: options, required: input.required || element.getAttribute("aria-required") === "true",
            maxlength: input.maxLength > 0 ? input.maxLength : undefined });
        }
        return results;
      });
      observation.framesScanned += 1;
      for (const field of fields) {
        if (observation.fields.length >= 250) break;
        observation.fields.push({
          fieldId: `read:${frameIndex}:${createHash("sha256").update(frame.url()).digest("hex").slice(0, 12)}:${field.occurrence}:${field.key}`.slice(0, 240),
          label: field.label, nearbyText: field.nearbyText, controlType: field.controlType,
          availableOptions: field.availableOptions, required: field.required, maxlength: field.maxlength,
          currentValue: field.filename, normalizedKey: "UNKNOWN", policy: "MANUAL_ONLY", confidence: 0.5,
        });
      }
    } catch { observation.unreadableFrames += 1; }
  }
  return observation;
}

export function readOnlyPageState(payload: ExtensionPayload, observation: PageObservation, reason: string): AssistantPageState {
  return {
    connected: true, applicationSessionId: payload.session.id, applicationPageUrl: observation.url,
    lastActionMessage: reason, paused: false, portal: "GENERIC", supportStatus: "BETA",
    company: payload.session.company, jobTitle: payload.resume.target_role,
    currentSection: observation.title || "Application", progress: 0, fields: observation.fields,
    pendingQuestions: [], consistencyIssues: [], isReviewPage: false, isConfirmationPage: false,
    confirmationText: "", assessmentType: observation.assessmentType, safeAutofillPausedReason: reason, stage: "QUESTIONS",
    adapterDiagnostics: { adapterVersion: "local-observer-1", lastSuccessfulDetection: new Date().toISOString(),
      fieldsDetected: observation.fields.length, fieldsFilled: 0, fieldsFailed: 0,
      unknownFields: observation.fields.length, confidence: observation.fields.length ? 0.6 : 0,
      evidence: ["Read-only browser labels, options, iframe and open shadow DOM inspection"] },
    resume: payload.resume, portfolio: payload.portfolio, legalReview: [], applicationChecks: [],
    counts: { filled: 0, reviewed: 0, confirmed: 0 }, agentDecisions: [], aiMode: payload.ai_settings.ai_mode, debugEnabled: false,
  };
}
