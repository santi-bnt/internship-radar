import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearRouteDataCache,
  readRouteData,
  ROUTE_DATA_CACHE_TTL_MS,
  writeRouteData,
} from "@/lib/route-data-cache";

describe("route data cache", () => {
  afterEach(() => {
    clearRouteDataCache();
    vi.useRealTimers();
  });

  it("restores only data stored for the exact route key", () => {
    writeRouteData("jobs-list:/jobs?country=Canada", { total: 4 });
    writeRouteData("jobs-list:/jobs?country=Mexico", { total: 7 });

    expect(readRouteData<{ total: number }>("jobs-list:/jobs?country=Canada")).toEqual({ total: 4 });
    expect(readRouteData("jobs-list:/jobs?country=United+States")).toBeNull();
  });

  it("expires cached results so the API remains the source of truth", () => {
    vi.useFakeTimers();
    writeRouteData("dashboard:/?rating_order=highest", { total: 4 });
    vi.advanceTimersByTime(ROUTE_DATA_CACHE_TTL_MS + 1);

    expect(readRouteData("dashboard:/?rating_order=highest")).toBeNull();
  });
});
