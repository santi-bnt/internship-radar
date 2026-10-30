import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import JobDetailPage from "@/app/jobs/[id]/page";

const state = vi.hoisted(() => ({ job: {} as Record<string, unknown>, calls: 0 }));
vi.mock("react", async (importOriginal) => {
  const original = await importOriginal<typeof import("react")>();
  return {
    ...original,
    useState: (initial: unknown) => [state.calls++ === 0 ? state.job : initial, () => {}],
  };
});
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "702" }),
  useRouter: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("next/link", () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/ApplyAssistantButton", () => ({ default: () => null }));
vi.mock("@/components/RecommendedResumeSection", () => ({
  default: () => React.createElement("button", null, "Generate Resume"),
}));

describe("job resume visibility", () => {
  beforeEach(() => {
    state.calls = 0;
    state.job = {
      id: 702, company: "Google", title: "Software Engineering Intern, BS, Summer 2027",
      status: "active", remote_scope: "US_ONLY", special_program_type: "NONE",
      verification_status: "verified", verification_method: "official_careers_page",
      sponsorship_status: "UNKNOWN", discovery_sources: ["Google Careers"],
      community_sponsorship_signal: "UNKNOWN",
      description: "Software development", requirements: "Python and algorithms",
      apply_url: "https://www.google.com/about/careers/applications/jobs/results/702",
      analysis: {
        eligibility_status: "NOT_ELIGIBLE", recommendation: "Not Eligible",
        blocker_reasons: ["Work authorization requires verification."],
        positive_reasons: [], risk_flags: [],
        education_eligibility_status: "UNKNOWN", degree_level_match: "UNKNOWN",
        degree_field_match: "UNKNOWN", degree_completion_match: "UNKNOWN",
        student_status_match: "UNKNOWN", special_program_eligibility_status: "UNKNOWN",
        graduation_window_match: "UNKNOWN",
      },
    };
  });

  it("shows the CV workspace for an ineligible Google job without removing its warning", () => {
    const html = renderToStaticMarkup(React.createElement(JobDetailPage));
    expect(html).toContain("Generate Resume");
    expect(html).toContain("Not eligible:");
    expect(html).toContain("Work authorization requires verification.");
    expect(html).toContain("Generating a resume does not confirm eligibility");
  });

  it("also shows the CV workspace before eligibility has been analyzed", () => {
    state.job.analysis = null;
    const html = renderToStaticMarkup(React.createElement(JobDetailPage));
    expect(html).toContain("Generate Resume");
    expect(html).not.toContain("Generating a resume does not confirm eligibility");
  });
});
