import { matchQuestion, normalizeQuestion } from "./questionMatcher";
import type { FieldPolicy } from "./types";

const autoFillPatterns = [
  /(?:first|given|last|family|full|preferred) name/,
  /email/,
  /phone|mobile/,
  /address|city|postal|zip|country/,
  /^(?:state|province|region)(?:\/| |$)/,
  /university|school|degree|field of study|gpa|grade point|graduation|education (?:start|end)|(?:start|end) date (?:month|year)/,
  /github|linked ?in|website/,
  /language|skill/
];

const reviewPatterns = [
  /project|academic experience|work experience|employment experience|experience description|availability/,
  /salary.*text|expected compensation.*text/
];

const manualPatterns = [
  /captcha|verification code|one time|mfa|multi factor|password|passcode/,
  /electronic signature|type your name to certify|attestation|certif(?:y|ication)/,
  /coding assessment|online assessment|behavioral assessment|work simulation|technical test/
];

export function fieldPolicy(label: string, inputType = "text"): { policy: FieldPolicy; normalizedKey: string; confidence: number } {
  const normalized = normalizeQuestion(label);
  if (inputType === "password" || manualPatterns.some((pattern) => pattern.test(normalized))) {
    return { policy: "MANUAL_ONLY", normalizedKey: "SECURITY_OR_ATTESTATION", confidence: 1 };
  }
  const question = matchQuestion(label);
  if (question.questionKey !== "UNKNOWN") {
    return { policy: question.policy, normalizedKey: question.questionKey, confidence: question.confidence };
  }
  if (reviewPatterns.some((pattern) => pattern.test(normalized))) {
    return { policy: "REVIEW_RECOMMENDED", normalizedKey: normalized.toUpperCase().replace(/ /g, "_"), confidence: 0.9 };
  }
  if (autoFillPatterns.some((pattern) => pattern.test(normalized))) {
    return { policy: "AUTO_FILL", normalizedKey: normalized.toUpperCase().replace(/ /g, "_"), confidence: 0.92 };
  }
  return { policy: "MANUAL_ONLY", normalizedKey: "UNKNOWN", confidence: 0.2 };
}

export function isFinalSubmitText(text: string): boolean {
  const normalized = normalizeQuestion(text);
  if (["submit", "apply", "apply now", "certify and submit", "send application", "submit application", "complete application"].includes(normalized)) return true;
  return /^(?:certify and )?(?:submit|send|complete)(?: (?:your|the))? application(?: now)?$/.test(normalized);
}

export function detectAssessmentText(text: string): "CODING_ASSESSMENT" | "ONLINE_ASSESSMENT" | "BEHAVIORAL_ASSESSMENT" | "TECHNICAL_TEST" | "" {
  const normalized = normalizeQuestion(text);
  if (/coding assessment|coding challenge/.test(normalized)) return "CODING_ASSESSMENT";
  if (/behavioral assessment|work simulation/.test(normalized)) return "BEHAVIORAL_ASSESSMENT";
  if (/technical test|technical assessment/.test(normalized)) return "TECHNICAL_TEST";
  if (/online assessment|assessment required|complete your assessment/.test(normalized)) return "ONLINE_ASSESSMENT";
  return "";
}

export const genericSafeFieldPatterns = [
  /(?:first|given|last|family|full|preferred) name/,
  /email/,
  /phone|mobile/,
  /linked ?in|github/,
  /university|school|degree|graduation/
];
