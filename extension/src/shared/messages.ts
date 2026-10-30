export type RuntimeMessage =
  | { type: "PING" }
  | { type: "CONNECT_APPLICATION_SESSION"; payload: { sessionId: number; token: string; expiresAt: string; apiBaseUrl: string; applicationUrl: string } }
  | { type: "GET_ACTIVE_SESSION" }
  | { type: "GET_APPLICATION_PAYLOAD" }
  | { type: "ANALYZE_APPLICATION_PAGE"; payload: { page_url: string; page_title: string; fields: Array<Record<string, unknown>> } }
  | { type: "APPROVE_AGENT_MAPPING"; payload: { portal: string; canonical_field: string; canonical_value: string; portal_option: string; match_type: string } }
  | { type: "UPDATE_PROGRESS"; payload: Record<string, unknown> }
  | { type: "CONFIRM_ANSWER"; payload: Record<string, unknown> }
  | { type: "CONFIRM_SUBMITTED"; payload: { confirmation_text: string; confirmation_url: string } }
  | { type: "DOWNLOAD_RESUME" }
  | { type: "DOWNLOAD_PORTFOLIO" }
  | { type: "GET_PREPARED_FILES" }
  | { type: "REVOKE_LOCAL_SESSION" }
  | { type: "ENABLE_PORTAL_FOR_TAB"; payload: { tabId: number; url: string } }
  | { type: "LOCAL_VISION_ANALYZE"; payload: { viewport: { width: number; height: number }; redactedRects: Array<{ x: number; y: number; width: number; height: number }>; pageTitle: string; unresolvedLabels: string[] } }
  | { type: "GET_PAGE_STATE" }
  | { type: "FILL_THIS_PAGE" }
  | { type: "FILL_WITH_AGENT" }
  | { type: "ANALYZE_QUESTIONS" }
  | { type: "APPLY_REVIEWED_ANSWER"; payload: { fieldId: string; answer: string } }
  | { type: "RUN_SAFE_AUTOPILOT" }
  | { type: "USE_AGENT_DECISION"; payload: { fieldId: string } }
  | { type: "REVIEW_FIELDS" }
  | { type: "CONTINUE" }
  | { type: "TOGGLE_PAUSE" }
  | { type: "SET_DEBUG"; payload: { enabled: boolean } }
  | { type: "CONFIRM_PAGE_ANSWER"; payload: { questionKey: string; answer: unknown } }
  | { type: "RESOLVE_FIELD_CONFLICT"; payload: { normalizedKey: string; useVerified: boolean } };
