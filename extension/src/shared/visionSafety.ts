import { normalizeQuestion } from "./questionMatcher";

export interface VisionRect { x: number; y: number; width: number; height: number }

export interface VisionCandidate {
  action: "LABEL_CONTROL" | "CONTINUE";
  x: number;
  y: number;
  label: string;
  control_type?: string;
  confidence: number;
}

const prohibited = /\b(?:submit|apply|send application|complete application|captcha|verification code|one time|mfa|password|passcode|electronic signature|attestation|certify|disability|veteran|race|ethnicity|religion|sexual orientation|criminal history)\b/;
const allowedContinue = /^(?:next|continue|save and continue|save)$/;

function contains(rect: VisionRect, x: number, y: number): boolean {
  return x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height;
}

export function safeVisionCandidate(
  value: unknown,
  viewport: { width: number; height: number },
  redactedRects: VisionRect[],
): VisionCandidate | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<VisionCandidate>;
  if (!Number.isFinite(raw.x) || !Number.isFinite(raw.y) || !Number.isFinite(raw.confidence)) return null;
  if (raw.action !== "CONTINUE" && raw.action !== "LABEL_CONTROL") return null;
  const candidate: VisionCandidate = {
    action: raw.action,
    x: Number(raw.x), y: Number(raw.y), label: String(raw.label || "").trim().slice(0, 240),
    control_type: String(raw.control_type || "").trim().slice(0, 40), confidence: Number(raw.confidence),
  };
  const normalized = normalizeQuestion(candidate.label);
  if (!candidate.label || candidate.confidence < 0.8 || candidate.x < 0 || candidate.y < 0 || candidate.x > viewport.width || candidate.y > viewport.height) return null;
  if (prohibited.test(normalized) || redactedRects.some((rect) => contains(rect, candidate.x, candidate.y))) return null;
  if (candidate.action === "CONTINUE" && !allowedContinue.test(normalized)) return null;
  return candidate;
}

export function filterSafeVisionCandidates(
  values: unknown,
  viewport: { width: number; height: number },
  redactedRects: VisionRect[],
): VisionCandidate[] {
  if (!Array.isArray(values)) return [];
  const result: VisionCandidate[] = [];
  for (const value of values.slice(0, 20)) {
    const candidate = safeVisionCandidate(value, viewport, redactedRects);
    if (candidate) result.push(candidate);
  }
  return result;
}
