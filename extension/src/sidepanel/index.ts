import type { RuntimeMessage } from "../shared/messages";
import { portalPermissionOrigins } from "../shared/portalNavigation";
import type { AssistantPageState } from "../shared/types";
import { ApplicationQuestions } from "./applicationQuestions";

const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
let state: AssistantPageState | null = null;
let currentTabId: number | null = null;
let currentTabUrl = "";
const requestedTabId = Number(new URLSearchParams(window.location.search).get("tabId"));
const applicationQuestions = new ApplicationQuestions(byId("application-questions"), action);

async function applicationTab(): Promise<number> {
  if (Number.isInteger(requestedTabId) && requestedTabId > 0) {
    const requestedTab = await chrome.tabs.get(requestedTabId);
    if (!requestedTab.url?.startsWith("https://")) throw new Error("Open the connected HTTPS career application tab.");
    currentTabId = requestedTabId;
    currentTabUrl = requestedTab.url;
    return requestedTabId;
  }
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id || !tab.url?.startsWith("https://")) throw new Error("Open the connected HTTPS career application tab.");
  currentTabId = tab.id;
  currentTabUrl = tab.url;
  return tab.id;
}

async function tabMessage<T>(message: RuntimeMessage): Promise<T> {
  const tabId = currentTabId ?? await applicationTab();
  const response = await chrome.tabs.sendMessage(tabId, message);
  if (!response?.ok) throw new Error(response?.error || "Apply Assistant action failed.");
  return response.data as T;
}

function text(id: string, value: string): void { byId(id).textContent = value; }
function hidden(id: string, value: boolean): void { byId(id).hidden = value; }

function render(next: AssistantPageState): void {
  state = next;
  const status = byId("status");
  status.classList.remove("error");
  text("status", next.connected
    ? (next.paused ? "Assistant paused. You can continue manually." : next.lastActionMessage || `Connected securely to ${next.portal.replaceAll("_", " ")}.`)
    : "No Application Session connected.");
  hidden("enable-card", true);
  hidden("job", !next.connected);
  hidden("section-card", !next.connected);
  hidden("agent-status-card", !next.connected);
  hidden("application-questions-card", !next.connected);
  applicationQuestions.render(next, currentTabUrl);
  if (!next.connected) return;
  byId<HTMLButtonElement>("read-questions").disabled = next.paused || next.isReviewPage || Boolean(next.assessmentType);
  text("job-title", next.jobTitle);
  text("company", next.company);
  text("portal", `${next.portal.replaceAll("_", " ")} · ${next.supportStatus}`);
  byId("progress-bar").style.width = `${next.progress}%`;
  text("progress-label", `${next.progress}% assisted completion`);
  text("current-section", `${next.stage} · ${next.currentSection}`);
  text("counts", `${next.counts.filled} filled · ${next.counts.reviewed} reviewed · ${next.counts.confirmed} confirmed`);
  text("privacy-mode", next.aiMode === "LOCAL_ONLY" ? "Maximum privacy" : next.aiMode === "EXTERNAL_ALLOWED" ? "Best quality" : "Balanced privacy");
  const checkByKey = new Map(next.applicationChecks.map((check) => [check.key, check.ready]));
  const agentChecks = [
    ["Profile loaded", true],
    ["Job understood", Boolean(next.jobTitle)],
    ["Resume selected", Boolean(next.resume)],
    ["Experience selected", checkByKey.get("EXPERIENCE") === true],
    ["Skills selected", checkByKey.get("SKILLS") === true],
  ] as const;
  byId<HTMLUListElement>("agent-checks").replaceChildren(...agentChecks.map(([label, ready]) => {
    const item = document.createElement("li");
    item.className = ready ? "ready" : "";
    item.textContent = `${ready ? "✓" : "○"} ${label}`;
    return item;
  }));
  const agentDecision = next.agentDecisions.find((decision) => decision.requires_review) || next.agentDecisions[0];
  hidden("agent-decision-card", !agentDecision);
  if (agentDecision) {
    text("agent-decision-field", agentDecision.canonical_field.replaceAll("_", " "));
    const chosen = agentDecision.selected_option ?? agentDecision.selected_value;
    text("agent-decision-value", chosen == null || chosen === "" ? "No verified value selected." : Array.isArray(chosen) ? chosen.join(", ") : String(chosen));
    text("agent-decision-reason", agentDecision.reason_summary);
    text("agent-decision-meta", `${Math.round(agentDecision.confidence * 100)}% confidence · ${agentDecision.match_type.replaceAll("_", " ")} · ${agentDecision.execution_location.toLowerCase()}`);
    byId("use-agent-decision").dataset.fieldId = agentDecision.field_id;
    byId<HTMLButtonElement>("use-agent-decision").disabled = !agentDecision.selected_option;
  }
  const pending = next.pendingQuestions[0];
  hidden("question-card", !pending);
  if (pending) {
    text("question", pending.question);
    const answer = byId<HTMLInputElement>("answer");
    answer.value = pending.suggestedAnswer == null ? "" : String(pending.suggestedAnswer);
    text("previous-confirmation", pending.previouslyConfirmedAt ? `Previously confirmed ${new Date(pending.previouslyConfirmedAt).toLocaleDateString()}. Confirm again for this application.` : "No prior confirmed answer. Review and enter the answer yourself.");
    byId("confirm-answer").dataset.questionKey = pending.questionKey;
  }
  hidden("manual-card", !next.safeAutofillPausedReason);
  text("manual-reason", next.safeAutofillPausedReason);
  hidden("review-card", !next.isReviewPage);
  text("review-summary", `${next.counts.filled} fields filled, ${next.counts.reviewed} reviewed, ${next.counts.confirmed} manually confirmed.`);
  byId<HTMLUListElement>("agent-review-items").replaceChildren(...next.agentDecisions.map((decision) => {
    const item = document.createElement("li");
    const value = decision.selected_option ?? decision.selected_value;
    item.textContent = `${decision.action === "MANUAL_ONLY" || decision.action === "CONFIRM" ? "⚠" : "✓"} ${decision.canonical_field.replaceAll("_", " ")}${value == null || value === "" ? "" : `: ${Array.isArray(value) ? value.join(", ") : String(value)}`}`;
    return item;
  }));
  hidden("legal-review-card", next.legalReview.length === 0);
  const legalReview = byId<HTMLDListElement>("legal-review");
  legalReview.replaceChildren(...next.legalReview.flatMap((answer) => {
    const term = document.createElement("dt");
    term.textContent = answer.label;
    term.title = answer.source;
    const value = document.createElement("dd");
    value.textContent = answer.value;
    value.title = `Source: ${answer.source}`;
    return [term, value];
  }));
  hidden("application-check-card", next.applicationChecks.length === 0);
  const checks = byId<HTMLUListElement>("application-checks");
  checks.replaceChildren(...next.applicationChecks.map((check) => {
    const item = document.createElement("li");
    item.className = check.ready ? "ready" : check.blocking ? "blocking" : "";
    item.textContent = `${check.ready ? "✓" : check.blocking ? "✕" : "○"} ${check.label}`;
    return item;
  }));
  const blockingCount = next.applicationChecks.filter((check) => check.blocking && !check.ready).length;
  text("blocking-count", blockingCount ? `${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"}` : "0 blocking issues — ready for final review.");
  hidden("confirmation-card", !next.isConfirmationPage);
  const conflictField = next.fields.find((field) => field.conflict && ["POTENTIAL_CONFLICT", "CRITICAL_CONFLICT"].includes(field.conflict.classification));
  hidden("conflict-card", !conflictField);
  if (conflictField?.conflict) {
    text("conflict-label", conflictField.label);
    text("portal-value", conflictField.conflict.portalValue);
    text("verified-value", conflictField.conflict.verifiedValue);
    byId("keep-portal").dataset.normalizedKey = conflictField.normalizedKey;
    byId("use-verified").dataset.normalizedKey = conflictField.normalizedKey;
  }
  hidden("issues-card", next.consistencyIssues.length === 0);
  const issues = byId<HTMLUListElement>("issues");
  issues.replaceChildren(...next.consistencyIssues.map((issue) => {
    const item = document.createElement("li");
    item.textContent = `${issue.message}${issue.observed != null ? ` Portal: ${String(issue.observed)}.` : ""}${issue.expected != null ? ` Verified: ${String(issue.expected)}.` : ""}`;
    return item;
  }));
  hidden("resume-card", !next.resume);
  if (next.resume) text("resume-name", `Recommended Resume v${next.resume.version} — ${next.resume.target_role}`);
  if (next.resume?.filename) text("resume-name", next.resume.filename);
  hidden("portfolio-card", !next.portfolio);
  if (next.portfolio) text("portfolio-name", next.portfolio.filename);
  byId<HTMLButtonElement>("fill").disabled = next.paused || next.isReviewPage || Boolean(next.assessmentType);
  byId<HTMLButtonElement>("ai-fill").disabled = next.paused || next.isReviewPage || Boolean(next.assessmentType);
  byId<HTMLButtonElement>("autopilot").disabled = next.paused || next.isReviewPage || Boolean(next.assessmentType);
  byId<HTMLButtonElement>("continue").disabled = next.paused || next.pendingQuestions.length > 0 || next.isReviewPage || Boolean(next.assessmentType);
  text("pause", next.paused ? "Resume Assistant" : "Pause Assistant");
  hidden("debug", !next.debugEnabled);
  if (next.debugEnabled) text("debug", JSON.stringify({ detection: next.adapterDiagnostics, fields: next.fields.map((field) => ({ label: field.label, canonical: field.normalizedKey, confidence: field.confidence, policy: field.policy, conflict: field.conflict })) }, null, 2));
}

function showError(error: unknown, canEnable = false): void {
  const status = byId("status");
  status.classList.add("error");
  status.textContent = error instanceof Error ? error.message : "Operation failed.";
  hidden("enable-card", !canEnable);
}

async function action(message: RuntimeMessage): Promise<void> {
  try { render(await tabMessage<AssistantPageState>(message)); } catch (error) { showError(error); }
}

byId("enable-portal").addEventListener("click", async () => {
  try {
    if (!currentTabId || !currentTabUrl) throw new Error("Reload the Apply Assistant controls and try again.");
    const tabId = currentTabId;
    const portalUrl = currentTabUrl;
    const origins = portalPermissionOrigins(portalUrl);

    // Opera requires permissions.request() to be invoked directly from this
    // click handler. Relaying the request through the background worker loses
    // the browser's user-gesture token and is rejected.
    const granted = await chrome.permissions.request({ origins });
    if (!granted) throw new Error("Portal access was not granted. You can continue the application manually.");

    const response = await chrome.runtime.sendMessage({ type: "ENABLE_PORTAL_FOR_TAB", payload: { tabId, url: portalUrl } } satisfies RuntimeMessage);
    if (!response?.ok) throw new Error(response?.error || "Portal access was not granted.");
    render(await tabMessage<AssistantPageState>({ type: "GET_PAGE_STATE" }));
  } catch (error) { showError(error, true); }
});
byId("fill").addEventListener("click", async () => {
  await action({ type: "FILL_THIS_PAGE" });
  if (byId<HTMLInputElement>("auto-continue").checked && state && !state.pendingQuestions.length && !state.isReviewPage && !state.assessmentType) await action({ type: "CONTINUE" });
});
byId("ai-fill").addEventListener("click", async () => {
  await action({ type: "FILL_WITH_AGENT" });
  if (byId<HTMLInputElement>("auto-continue").checked && state && !state.pendingQuestions.length && !state.isReviewPage && !state.assessmentType) await action({ type: "CONTINUE" });
});
byId("read-questions").addEventListener("click", async () => {
  const button = byId<HTMLButtonElement>("read-questions");
  button.disabled = true;
  button.textContent = "Reading questions…";
  try { await action({ type: "ANALYZE_QUESTIONS" }); }
  finally {
    button.textContent = "Read questions & draft answers";
    if (state) render(state);
  }
});
byId("autopilot").addEventListener("click", async () => {
  const button = byId<HTMLButtonElement>("autopilot");
  button.disabled = true;
  button.textContent = "Autopilot running…";
  try {
    // Vision remains optional and local-only. Denying this permission does not
    // disable the DOM-based autopilot.
    await chrome.permissions.request({ origins: ["http://127.0.0.1:11434/*"] }).catch(() => false);
    await action({ type: "RUN_SAFE_AUTOPILOT" });
  } finally {
    button.textContent = "Run Safe Autopilot";
    if (state) render(state);
  }
});
byId("use-agent-decision").addEventListener("click", () => {
  const fieldId = byId("use-agent-decision").dataset.fieldId;
  if (fieldId) void action({ type: "USE_AGENT_DECISION", payload: { fieldId } });
});
byId("change-agent-decision").addEventListener("click", async () => {
  text("status", "Change this value directly on the application portal; it will not be learned globally without approval.");
  if (currentTabId) await chrome.tabs.update(currentTabId, { active: true });
});
byId("review").addEventListener("click", () => void action({ type: "REVIEW_FIELDS" }));
byId("edit-answers").addEventListener("click", async () => {
  text("status", "Review or change these answers directly on the application portal. Final Submit remains manual.");
  if (currentTabId) await chrome.tabs.update(currentTabId, { active: true });
});
byId("continue").addEventListener("click", () => void action({ type: "CONTINUE" }));
byId("pause").addEventListener("click", () => void action({ type: "TOGGLE_PAUSE" }));
byId("continue-manually").addEventListener("click", () => { if (state && !state.paused) void action({ type: "TOGGLE_PAUSE" }); });
byId("confirm-answer").addEventListener("click", () => {
  const questionKey = byId("confirm-answer").dataset.questionKey;
  if (questionKey) void action({ type: "CONFIRM_PAGE_ANSWER", payload: { questionKey, answer: byId<HTMLInputElement>("answer").value } });
});
for (const [id, useVerified] of [["keep-portal", false], ["use-verified", true]] as const) {
  byId(id).addEventListener("click", () => {
    const normalizedKey = byId(id).dataset.normalizedKey;
    if (normalizedKey) void action({ type: "RESOLVE_FIELD_CONFLICT", payload: { normalizedKey, useVerified } });
  });
}
byId("download-resume").addEventListener("click", async () => {
  try {
    const response = await chrome.runtime.sendMessage({ type: "DOWNLOAD_RESUME" });
    if (!response?.ok) throw new Error(response?.error || "Resume download failed.");
  } catch (error) { showError(error); }
});
byId("download-portfolio").addEventListener("click", async () => {
  try {
    const response = await chrome.runtime.sendMessage({ type: "DOWNLOAD_PORTFOLIO" });
    if (!response?.ok) throw new Error(response?.error || "Project Portfolio download failed.");
  } catch (error) { showError(error); }
});
byId("confirm-applied").addEventListener("click", async () => {
  if (!state?.isConfirmationPage || !state.confirmationText) return;
  try {
    const tab = currentTabId ? await chrome.tabs.get(currentTabId) : null;
    const response = await chrome.runtime.sendMessage({ type: "CONFIRM_SUBMITTED", payload: { confirmation_text: state.confirmationText, confirmation_url: tab?.url || "" } });
    if (!response?.ok) throw new Error(response?.error || "Applied status could not be confirmed.");
    text("status", "Application marked Applied in Internship Radar.");
    hidden("confirmation-card", true);
  } catch (error) { showError(error); }
});
byId<HTMLInputElement>("auto-continue").addEventListener("change", (event) => {
  void chrome.storage.local.set({ automaticallyContinueSafePages: (event.target as HTMLInputElement).checked });
});

async function initialize(): Promise<void> {
  try {
    const settings = await chrome.storage.local.get(["automaticallyContinueSafePages", "developerDebugEnabled"]);
    byId<HTMLInputElement>("auto-continue").checked = settings.automaticallyContinueSafePages === true;
    await applicationTab();
    if (settings.developerDebugEnabled === true) await action({ type: "SET_DEBUG", payload: { enabled: true } });
    render(await tabMessage<AssistantPageState>({ type: "GET_PAGE_STATE" }));
  } catch (error) { showError(error, Boolean(currentTabId)); }
}

chrome.tabs.onActivated.addListener(() => {
  if (!(Number.isInteger(requestedTabId) && requestedTabId > 0)) {
    currentTabId = null;
    currentTabUrl = "";
  }
  void initialize();
});
void initialize();
