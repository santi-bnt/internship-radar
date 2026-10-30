import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { request as httpRequest, type Server } from "node:http";
import { createAgentServer } from "../src/http";

const origin = "http://localhost:3000";
const key = "random-local-test-key";
const launch = { sessionId: 4, token: "a".repeat(32), expiresAt: new Date(Date.now() + 600_000).toISOString(), apiBaseUrl: `${origin}/api/backend`, applicationUrl: "https://careers.example.com/apply" };

describe("loopback control API", () => {
  let server: Server;
  let base: string;
  const runner = { start: vi.fn(), action: vi.fn(), close: vi.fn() };
  const headers = { Origin: origin, Host: "127.0.0.1:43123", Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
  beforeEach(async () => {
    vi.resetAllMocks();
    runner.start.mockResolvedValue({ id: "12345678-abcd-1234-abcd-123456789000" });
    runner.action.mockResolvedValue({ fields: [] });
    server = createAgentServer(runner, key, 0).server;
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address() as { port: number };
    base = `http://127.0.0.1:${address.port}`;
  });
  afterEach(async () => { await new Promise<void>((resolve) => server.close(() => resolve())); });

  it("supports authenticated pairing and browser private-network preflight", async () => {
    const preflight = await fetch(`${base}/sessions`, { method: "OPTIONS", headers: { Origin: origin, Host: headers.Host } });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-private-network")).toBe("true");
    const health = await fetch(`${base}/health`, { headers });
    expect(health.status).toBe(200);
    expect(await health.json()).toMatchObject({ ready: true, protocolVersion: 3 });
    const response = await fetch(`${base}/sessions`, { method: "POST", headers, body: JSON.stringify(launch) });
    expect(response.status).toBe(201);
    expect(runner.start).toHaveBeenCalledWith(launch);
    expect(JSON.stringify(await response.json())).not.toContain(launch.token);
  });
  it("rejects remote origins, missing keys and DNS-rebinding hosts", async () => {
    for (const changed of [{ Origin: "https://evil.example" }, { Authorization: "" }]) {
      const response = await fetch(`${base}/sessions`, { method: "POST", headers: { ...headers, ...changed }, body: JSON.stringify(launch) });
      expect([401, 403]).toContain(response.status);
    }
    const badHostStatus = await new Promise<number>((resolve) => {
      const request = httpRequest(`${base}/health`, { headers: { ...headers, Host: "attacker.example:43123" } }, (response) => {
        response.resume(); resolve(response.statusCode || 0);
      });
      request.end();
    });
    expect(badHostStatus).toBe(403);
    expect(runner.start).not.toHaveBeenCalled();
  });
  it("exposes only specific actions and rejects oversized input", async () => {
    expect((await fetch(`${base}/sessions/12345678-abcd-1234-abcd-123456789000/evaluate`, { method: "POST", headers, body: "{}" })).status).toBe(404);
    expect((await fetch(`${base}/sessions`, { method: "POST", headers, body: JSON.stringify({ text: "x".repeat(33_000) }) })).status).toBe(413);
    expect(runner.action).not.toHaveBeenCalled();
  });
  it("serializes browser operations instead of applying commands concurrently", async () => {
    let finish: (value: { id: string }) => void = () => undefined;
    runner.start.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = fetch(`${base}/sessions`, { method: "POST", headers, body: JSON.stringify(launch) });
    await vi.waitFor(() => expect(runner.start).toHaveBeenCalled());
    const second = await fetch(`${base}/sessions`, { method: "POST", headers, body: JSON.stringify(launch) });
    expect(second.status).toBe(409);
    finish({ id: "finished" });
    expect((await pending).status).toBe(201);
  });
  it("allows authenticated cancellation while an inference action is running", async () => {
    let finish: (value: unknown) => void = () => undefined;
    runner.action.mockImplementation((_id: string, action: string) => action === "cancel-analysis"
      ? Promise.resolve({ cancelled: true }) : new Promise((resolve) => { finish = resolve; }));
    const pending = fetch(`${base}/sessions/12345678-abcd-1234-abcd-123456789000/analyze-local`, { method: "POST", headers, body: "{}" });
    await vi.waitFor(() => expect(runner.action).toHaveBeenCalled());
    const cancelled = await fetch(`${base}/sessions/12345678-abcd-1234-abcd-123456789000/cancel-analysis`, { method: "POST", headers, body: "{}" });
    expect(cancelled.status).toBe(200);
    expect(await cancelled.json()).toEqual({ cancelled: true });
    finish({ fields: [] });
    expect((await pending).status).toBe(200);
  });
});
