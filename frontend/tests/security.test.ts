import { createHmac } from "node:crypto";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { isAppAccessEnabled, isPublicDemoMode } from "@/lib/access";
import { frameSecurityPolicy } from "@/lib/frame-policy";
import {
  authorizedEmails,
  isAuthorizedEmail,
  normalizeEmail,
  resolvePrimaryUser,
} from "@/lib/identity";
import { removeItemOptimistically } from "@/lib/jobs-state";
import { checkRateLimit } from "@/lib/rate-limit";
import { createUserIdentityToken } from "@/lib/user-identity-token";

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  process.env.AUTHORIZED_USER_EMAILS =
    "candidate@example.com,alerts@example.com,alternate@example.com";
  process.env.PRIMARY_USER_ID = "internship-radar-primary";
  process.env.USER_IDENTITY_SIGNING_SECRET = "unit-test-signing-secret";
  process.env.APP_ACCESS_ENABLED = "false";
  process.env.PUBLIC_DEMO_MODE = "false";
  process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE = "false";
});

afterEach(() => {
  process.env = { ...ORIGINAL_ENV };
});

describe("authorized identity", () => {
  it("normalizes and exactly matches only configured emails", () => {
    expect(normalizeEmail("  CANDIDATE@EXAMPLE.COM ")).toBe("candidate@example.com");
    expect(authorizedEmails().size).toBe(3);
    expect(isAuthorizedEmail("candidate@example.com")).toBe(true);
    expect(isAuthorizedEmail("alerts@example.com")).toBe(true);
    expect(isAuthorizedEmail("alternate@example.com")).toBe(true);
    expect(isAuthorizedEmail("attacker+candidate@example.com")).toBe(false);
    expect(isAuthorizedEmail("fake-alerts@example.com")).toBe(false);
    expect(isAuthorizedEmail("candidate@example.com.attacker.test")).toBe(false);
  });

  it("maps all three login accounts to one stable user", () => {
    for (const email of authorizedEmails()) {
      expect(resolvePrimaryUser(email)).toBe("internship-radar-primary");
    }
    expect(resolvePrimaryUser("attacker@example.com")).toBeNull();
  });
});

describe("signed BFF identity", () => {
  it("contains a short-lived scoped payload and a valid HMAC", () => {
    const token = createUserIdentityToken(
      "internship-radar-primary",
      "CANDIDATE@EXAMPLE.COM",
    );
    const [encoded, signature] = token.split(".");
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    const expected = createHmac("sha256", "unit-test-signing-secret")
      .update(encoded)
      .digest("base64url");

    expect(signature).toBe(expected);
    expect(payload.sub).toBe("internship-radar-primary");
    expect(payload.email).toBe("candidate@example.com");
    expect(payload.aud).toBe("internship-radar-api");
    expect(payload.purpose).toBe("user_request");
    expect(payload.exp - payload.iat).toBe(60);
    expect(token).not.toContain("unit-test-signing-secret");
  });
});

describe("server-side access and abuse controls", () => {
  it("fails closed unless access is explicitly true", () => {
    expect(isAppAccessEnabled()).toBe(false);
    delete process.env.APP_ACCESS_ENABLED;
    expect(isAppAccessEnabled()).toBe(false);
    process.env.APP_ACCESS_ENABLED = "TRUE";
    expect(isAppAccessEnabled()).toBe(true);
  });

  it("enables public demo mode only through an explicit flag", () => {
    expect(isPublicDemoMode()).toBe(false);
    process.env.PUBLIC_DEMO_MODE = "TRUE";
    expect(isPublicDemoMode()).toBe(true);
  });

  it("rate-limits by authenticated primary user", () => {
    const rule = { key: "unit-test", limit: 2, windowMs: 60_000 };
    expect(checkRateLimit("user-a", rule).allowed).toBe(true);
    expect(checkRateLimit("user-a", rule).allowed).toBe(true);
    expect(checkRateLimit("user-a", rule).allowed).toBe(false);
    expect(checkRateLimit("user-b", rule).allowed).toBe(true);
  });
});

describe("frame security policy", () => {
  it("allows only proxied generated PDFs in the same-origin resume viewer", () => {
    expect(
      frameSecurityPolicy("/api/backend/api/generated-resumes/42/pdf"),
    ).toEqual({
      xFrameOptions: "SAMEORIGIN",
      contentSecurityPolicy: "frame-ancestors 'self'",
    });
  });

  it("continues blocking every other page and backend response from frames", () => {
    expect(frameSecurityPolicy("/jobs/42")).toEqual({
      xFrameOptions: "DENY",
      contentSecurityPolicy: "frame-ancestors 'none'",
    });
    expect(
      frameSecurityPolicy("/api/backend/api/generated-resumes/42/tex"),
    ).toEqual({
      xFrameOptions: "DENY",
      contentSecurityPolicy: "frame-ancestors 'none'",
    });
  });
});

describe("optimistic application state", () => {
  it("removes an applied job immediately and updates its counter", () => {
    const current = {
      items: [{ id: 1, title: "Intern" }, { id: 2, title: "Co-op" }],
      total: 2,
    };
    expect(removeItemOptimistically(current, 1)).toEqual({
      items: [{ id: 2, title: "Co-op" }],
      total: 1,
    });
  });
});
