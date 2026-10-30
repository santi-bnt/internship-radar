import { afterEach, describe, expect, it, vi } from "vitest";
import { checkLocalAssistant, localAssistant, localLaunchPayload, startLocalApplication } from "../lib/local-assistant";
import type { ApplicationSessionLaunch } from "../lib/types";

afterEach(() => vi.unstubAllGlobals());

describe("local assistant connection", () => {
  it("requires the current page-reading helper instead of silently pairing with an old running process", async () => {
    const request = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ ready: true, protocolVersion: 1 })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ready: true, protocolVersion: 3 })));
    vi.stubGlobal("fetch", request);
    await expect(checkLocalAssistant("local-key")).rejects.toThrow("versión anterior");
    await expect(checkLocalAssistant("local-key")).resolves.toBeUndefined();
  });
  it("uses a scoped backend session and the current site API", () => {
    const launch = { session: { id: 3, application_url: "https://careers.example.com/apply" }, application_session_token: "scoped-token", token_expires_at: "2026-12-01" } as ApplicationSessionLaunch;
    expect(localLaunchPayload(launch, "https://your-app.vercel.app")).toEqual({
      sessionId: 3, token: "scoped-token", expiresAt: "2026-12-01", apiBaseUrl: "https://your-app.vercel.app/api/backend", applicationUrl: launch.session.application_url,
    });
  });
  it("connects only to the fixed loopback helper and sends no browser cookies", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ready: true })));
    vi.stubGlobal("fetch", request);
    await localAssistant("local-key", "/health");
    expect(request).toHaveBeenCalledWith("http://127.0.0.1:43123/health", expect.objectContaining({
      credentials: "omit", redirect: "error", headers: { Authorization: "Bearer local-key" },
    }));
  });
  it("surfaces connection errors instead of silently requiring an extension", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Connection code is invalid" }), { status: 401 })));
    await expect(localAssistant("bad", "/health")).rejects.toThrow("Connection code is invalid");
  });
  it("closes a late browser launch when the user has switched jobs", async () => {
    let finish: (response: Response) => void = () => undefined;
    let current = true;
    const request = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ closed: true })));
    vi.stubGlobal("fetch", request);
    const launch = { session: { id: 3, application_url: "https://careers.example.com/apply" }, application_session_token: "scoped-token", token_expires_at: "2026-12-01" } as ApplicationSessionLaunch;
    const pending = startLocalApplication("local-key", launch, "http://localhost:3000", () => current);
    current = false;
    finish(new Response(JSON.stringify({ id: "old-job-session" })));
    expect(await pending).toBeNull();
    expect(request).toHaveBeenLastCalledWith("http://127.0.0.1:43123/sessions/old-job-session/close", expect.objectContaining({ method: "POST" }));
  });
});
