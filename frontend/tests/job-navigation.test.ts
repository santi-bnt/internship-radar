import { describe, expect, it } from "vitest";

import { jobDetailHref, jobListReturnPath, safeJobListPath } from "@/lib/job-navigation";
import { jobsListPath, readJobsListState } from "@/lib/jobs-list-state";

function returnPathFromDetail(detailHref: string): string {
  return jobListReturnPath(detailHref.split("?")[1] ?? "");
}

function stateFromPath(path: string) {
  return readJobsListState(new URL(path, "https://internship-radar.local").search);
}

describe("job-list navigation state", () => {
  it("does not silently hide jobs with unknown country metadata by default", () => {
    const state = readJobsListState("");
    expect(state.filters.countries).toEqual([]);
    expect(jobsListPath(state)).toContain("country_any=true");
  });

  it("keeps a Canada filter after opening a job and returning", () => {
    const listPath = "/jobs?country=Canada&rating_order=highest";
    expect(returnPathFromDetail(jobDetailHref(101, listPath))).toBe(listPath);
    expect(stateFromPath(listPath).filters.countries).toEqual(["Canada"]);
  });

  it("preserves multiple filters exactly through a job detail route", () => {
    const state = readJobsListState("?country=Canada&country=Mexico&company=Roblox&area=Software+%2F+SDE&eligibility=ELIGIBLE&recommendation=Apply+Now&rating_order=lowest&q=platform");
    const listPath = jobsListPath(state);
    const restored = stateFromPath(returnPathFromDetail(jobDetailHref(102, listPath)));

    expect(restored.filters.countries).toEqual(["Canada", "Mexico"]);
    expect(restored.companyFilter).toBe("Roblox");
    expect(restored.filters.areas).toEqual(["Software / SDE"]);
    expect(restored.filters.eligibility).toEqual(["ELIGIBLE"]);
    expect(restored.filters.statuses).toEqual(["Apply Now"]);
    expect(restored.ratingOrder).toBe("lowest");
    expect(restored.filters.q).toBe("platform");
  });

  it("preserves filters, rating sort, and pagination", () => {
    const listPath = "/jobs?country=Canada&remote_type=Remote&rating_order=lowest&page=3";
    const restored = stateFromPath(returnPathFromDetail(jobDetailHref(103, listPath)));
    expect(restored.filters.countries).toEqual(["Canada"]);
    expect(restored.filters.arrangements).toEqual(["Remote"]);
    expect(restored.ratingOrder).toBe("lowest");
    expect(restored.page).toBe(3);
  });

  it("keeps an intentionally empty country selection as all countries", () => {
    const state = readJobsListState("?country=Canada");
    state.filters.countries = [];
    const path = jobsListPath(state);
    expect(path).toContain("country_any=true");
    expect(stateFromPath(path).filters.countries).toEqual([]);
  });

  it("uses the prior URL for browser Back instead of falling back to default jobs", () => {
    const listPath = "/jobs?company=Roblox&q=intern&rating_order=highest";
    const detailPath = jobDetailHref(104, listPath);
    expect(returnPathFromDetail(detailPath)).toBe(listPath);
  });

  it("does not mutate the original list path when a job is opened in a new tab", () => {
    const originalListPath = "/jobs?country=Canada&company=Roblox&rating_order=highest";
    const newTabPath = jobDetailHref(105, originalListPath);
    expect(originalListPath).toBe("/jobs?country=Canada&company=Roblox&rating_order=highest");
    expect(returnPathFromDetail(newTabPath)).toBe(originalListPath);
  });

  it("rejects external or unrelated return destinations", () => {
    expect(safeJobListPath("https://example.com")).toBe("/jobs");
    expect(safeJobListPath("/profile")).toBe("/jobs");
  });

  it("keeps the Archived tab selected when opening a hidden job and returning", () => {
    const path = jobsListPath(readJobsListState("?lifecycle=archived&company=Five+Rings"));
    expect(stateFromPath(returnPathFromDetail(jobDetailHref(5394515008, path))).lifecycleStatus).toBe("archived");
  });
});
