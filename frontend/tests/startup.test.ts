import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import {
  BACKEND_STARTUP_TIMEOUT_MS,
  formatStartupElapsed,
  isRetriableStartupError,
  startupRetryDelayMs,
} from "@/lib/startup";

describe("backend startup status", () => {
  it.each([502, 503, 504])("retries transient HTTP %s responses", (status) => {
    expect(
      isRetriableStartupError(new ApiError("Still waking", status), 5_000),
    ).toBe(true);
  });

  it("retries browser network failures", () => {
    expect(isRetriableStartupError(new TypeError("fetch failed"), 5_000)).toBe(
      true,
    );
  });

  it("retries a short API rate limit using Retry-After", () => {
    const error = new ApiError("Too many requests", 429, 7);
    expect(isRetriableStartupError(error, 5_000)).toBe(true);
    expect(startupRetryDelayMs(error, 5_000)).toBe(7_000);
  });

  it("does not wait past the startup timeout for a rate limit", () => {
    const error = new ApiError("Too many requests", 429, 120);
    expect(isRetriableStartupError(error, 5_000)).toBe(false);
  });

  it("does not retry authentication failures or exceed the startup limit", () => {
    expect(isRetriableStartupError(new ApiError("Unauthorized", 401), 5_000)).toBe(
      false,
    );
    expect(
      isRetriableStartupError(
        new ApiError("Still waking", 503),
        BACKEND_STARTUP_TIMEOUT_MS,
      ),
    ).toBe(false);
  });

  it("formats a stable elapsed-time label", () => {
    expect(formatStartupElapsed(0)).toBe("0.0s");
    expect(formatStartupElapsed(12_345)).toBe("12.3s");
  });
});
