import { describe, expect, it } from "vitest";

import {
  buildResultsQuery,
  buildPriorityResultsQuery,
  canShowSearchRunResults,
  dashboardResultsPath,
  DEFAULT_SEARCH_CRITERIA,
  readDashboardResultsState,
  readActiveSearchId,
  summarizeSearchCriteria,
  writeActiveSearchId,
} from "@/lib/job-search";

describe("job search state", () => {
  it("keeps visible offers until a custom discovery run has finished", () => {
    expect(canShowSearchRunResults({ search_type: "custom", status: "pending" })).toBe(false);
    expect(canShowSearchRunResults({ search_type: "custom", status: "running" })).toBe(false);
    expect(canShowSearchRunResults({ search_type: "custom", status: "completed" })).toBe(true);
    expect(canShowSearchRunResults({ search_type: "custom", status: "partial" })).toBe(true);
    expect(canShowSearchRunResults({ search_type: "custom", status: "failed" })).toBe(false);
    expect(canShowSearchRunResults({ search_type: "general", status: "completed" })).toBe(false);
  });

  it("persists a valid active search in the URL", () => {
    expect(readActiveSearchId("?search=42")).toBe(42);
    expect(readActiveSearchId("?search=invalid")).toBeNull();
    expect(writeActiveSearchId(42)).toBe("/?search=42");
    expect(writeActiveSearchId(null)).toBe("/");
  });

  it("scopes current-result filters without creating search criteria", () => {
    const query = buildResultsQuery(7, {
      q: "Oracle",
      minScore: "80",
      ratingOrder: "highest",
      remoteType: "Remote",
      eligibility: "ELIGIBLE",
      recommendation: "",
      date: "Last 7 days",
      targetGroup: "",
    });
    const params = new URLSearchParams(query.split("?")[1]);
    expect(params.get("search_run_id")).toBe("7");
    expect(params.get("q")).toBe("Oracle");
    expect(params.get("search_fields")).toBe("listing");
    expect(params.get("remote_type")).toBe("Remote");
    expect(params.get("rating_order")).toBe("highest");
  });

  it("filters important opportunities by the same dashboard query", () => {
    const query = buildPriorityResultsQuery({
      q: "google", minScore: "", ratingOrder: "highest", remoteType: "",
      eligibility: "", recommendation: "", date: "Any date", targetGroup: "",
    });
    const params = new URLSearchParams(query.split("?")[1]);
    expect(params.get("q")).toBe("google");
    expect(params.get("search_fields")).toBe("listing");
    expect(params.get("priority")).toBe("true");
    expect(params.get("include_ineligible")).toBe("true");
  });

  it("sends the selected rating order with current-result filters", () => {
    const query = buildResultsQuery(null, {
      q: "",
      minScore: "",
      ratingOrder: "lowest",
      remoteType: "",
      eligibility: "",
      recommendation: "",
      date: "Any date",
      targetGroup: "",
    });
    expect(new URLSearchParams(query.split("?")[1]).get("rating_order")).toBe("lowest");
  });

  it("restores dashboard filters from the same URL used for a job-detail return", () => {
    const filters = {
      q: "Roblox",
      minScore: "80",
      ratingOrder: "lowest" as const,
      remoteType: "Remote",
      eligibility: "ELIGIBLE",
      recommendation: "",
      date: "Last 7 days",
      targetGroup: "Target companies",
    };
    const path = dashboardResultsPath(7, filters);
    expect(readDashboardResultsState(path.split("?")[1] ?? "")).toEqual({
      searchRunId: 7,
      filters,
    });
  });

  it("summarizes a remote LATAM search", () => {
    expect(
      summarizeSearchCriteria({
        ...DEFAULT_SEARCH_CRITERIA,
        work_models: ["REMOTE"],
        remote_scopes: ["MEXICO", "LATAM", "GLOBAL"],
        role_categories: ["SOFTWARE_ENGINEERING", "EMBEDDED_FIRMWARE"],
      }),
    ).toEqual(expect.arrayContaining([
      "Remote: Mexico, LATAM, Global",
      "Roles: Software, Embedded / Firmware",
    ]));
  });
});
