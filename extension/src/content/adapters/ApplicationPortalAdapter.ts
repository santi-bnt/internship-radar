import type { AdapterDiagnostics, AgentFieldResolution, AssistantPageState, AssessmentType, DetectedField, ExtensionPayload, PortalSupportStatus, PortalType, PreparedApplicationFile } from "../../shared/types";

export interface ApplicationPortalAdapter {
  readonly portalType: PortalType;
  readonly adapterVersion: string;
  readonly supportStatus: PortalSupportStatus;
  detectFields(): DetectedField[];
  detectPortalMetadata(): { companyHost: string; jobTitle: string; portalJobId: string };
  fillThisPage(payload: ExtensionPayload, preparedFiles?: PreparedApplicationFile[], resolutions?: AgentFieldResolution[]): Promise<{ filled: number; reviewed: number }>;
  fillConfirmedAnswer(questionKey: string, answer: unknown): Promise<boolean>;
  fillReviewedText(fieldId: string, answer: string): Promise<boolean>;
  resolveFieldConflict(normalizedKey: string, useVerified: boolean, payload: ExtensionPayload): Promise<boolean>;
  review(payload: ExtensionPayload): AssistantPageState;
  continuePage(pendingConfirmationCount: number): Promise<boolean>;
  observe(onChange: () => void): () => void;
  isReviewPage(): boolean;
  detectConfirmation(): { confirmed: boolean; text: string };
  observedValues(): Record<string, unknown>;
  detectAssessment(): AssessmentType;
  diagnostics(): AdapterDiagnostics;
}
