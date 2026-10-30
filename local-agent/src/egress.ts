import { randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { connect, type Socket } from "node:net";
import { authenticate, resolvePublicDestination } from "./security";

/** HTTPS tunnels use the checked numeric IP, so Chromium cannot resolve a
 * different (private) address after validation. TLS remains end-to-end. */
export async function createEgressProxy(
  resolve = resolvePublicDestination,
  open = (host: string, port: number): Socket => connect({ host, port }),
) {
  const key = randomBytes(24).toString("base64url");
  const expected = `Basic ${Buffer.from(`radar:${key}`).toString("base64")}`;
  const sockets = new Set<Socket>();
  const server = createServer((_request, response) => { response.writeHead(403); response.end(); });
  server.on("connection", (socket) => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
  server.on("connect", (request, client, head) => {
    const reject = (status: number) => {
      if (!client.destroyed) client.end(`HTTP/1.1 ${status} Blocked\r\n${status === 407 ? 'Proxy-Authenticate: Basic realm="Internship Radar"\r\n' : ""}Connection: close\r\n\r\n`);
    };
    if (!authenticate(expected, `Bearer ${request.headers["proxy-authorization"] || ""}`)) { reject(407); return; }
    void (async () => {
      try {
        const destination = new URL(`https://${request.url || ""}`);
        if (destination.pathname !== "/" || destination.search || destination.hash) { reject(403); return; }
        const { addresses } = await resolve(destination.href);
        const ip = addresses.find((item) => item.family === 4)?.address || addresses[0].address;
        if (client.destroyed) return;
        const upstream = open(ip, 443);
        sockets.add(upstream);
        upstream.on("close", () => sockets.delete(upstream));
        upstream.setTimeout(10_000, () => upstream.destroy());
        upstream.once("error", () => { reject(502); client.destroy(); });
        client.once("error", () => upstream.destroy());
        client.once("close", () => upstream.destroy());
        upstream.once("connect", () => {
          upstream.setTimeout(0);
          client.write("HTTP/1.1 200 Connection Established\r\n\r\n");
          if (head.length) upstream.write(head);
          client.pipe(upstream); upstream.pipe(client);
        });
      } catch { reject(403); }
    })();
  });
  server.headersTimeout = 10_000;
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject); server.listen(0, "127.0.0.1", () => resolve());
  });
  const port = (server.address() as { port: number }).port;
  return {
    server: `http://127.0.0.1:${port}`, username: "radar", password: key,
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}
