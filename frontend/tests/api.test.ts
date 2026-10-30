import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API errors", () => {
  it("keeps the provider message and Retry-After for a 429 response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Too many requests. Try again later." }), {
          status: 429,
          statusText: "Too Many Requests",
          headers: { "content-type": "application/json", "retry-after": "7" },
        }),
      ),
    );

    await expect(api("/api/stats")).rejects.toMatchObject({
      name: "ApiError",
      message: "Too many requests. Try again later.",
      status: 429,
      retryAfterSeconds: 7,
    } satisfies Partial<ApiError>);
  });

  it("does not expose a non-string error payload as a raw dashboard message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 429 }), {
          status: 429,
          statusText: "Too Many Requests",
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(api("/api/stats")).rejects.toMatchObject({
      message: "429 Too Many Requests",
      status: 429,
    });
  });
});
