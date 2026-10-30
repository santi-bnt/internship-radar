import { ApplicationAssistantCore } from "../../extension/src/content/ApplicationAssistantCore";
import type { AgentFieldResolution, ExtensionPayload, PreparedApplicationFile } from "../../extension/src/shared/types";

// This bundle runs only inside a Chromium isolated world, never in the
// employer page's JavaScript world. Profile snapshots stay in this closure.
let core: ApplicationAssistantCore;
let sessionId = 0;
let decisions: AgentFieldResolution[] = [];
const methods = {
  connect(payload: ExtensionPayload) {
    if (!core || sessionId !== payload.session.id) {
      core = new ApplicationAssistantCore(payload);
      sessionId = payload.session.id;
      decisions = [];
    }
  },
  review() {
    const state = core.review();
    return { ...state, applicationSessionId: sessionId, applicationPageUrl: location.href, agentDecisions: decisions.filter((item) => state.fields.some((field) => field.fieldId === item.field_id)) };
  },
  setDecisions(value: AgentFieldResolution[]) { decisions = value; },
  async fill(files: PreparedApplicationFile[]) { return core.fillThisPage(files, decisions); },
  async answer(fieldId: string, answer: string) {
    const decision = decisions.find((item) => item.field_id === fieldId);
    if (!decision) throw new Error("Read the current questions again before using this answer.");
    return core.applyReviewedAnswer(decision, answer);
  },
  async next() { return core.continuePage(methods.review().pendingQuestions.length); },
};

Object.defineProperty(globalThis, "__radarLocal", { value: methods, configurable: false });
