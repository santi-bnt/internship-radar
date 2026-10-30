import { afterEach, describe, expect, it, vi } from "vitest";
import { connect, Socket } from "node:net";
import { createEgressProxy } from "../src/egress";
import type { resolvePublicDestination } from "../src/security";

describe("pinned-IP browser egress", () => {
  let proxy: Awaited<ReturnType<typeof createEgressProxy>> | undefined;
  afterEach(async () => { await proxy?.close(); });
  async function tunnel(host: string, authorization?: string): Promise<string> {
    const target = new URL(proxy!.server);
    return new Promise((resolve, reject) => {
      const client = connect(Number(target.port), "127.0.0.1", () => {
        client.write(`CONNECT ${host}:443 HTTP/1.1\r\nHost: ${host}:443\r\n${authorization ? `Proxy-Authorization: ${authorization}\r\n` : ""}\r\n`);
      });
      client.once("data", (data) => { resolve(data.toString()); client.destroy(); });
      client.once("error", reject);
    });
  }
  it("connects to the approved numeric IP rather than resolving the hostname a second time", async () => {
    const resolve = vi.fn().mockResolvedValueOnce({ url: new URL("https://host.example"), addresses: [{ address: "8.8.8.8", family: 4 }] })
      .mockResolvedValueOnce({ url: new URL("https://host.example"), addresses: [{ address: "127.0.0.1", family: 4 }] });
    const open = vi.fn(() => {
      const socket = new Socket();
      queueMicrotask(() => socket.emit("connect"));
      return socket;
    });
    proxy = await createEgressProxy(resolve as unknown as typeof resolvePublicDestination, open);
    const auth = `Basic ${Buffer.from(`${proxy.username}:${proxy.password}`).toString("base64")}`;
    expect(await tunnel("host.example", auth)).toContain("200 Connection Established");
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith("8.8.8.8", 443);
  });
  it("does not open private destinations or unauthenticated tunnels", async () => {
    const resolve = vi.fn().mockRejectedValue(new Error("Private destination"));
    const open = vi.fn();
    proxy = await createEgressProxy(resolve as unknown as typeof resolvePublicDestination, open);
    expect(await tunnel("host.example")).toContain("407");
    const auth = `Basic ${Buffer.from(`${proxy.username}:${proxy.password}`).toString("base64")}`;
    expect(await tunnel("localhost", auth)).toContain("403");
    expect(open).not.toHaveBeenCalled();
  });
});
