import { filterSafeVisionCandidates, type VisionCandidate, type VisionRect } from "../shared/visionSafety";

interface VisionRequestContext {
  viewport: { width: number; height: number };
  redactedRects: VisionRect[];
  pageTitle: string;
  unresolvedLabels: string[];
}

function arrayBufferToBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  for (let offset = 0; offset < view.length; offset += 0x8000) binary += String.fromCharCode(...view.subarray(offset, offset + 0x8000));
  return btoa(binary);
}

async function redactScreenshot(dataUrl: string, context: VisionRequestContext): Promise<string> {
  const source = await createImageBitmap(await (await fetch(dataUrl)).blob());
  // Normalize the captured device-pixel image to CSS viewport pixels. This
  // keeps the model's coordinates aligned on Windows display scaling (125%,
  // 150%, etc.) before any action is validated against document.elementFromPoint.
  const canvas = new OffscreenCanvas(Math.max(1, Math.round(context.viewport.width)), Math.max(1, Math.round(context.viewport.height)));
  const drawing = canvas.getContext("2d");
  if (!drawing) throw new Error("Local screenshot redaction is unavailable in this browser.");
  drawing.drawImage(source, 0, 0, canvas.width, canvas.height);
  drawing.fillStyle = "#111111";
  for (const rect of context.redactedRects) {
    drawing.fillRect(rect.x, rect.y, rect.width, rect.height);
  }
  source.close();
  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.72 });
  return arrayBufferToBase64(await blob.arrayBuffer());
}

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = 20_000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...init, signal: controller.signal, credentials: "omit", cache: "no-store" }); }
  finally { clearTimeout(timer); }
}

async function localVisionModel(): Promise<string> {
  const response = await fetchWithTimeout("http://127.0.0.1:11434/api/tags", undefined, 2500);
  if (!response.ok) throw new Error("Local vision is unavailable. Start Ollama with a vision-capable model.");
  const payload = await response.json() as { models?: Array<{ name?: string }> };
  const models = (payload.models || []).map((item) => String(item.name || "")).filter(Boolean);
  const model = models.find((name) => /(?:qwen.*vl|llava|moondream|minicpm.*v|gemma3)/i.test(name));
  if (!model) throw new Error("No local vision-capable Ollama model was found.");
  return model;
}

function parseVisionResponse(content: string): unknown[] {
  const cleaned = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const parsed = JSON.parse(cleaned) as { controls?: unknown[] } | unknown[];
  return Array.isArray(parsed) ? parsed : Array.isArray(parsed.controls) ? parsed.controls : [];
}

export async function analyzeVisibleApplicationLocally(
  tab: chrome.tabs.Tab,
  context: VisionRequestContext,
): Promise<{ model: string; candidates: VisionCandidate[] }> {
  if (!tab.id || tab.windowId == null) throw new Error("The active application tab is unavailable.");
  if (!tab.active) throw new Error("Keep the application tab visible while local vision inspects it.");
  const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 75 });
  const redactedBase64 = await redactScreenshot(screenshot, context);
  const model = await localVisionModel();
  const prompt = [
    "You inspect a redacted job-application viewport. Return JSON only as {\"controls\":[...] }.",
    "Identify visible unlabeled form controls and a safe Next/Continue button only.",
    "Each item: action LABEL_CONTROL or CONTINUE, x, y in CSS viewport pixels, label, control_type, confidence 0..1.",
    "Never return Submit, Apply, CAPTCHA, password, MFA, assessment, signature, attestation, demographic or voluntary-disclosure controls.",
    `Viewport: ${context.viewport.width}x${context.viewport.height}. Page: ${context.pageTitle.slice(0, 200)}.`,
    `DOM labels needing help: ${context.unresolvedLabels.slice(0, 30).join(" | ").slice(0, 2000) || "none"}.`,
  ].join("\n");
  const response = await fetchWithTimeout("http://127.0.0.1:11434/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, stream: false, format: "json", messages: [{ role: "user", content: prompt, images: [redactedBase64] }] }),
  });
  if (!response.ok) throw new Error(`Local vision model failed (${response.status}).`);
  const payload = await response.json() as { message?: { content?: string } };
  const raw = parseVisionResponse(String(payload.message?.content || "{}"));
  return { model, candidates: filterSafeVisionCandidates(raw, context.viewport, context.redactedRects) };
}
