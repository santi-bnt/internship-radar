import { describe, expect, it } from "vitest";
import { authenticate, isPublicAddress, validateLaunch, validatePortalUrl } from "../src/security";
import type { lookup } from "node:dns/promises";

const origin = "https://your-app.vercel.app";
const launch = () => ({ sessionId: 4, token: "a".repeat(32), expiresAt: new Date(Date.now() + 60_000).toISOString(), apiBaseUrl: `${origin}/api/backend`, applicationUrl: "https://careers.example.com/apply" });

describe("local browser security", () => {
  it.each(["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.1.2", "169.254.169.254", "::1", "::ffff:127.0.0.1", "fc00::1", "fe80::1", "0.0.0.0"])("blocks private or reserved address %s", (address) => {
    expect(isPublicAddress(address)).toBe(false);
  });
  it("accepts public addresses and requires the exact local connection key", () => {
    expect(isPublicAddress("8.8.8.8")).toBe(true);
    expect(authenticate("secret-key", "Bearer secret-key")).toBe(true);
    expect(authenticate("secret-key", "Bearer another-key")).toBe(false);
  });
  it("validates all DNS addresses and rejects unsafe URLs before browsing", async () => {
    const mixed = (async () => [{ address: "8.8.8.8", family: 4 }, { address: "127.0.0.1", family: 4 }]) as unknown as typeof lookup;
    await expect(validatePortalUrl("https://example.com/apply", mixed)).rejects.toThrow("network addresses");
    for (const value of ["file:///etc/passwd", "http://example.com", "https://localhost", "https://render.internal", "https://user:password@example.com", "https://example.com:9999"]) {
      await expect(validatePortalUrl(value, mixed)).rejects.toThrow();
    }
  });
  it("accepts only a scoped session from the connected web application", () => {
    expect(validateLaunch(launch(), origin).sessionId).toBe(4);
    expect(() => validateLaunch({ ...launch(), apiBaseUrl: "http://169.254.169.254/api/backend" }, origin)).toThrow("connected Internship Radar");
    expect(() => validateLaunch({ ...launch(), expiresAt: "2020-01-01" }, origin)).toThrow("expired");
    expect(() => validateLaunch(launch(), "https://evil.example")).toThrow();
  });
});
