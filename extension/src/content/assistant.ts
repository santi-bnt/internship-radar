import { ApplicationAssistantCore } from "./ApplicationAssistantCore";
import type { RuntimeMessage } from "../shared/messages";
import type { ApplicationAgentPlan, AssistantPageState, ExtensionPayload, PreparedApplicationFile } from "../shared/types";
import { isFinalSubmitText } from "../shared/policies";
import type { VisionCandidate, VisionRect } from "../shared/visionSafety";

declare global { interface Window { __internshipRadarApplyAssistantLoaded?: boolean } }

function initialState(): AssistantPageState {
  return {
    connected: false, lastActionMessage: "", paused: false, portal: "UNKNOWN", supportStatus: "UNSUPPORTED", company: "", jobTitle: "",
    currentSection: "Connect from Internship Radar", progress: 0, fields: [], pendingQuestions: [], consistencyIssues: [],
    isReviewPage: false, isConfirmationPage: false, confirmationText: "", assessmentType: "", safeAutofillPausedReason: "",
    stage: "PROFILE", adapterDiagnostics: { adapterVersion: "", lastSuccessfulDetection: null, fieldsDetected: 0, fieldsFilled: 0, fieldsFailed: 0, unknownFields: 0, confidence: 0, evidence: [] },
    resume: null, portfolio: null, legalReview: [], applicationChecks: [],
    counts: { filled: 0, reviewed: 0, confirmed: 0 }, agentDecisions: [], aiMode: "BALANCED", debugEnabled: false
  };
}

function startAssistant(): void {
  let payload: ExtensionPayload | null = null;
  let core: ApplicationAssistantCore | null = null;
  let paused = false;
  let debugEnabled = false;
  let agentPlan: ApplicationAgentPlan | null = null;
  let analyzedPageUrl = "";
  let stopObserving: (() => void) | null = null;
  let lastActionMessage = "Ready to fill this page.";
  const counts = { filled: 0, reviewed: 0, confirmed: 0 };
  const confirmedThisApplication = new Set<string>();
  let state = initialState();

  function runtime<T>(message: RuntimeMessage): Promise<T> {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (!response?.ok) return reject(new Error(response?.error || "Extension operation failed."));
        resolve(response.data as T);
      });
    });
  }

  function pageStatus(): string {
    if (state.isReviewPage) return "READY_FOR_REVIEW";
    if (state.pendingQuestions.length || state.assessmentType || state.safeAutofillPausedReason) return "WAITING_FOR_USER";
    return "IN_PROGRESS";
  }

  function refreshState(): AssistantPageState {
    if (!payload || !core) return state;
    const reviewed = core.review();
    if (analyzedPageUrl !== window.location.href) agentPlan = null;
    reviewed.pendingQuestions = reviewed.pendingQuestions.filter((question) => !confirmedThisApplication.has(question.questionKey));
    state = {
      ...reviewed,
      applicationSessionId: payload.session.id,
      applicationPageUrl: window.location.href,
      lastActionMessage,
      paused: paused || reviewed.paused,
      debugEnabled,
      counts: { ...counts },
      agentDecisions: (agentPlan?.resolutions || []).filter((decision) => reviewed.fields.some((field) => field.fieldId === decision.field_id)),
      aiMode: payload.ai_settings.ai_mode,
    };
    return state;
  }

  async function syncProgress(): Promise<void> {
    if (!payload || !core) return;
    refreshState();
    const reviewRequiredAnswers = state.fields
      .filter((field) => field.policy === "AUTO_FILL_REVIEW_REQUIRED")
      .map((field) => ({
          raw_question: field.label,
          normalized_question_key: field.normalizedKey,
          confidence: field.confidence,
          selected_answer: field.value ?? "",
          answer_source: field.answerSource ?? "PREVIOUSLY_CONFIRMED_CANDIDATE_PROFILE",
          policy: field.policy,
        }));
    await runtime({
      type: "UPDATE_PROGRESS",
      payload: {
        status: pageStatus(), current_step: state.stage,
        portal_type: state.portal,
        portal_job_id: core.adapter.detectPortalMetadata().portalJobId || payload.session.portal_job_id,
        pending_questions_json: state.pendingQuestions,
        confirmed_fields_json: {
          review_required_answers: reviewRequiredAnswers,
          ai_decisions: state.agentDecisions.map((decision) => ({
            field: decision.canonical_field,
            action: decision.action,
            confidence: decision.confidence,
            provider: decision.provider,
            execution_location: decision.execution_location,
          })),
        },
        fields_filled_count: counts.filled, fields_reviewed_count: counts.reviewed, fields_confirmed_count: counts.confirmed,
        last_page_url: window.location.href, observed_fields: core.adapter.observedValues(),
        portal_detection_evidence_json: state.adapterDiagnostics.evidence,
        adapter_diagnostics_json: state.adapterDiagnostics,
        adapter_version: state.adapterDiagnostics.adapterVersion,
        company_policy_key: payload.company_policy.company_policy_key,
        assessment_type: state.assessmentType,
        error_code: state.supportStatus === "PORTAL_CHANGED" ? "PORTAL_CHANGED" : "",
        safe_error_message: state.safeAutofillPausedReason
      }
    }).catch(() => undefined);
  }

  async function connect(): Promise<void> {
    try {
      payload = await runtime<ExtensionPayload>({ type: "GET_APPLICATION_PAYLOAD" });
      core = new ApplicationAssistantCore(payload);
      agentPlan = null;
      confirmedThisApplication.clear();
      Object.keys(payload.session.application_answers_json || {}).forEach((key) => confirmedThisApplication.add(key));
      counts.filled = payload.session.fields_filled_count || 0;
      counts.reviewed = payload.session.fields_reviewed_count || 0;
      counts.confirmed = confirmedThisApplication.size;
      lastActionMessage = "Profile connected. Ready to fill this page.";
      stopObserving?.();
      stopObserving = core.adapter.observe(() => { if (payload && !paused) void syncProgress(); });
      refreshState();
      await syncProgress();
    } catch (error) {
      payload = null;
      core = null;
      state = { ...initialState(), currentSection: error instanceof Error ? error.message : "Start Apply with Assistant from Internship Radar" };
    }
  }

  async function analyzeQuestions(): Promise<AssistantPageState> {
    if (!payload || !core) throw new Error("No Application Session is connected.");
    if (paused) throw new Error("Apply Assistant is paused.");
    const reviewed = refreshState();
    if (reviewed.isReviewPage || reviewed.assessmentType) throw new Error("Open an application form section to read its questions.");
    const pageUrl = window.location.href;
    agentPlan = await runtime<ApplicationAgentPlan>({
      type: "ANALYZE_APPLICATION_PAGE",
      payload: {
        page_url: pageUrl, page_title: document.title,
        fields: reviewed.fields.map((field) => ({
          field_id: field.fieldId, raw_label: field.label, nearby_text: field.nearbyText,
          control_type: field.controlType, available_options: field.availableOptions,
          current_value: field.currentValue ?? field.value, required: field.required, maxlength: field.maxlength,
        })),
      },
    });
    analyzedPageUrl = pageUrl;
    lastActionMessage = "Questions read. Review and edit the suggested answers below.";
    return refreshState();
  }

  async function applyReviewedAnswer(fieldId: string, answer: string): Promise<AssistantPageState> {
    if (!core || paused) throw new Error("Connect and resume the application assistant first.");
    refreshState();
    const decision = agentPlan?.resolutions.find((item) => item.field_id === fieldId);
    if (!decision) throw new Error("Read the current questions again before using an answer.");
    if (!(await core.applyReviewedAnswer(decision, answer))) throw new Error("This field could not be filled. Copy the answer to the portal.");
    counts.reviewed += 1;
    lastActionMessage = "Your reviewed answer was filled into the application.";
    await syncProgress();
    return refreshState();
  }

  async function fillPage(useAgent = false): Promise<AssistantPageState> {
    if (!payload || !core) throw new Error("No Application Session is connected.");
    if (paused) throw new Error("Apply Assistant is paused.");
    if (useAgent) {
      try {
        await analyzeQuestions();
      } catch {
        // Basic verified-profile filling is local and deterministic. A busy or
        // temporarily unavailable API must not turn the Apply button into a
        // no-op, so continue locally and leave ambiguous questions untouched.
        agentPlan = null;
        lastActionMessage = "AI analysis was unavailable; safe profile fields were filled locally.";
      }
    }
    let preparedFiles: PreparedApplicationFile[] = [];
    try { preparedFiles = await runtime<PreparedApplicationFile[]>({ type: "GET_PREPARED_FILES" }); } catch { /* safe fields can still be filled; file readiness remains blocking */ }
    const result = await core.fillThisPage(preparedFiles, useAgent ? agentPlan?.resolutions || [] : []);
    counts.filled += result.filled;
    counts.reviewed += result.reviewed;
    if (result.filled > 0) {
      lastActionMessage = `${result.filled} field${result.filled === 1 ? "" : "s"} filled on this page${result.reviewed ? `; ${result.reviewed} need review` : ""}.`;
    } else {
      const detected = refreshState().adapterDiagnostics.fieldsDetected;
      lastActionMessage = detected
        ? "No new fields were filled. Existing answers were preserved; unsupported or sensitive fields need manual input."
        : "No form fields were detected. Wait for the form to load, then enable this portal and try again.";
    }
    await syncProgress();
    return refreshState();
  }

  async function confirmAnswer(questionKey: string, answer: unknown): Promise<AssistantPageState> {
    if (!payload || !core) throw new Error("No Application Session is connected.");
    const question = refreshState().pendingQuestions.find((item) => item.questionKey === questionKey);
    if (!question || question.policy !== "CONFIRM_REQUIRED") throw new Error("This question must be completed manually.");
    await runtime({ type: "CONFIRM_ANSWER", payload: { question_key: question.questionKey, normalized_question: question.question, answer, answer_type: typeof answer === "boolean" ? "boolean" : "text", classification_confidence: question.confidence } });
    const filled = await core.adapter.fillConfirmedAnswer(questionKey, answer);
    if (!filled) throw new Error("Answer confirmed, but this portal requires you to select it manually on the page.");
    confirmedThisApplication.add(questionKey);
    counts.confirmed = confirmedThisApplication.size;
    await syncProgress();
    return refreshState();
  }

  async function approveAgentDecision(fieldId: string): Promise<AssistantPageState> {
    if (!payload || !agentPlan) throw new Error("Analyze this page before approving a mapping.");
    const decision = agentPlan.resolutions.find((item) => item.field_id === fieldId);
    if (!decision?.selected_option || decision.selected_value == null) throw new Error("This decision is not a reusable dropdown mapping.");
    await runtime({
      type: "APPROVE_AGENT_MAPPING",
      payload: {
        portal: payload.session.portal_type,
        canonical_field: decision.canonical_field,
        canonical_value: String(decision.selected_value),
        portal_option: decision.selected_option,
        match_type: decision.match_type,
      },
    });
    decision.requires_review = false;
    return refreshState();
  }

  function rectFor(element: Element): VisionRect | null {
    const rect = element.getBoundingClientRect();
    const left = Math.max(0, rect.left);
    const top = Math.max(0, rect.top);
    const right = Math.min(window.innerWidth, rect.right);
    const bottom = Math.min(window.innerHeight, rect.bottom);
    if (right <= left || bottom <= top) return null;
    return { x: left, y: top, width: right - left, height: bottom - top };
  }

  function visionPrivacyRects(): VisionRect[] {
    const sensitive = /(?:full|first|last|preferred|legal) name|email|phone|mobile|address|postal|zip|password|passcode|mfa|verification|captcha|signature|attestation|ssn|curp|rfc|passport|visa|disability|veteran|race|ethnicity|religion|sexual orientation|criminal/i;
    const rectangles: VisionRect[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("input, textarea, select, [contenteditable='true']")) {
      const value = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement
        ? element.value : element.textContent || "";
      const descriptor = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("name") || ""} ${element.getAttribute("placeholder") || ""} ${element instanceof HTMLInputElement ? [...(element.labels || [])].map((label) => label.textContent || "").join(" ") : ""}`;
      if (value.trim() || sensitive.test(descriptor)) {
        const rect = rectFor(element.closest("label, .field, .form-group, [class*='field'], [role='group']") || element);
        if (rect) rectangles.push(rect);
      }
    }
    for (const element of document.querySelectorAll<HTMLElement>("main *, form *")) {
      if (element.children.length || !/(?:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\+?\d[\d ()-]{7,}\d|\b(?:CURP|RFC|SSN|passport|visa)\b)/i.test(element.textContent || "")) continue;
      const rect = rectFor(element);
      if (rect) rectangles.push(rect);
    }
    return rectangles.slice(0, 100);
  }

  function controlAt(candidate: VisionCandidate): HTMLElement | null {
    const hit = document.elementFromPoint(candidate.x, candidate.y) as HTMLElement | null;
    if (!hit) return null;
    const selector = "input:not([type='hidden']), textarea, select, [role='combobox'], [contenteditable='true']";
    if (hit.matches(selector)) return hit;
    return hit.closest("label, .field, .form-group, [class*='field'], [class*='question'], [role='group']")?.querySelector<HTMLElement>(selector)
      || hit.querySelector<HTMLElement>(selector);
  }

  function applyVisionCandidates(candidates: VisionCandidate[]): { labeled: number; continued: boolean } {
    let labeled = 0;
    for (const candidate of candidates.filter((item) => item.action === "LABEL_CONTROL")) {
      const control = controlAt(candidate);
      if (!control || control instanceof HTMLInputElement && ["password", "hidden"].includes(control.type)) continue;
      control.setAttribute("data-internship-radar-vision-label", candidate.label);
      labeled += 1;
    }
    // Never navigate away before newly identified controls have gone through
    // the deterministic resolver and validation pass.
    if (labeled) return { labeled, continued: false };
    for (const candidate of candidates.filter((item) => item.action === "CONTINUE")) {
      const hit = document.elementFromPoint(candidate.x, candidate.y) as HTMLElement | null;
      const button = hit?.closest<HTMLElement>("button, [role='button'], input[type='button'], input[type='submit']");
      const text = (button instanceof HTMLInputElement ? button.value : button?.textContent || "").trim();
      if (button && /^(?:next|continue|save and continue|save)$/i.test(text) && !isFinalSubmitText(text)) {
        button.click();
        return { labeled: 0, continued: true };
      }
    }
    return { labeled: 0, continued: false };
  }

  async function runSafeAutopilot(): Promise<AssistantPageState> {
    if (!payload || !core) throw new Error("No Application Session is connected.");
    const visionPages = new Set<string>();
    for (let step = 0; step < 6; step += 1) {
      let reviewed = refreshState();
      if (reviewed.isReviewPage || reviewed.isConfirmationPage || reviewed.assessmentType) break;
      const before = counts.filled;
      reviewed = await fillPage(true);
      const newlyFilled = counts.filled - before;
      const blocking = reviewed.applicationChecks.some((check) => check.blocking && !check.ready);
      const pageKey = `${window.location.href}|${reviewed.stage}`;
      if ((newlyFilled === 0 || blocking) && !visionPages.has(pageKey)) {
        visionPages.add(pageKey);
        try {
          const result = await runtime<{ model: string; candidates: VisionCandidate[] }>({
            type: "LOCAL_VISION_ANALYZE",
            payload: {
              viewport: { width: window.innerWidth, height: window.innerHeight },
              redactedRects: visionPrivacyRects(),
              pageTitle: document.title,
              unresolvedLabels: reviewed.fields.filter((field) => field.normalizedKey === "UNKNOWN").map((field) => field.label),
            },
          });
          const applied = applyVisionCandidates(result.candidates);
          if (applied.labeled) {
            lastActionMessage = `Local vision (${result.model}) identified ${applied.labeled} control${applied.labeled === 1 ? "" : "s"}; filling them safely.`;
            await new Promise((resolve) => window.setTimeout(resolve, 150));
            continue;
          }
          if (applied.continued) {
            lastActionMessage = "Local vision safely advanced to the next section.";
            await new Promise((resolve) => window.setTimeout(resolve, 800));
            continue;
          }
        } catch (error) {
          const detail = error instanceof Error ? error.message : "Local vision unavailable.";
          lastActionMessage = `${newlyFilled ? `${newlyFilled} fields filled. ` : ""}${detail}`;
        }
      }
      reviewed = refreshState();
      if (reviewed.pendingQuestions.length || reviewed.isReviewPage || reviewed.assessmentType) break;
      if (reviewed.applicationChecks.some((check) => check.blocking && !check.ready)) break;
      if (!(await core.continuePage(0))) break;
      lastActionMessage = `Safe Autopilot advanced section ${step + 1}.`;
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }
    await syncProgress();
    return refreshState();
  }

  chrome.runtime.onMessage.addListener((message: RuntimeMessage | { type: "APPLICATION_SESSION_AVAILABLE" }, _sender, sendResponse) => {
    void (async () => {
      try {
        switch (message.type) {
          case "APPLICATION_SESSION_AVAILABLE": await connect(); sendResponse({ ok: true, data: refreshState() }); break;
          case "GET_PAGE_STATE": sendResponse({ ok: true, data: refreshState() }); break;
          case "FILL_THIS_PAGE": sendResponse({ ok: true, data: await fillPage() }); break;
          case "FILL_WITH_AGENT": sendResponse({ ok: true, data: await fillPage(true) }); break;
          case "ANALYZE_QUESTIONS": sendResponse({ ok: true, data: await analyzeQuestions() }); break;
          case "APPLY_REVIEWED_ANSWER": sendResponse({ ok: true, data: await applyReviewedAnswer(message.payload.fieldId, message.payload.answer) }); break;
          case "RUN_SAFE_AUTOPILOT": sendResponse({ ok: true, data: await runSafeAutopilot() }); break;
          case "USE_AGENT_DECISION": sendResponse({ ok: true, data: await approveAgentDecision(message.payload.fieldId) }); break;
          case "REVIEW_FIELDS": await syncProgress(); sendResponse({ ok: true, data: refreshState() }); break;
          case "CONTINUE": {
            if (!payload || !core) throw new Error("No Application Session is connected.");
            refreshState();
            const continued = await core.continuePage(state.pendingQuestions.length);
            if (!continued) throw new Error(state.isReviewPage ? "Final review reached. Internship Radar will not press Submit." : state.assessmentType ? "Assessment detected. Continue manually." : "Confirm sensitive fields or continue manually.");
            sendResponse({ ok: true, data: refreshState() });
            break;
          }
          case "TOGGLE_PAUSE": paused = !paused; sendResponse({ ok: true, data: refreshState() }); break;
          case "SET_DEBUG": debugEnabled = message.payload.enabled; sendResponse({ ok: true, data: refreshState() }); break;
          case "CONFIRM_PAGE_ANSWER": sendResponse({ ok: true, data: await confirmAnswer(message.payload.questionKey, message.payload.answer) }); break;
          case "RESOLVE_FIELD_CONFLICT": {
            if (!payload || !core) throw new Error("No Application Session is connected.");
            const resolved = await core.adapter.resolveFieldConflict(message.payload.normalizedKey, message.payload.useVerified, payload);
            if (!resolved) throw new Error("This saved-profile conflict could not be resolved automatically. Continue manually.");
            await syncProgress();
            sendResponse({ ok: true, data: refreshState() });
            break;
          }
          default: sendResponse({ ok: false, error: "Unsupported assistant action." });
        }
      } catch (error) {
        sendResponse({ ok: false, error: error instanceof Error ? error.message : "Assistant action failed." });
      }
    })();
    return true;
  });

  void connect();
}

if (!window.__internshipRadarApplyAssistantLoaded) {
  window.__internshipRadarApplyAssistantLoaded = true;
  startAssistant();
}
