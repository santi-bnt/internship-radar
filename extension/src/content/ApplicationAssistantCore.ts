import type { ApplicationPortalAdapter } from "./adapters/ApplicationPortalAdapter";
import { AmazonJobsAdapter } from "./adapters/amazon/AmazonJobsAdapter";
import { GenericApplicationAdapter } from "./adapters/generic/GenericApplicationAdapter";
import { GreenhouseAdapter } from "./adapters/greenhouse/GreenhouseAdapter";
import { MicrosoftCareersAdapter } from "./adapters/microsoft/MicrosoftCareersAdapter";
import { OracleCareersAdapter } from "./adapters/oracle/OracleCareersAdapter";
import { SmartRecruitersAdapter } from "./adapters/smartrecruiters/SmartRecruitersAdapter";
import { WorkdayAdapter } from "./adapters/workday/WorkdayAdapter";
import { detectPortal } from "../shared/portalDetection";
import type { AgentFieldResolution, AssistantPageState, ExtensionPayload, PortalDetection, PreparedApplicationFile } from "../shared/types";

const adapterFactories = {
  WORKDAY: () => new WorkdayAdapter(),
  GREENHOUSE: () => new GreenhouseAdapter(),
  MICROSOFT_CAREERS: () => new MicrosoftCareersAdapter(),
  AMAZON_JOBS: () => new AmazonJobsAdapter(),
  ORACLE_CAREERS: () => new OracleCareersAdapter(),
  SMARTRECRUITERS: () => new SmartRecruitersAdapter(),
  GENERIC: () => new GenericApplicationAdapter()
} as const;

export class ApplicationAssistantCore {
  readonly detection: PortalDetection;
  readonly adapter: ApplicationPortalAdapter;

  constructor(private readonly payload: ExtensionPayload) {
    this.detection = detectPortal(window.location.href, payload.session.company);
    const factory = adapterFactories[this.detection.portalType as keyof typeof adapterFactories];
    if (!factory || this.detection.supportStatus === "UNSUPPORTED") {
      throw new Error(`${this.detection.portalType.replaceAll("_", " ")} is not supported. Continue manually.`);
    }
    this.adapter = factory();
  }

  review(): AssistantPageState {
    const state = this.adapter.review(this.payload);
    state.portal = this.detection.portalType;
    // The runtime detector selects the adapter, but the adapter remains the
    // authority on whether its expected DOM is still present. Never downgrade
    // PORTAL_CHANGED back to a registry status after a portal navigation.
    state.supportStatus = state.supportStatus === "PORTAL_CHANGED"
      ? "PORTAL_CHANGED"
      : this.detection.supportStatus;
    state.adapterDiagnostics.evidence = [...new Set([...this.detection.evidence, ...state.adapterDiagnostics.evidence])];
    if (state.isReviewPage) {
      state.isReviewPage = true;
      state.stage = "REVIEW";
    }
    return state;
  }

  async fillThisPage(preparedFiles: PreparedApplicationFile[] = [], resolutions: AgentFieldResolution[] = []): Promise<{ filled: number; reviewed: number }> {
    const state = this.review();
    if (state.isReviewPage) throw new Error("Final review reached. Internship Radar will not fill or submit this page.");
    if (state.assessmentType) throw new Error("Assessment detected. Complete this section manually.");
    if (state.supportStatus === "PORTAL_CHANGED") throw new Error("This portal may have changed. Safe autofill is paused.");
    return this.adapter.fillThisPage(this.payload, preparedFiles, resolutions);
  }

  async continuePage(pendingConfirmationCount: number): Promise<boolean> {
    if (this.review().isReviewPage) return false;
    return this.adapter.continuePage(pendingConfirmationCount);
  }

  async applyReviewedAnswer(decision: AgentFieldResolution, answer: string): Promise<boolean> {
    const state = this.review();
    if (state.isReviewPage || state.assessmentType || state.supportStatus === "PORTAL_CHANGED") {
      throw new Error("Return to an editable application section to use this answer.");
    }
    if (decision.action !== "GENERATE_REVIEW"
      || !["JOB_SPECIFIC_TEXT", "EXPERIENCE_QUESTION"].includes(decision.question_category)
      || !state.fields.some((field) => field.fieldId === decision.field_id)) {
      throw new Error("Read the current application questions before using this answer.");
    }
    return this.adapter.fillReviewedText(decision.field_id, answer);
  }
}
