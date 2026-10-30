import { describe, expect, it } from "vitest";

import {
  portalPermissionOrigins,
  trustedGreenhouseEmbedUrl,
} from "../src/shared/portalNavigation";

describe("embedded career portal navigation", () => {
  it("requests only Zipline and its Greenhouse application origin", () => {
    expect(portalPermissionOrigins("https://www.zipline.com/open-roles/7904518003")).toEqual([
      "https://www.zipline.com/*",
      "https://boards.greenhouse.io/*",
    ]);
    expect(portalPermissionOrigins("https://careers.example.com/jobs/123")).toEqual([
      "https://careers.example.com/*",
    ]);
  });

  it("accepts the exact Greenhouse application and rejects lookalike URLs", () => {
    const valid = "https://boards.greenhouse.io/embed/job_app?for=flyzipline&token=7904518003";
    expect(trustedGreenhouseEmbedUrl(valid)).toBe(valid);
    expect(trustedGreenhouseEmbedUrl("https://boards.greenhouse.io/embed/job_app?for=flyzipline")).toBeNull();
    expect(trustedGreenhouseEmbedUrl("https://boards.greenhouse.io.example.com/embed/job_app?for=flyzipline&token=7904518003")).toBeNull();
    expect(trustedGreenhouseEmbedUrl("https://boards.greenhouse.io/jobs/7904518003?for=flyzipline&token=7904518003")).toBeNull();
  });
});
