import { describe, expect, it } from "vitest";

import { displayedJobAction } from "@/lib/job-action";

describe("displayedJobAction", () => {
  it("shows the manual action while retaining the normal analysis", () => {
    const analysis = { recommendation: "Not Eligible" };
    const job = {
      candidate_action_recommendation: "Apply Now",
      analysis,
    } as never;
    expect(displayedJobAction(job)).toBe("Apply Now");
    expect(analysis.recommendation).toBe("Not Eligible");
  });

  it("uses the normal recommendation without a candidate action", () => {
    expect(displayedJobAction({
      candidate_action_recommendation: null,
      analysis: { recommendation: "Review" },
    } as never)).toBe("Review");
  });
});
