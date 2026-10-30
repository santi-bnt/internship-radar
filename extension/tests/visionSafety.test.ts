import { describe, expect, it } from "vitest";

import { filterSafeVisionCandidates, safeVisionCandidate } from "../src/shared/visionSafety";

const viewport = { width: 1200, height: 800 };

describe("local vision safety boundary", () => {
  it("accepts only high-confidence control labels and safe navigation", () => {
    const result = filterSafeVisionCandidates([
      { action: "LABEL_CONTROL", x: 100, y: 200, label: "Expected graduation date", confidence: 0.94 },
      { action: "CONTINUE", x: 900, y: 700, label: "Save and Continue", confidence: 0.91 },
      { action: "CONTINUE", x: 910, y: 710, label: "Submit Application", confidence: 0.99 },
    ], viewport, []);
    expect(result.map((item) => item.label)).toEqual(["Expected graduation date", "Save and Continue"]);
  });

  it("rejects sensitive, redacted, low-confidence, and out-of-bounds targets", () => {
    const redacted = [{ x: 50, y: 50, width: 200, height: 100 }];
    expect(safeVisionCandidate({ action: "LABEL_CONTROL", x: 100, y: 80, label: "School", confidence: 0.99 }, viewport, redacted)).toBeNull();
    expect(safeVisionCandidate({ action: "LABEL_CONTROL", x: 300, y: 200, label: "Electronic signature", confidence: 0.99 }, viewport, redacted)).toBeNull();
    expect(safeVisionCandidate({ action: "LABEL_CONTROL", x: 300, y: 200, label: "University", confidence: 0.5 }, viewport, redacted)).toBeNull();
    expect(safeVisionCandidate({ action: "LABEL_CONTROL", x: 1400, y: 200, label: "University", confidence: 0.99 }, viewport, redacted)).toBeNull();
    expect(safeVisionCandidate({ action: "SUBMIT", x: 300, y: 200, label: "University", confidence: 0.99 }, viewport, redacted)).toBeNull();
  });
});
