import { describe, expect, it } from "vitest";

import { buildExtensionEndpoint } from "../src/api/client";
import type { StoredApplicationSession } from "../src/shared/types";

const session: StoredApplicationSession = {
  sessionId: 1,
  token: "token",
  expiresAt: "2099-01-01T00:00:00Z",
  apiBaseUrl: "https://your-app.vercel.app/api/backend",
  applicationUrl: "https://example.wd1.myworkdayjobs.com/job/REQ-1"
};

describe("extension API URL", () => {
  it("keeps extension requests behind the public BFF path", () => {
    expect(buildExtensionEndpoint(session, "/api/extension/application-session")).toBe(
      "https://your-app.vercel.app/api/backend/api/extension/application-session",
    );
  });

  it("allows HTTP only for local development", () => {
    expect(buildExtensionEndpoint({ ...session, apiBaseUrl: "http://localhost:3000/api/backend" }, "/api/extension/application-session"))
      .toBe("http://localhost:3000/api/backend/api/extension/application-session");
    expect(() => buildExtensionEndpoint({ ...session, apiBaseUrl: "http://example.com/api/backend" }, "/api/extension/application-session"))
      .toThrow("Insecure Internship Radar API URL");
  });
});
