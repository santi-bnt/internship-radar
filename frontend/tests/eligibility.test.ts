import { describe, expect, it } from "vitest";

import { appendEligibilityFilters, primaryEligibilityReason } from "@/lib/eligibility";
import type { Job } from "@/lib/types";

describe("eligibility filters", () => {
  it("keeps hard-ineligible jobs hidden by default", () => {
    const params = appendEligibilityFilters(new URLSearchParams(), {
      showIneligible: false,
      eligibility: [],
      remoteScopes: [],
      sponsorship: [],
    });
    expect(params.has("include_ineligible")).toBe(false);
  });

  it("only requests hard-ineligible jobs when the user enables the switch", () => {
    const params = appendEligibilityFilters(new URLSearchParams(), {
      showIneligible: true,
      eligibility: ["NOT_ELIGIBLE"],
      remoteScopes: ["US_ONLY"],
      sponsorship: ["NOT_AVAILABLE"],
    });
    expect(params.get("include_ineligible")).toBe("true");
    expect(params.get("eligibility")).toBe("NOT_ELIGIBLE");
    expect(params.get("remote_scope")).toBe("US_ONLY");
    expect(params.get("sponsorship")).toBe("NOT_AVAILABLE");
  });

  it("shows the first hard blocker prominently", () => {
    const job = {
      analysis: {
        eligibility_status: "NOT_ELIGIBLE",
        blocker_reasons: ["U.S. work authorization required and employer indicates sponsorship is unavailable."],
      },
    } as unknown as Pick<Job, "analysis">;
    expect(primaryEligibilityReason(job)).toContain("sponsorship is unavailable");
  });
});
