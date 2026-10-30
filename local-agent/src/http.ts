import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { AgentError, authenticate, PORT, validateLaunch, WEB_ORIGINS } from "./security";
import type { LocalBrowserRunner, LocalAction } from "./runner";

async function body(request: IncomingMessage): Promise<unknown> {
  if (Number(request.headers["content-length"]) > 32_000) { request.resume(); throw new AgentError("Request is too large.", 413); }
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 32_000) throw new AgentError("Request is too large.", 413);
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"); }
  catch { throw new AgentError("Invalid request JSON."); }
}

export function createAgentServer(runner: Pick<LocalBrowserRunner, "start" | "action" | "close">, key = randomBytes(24).toString("base64url"), port = PORT) {
  let busy = false;
  const server = createServer(async (request: IncomingMessage, response: ServerResponse) => {
    const send = (status: number, data: unknown) => { response.writeHead(status, { "Content-Type": "application/json" }); response.end(JSON.stringify(data)); };
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("X-Content-Type-Options", "nosniff");
    const origin = request.headers.origin || "";
    const address = server.address();
    const listeningPort = typeof address === "object" && address ? address.port : port;
    if (request.headers.host !== `127.0.0.1:${listeningPort}` || !WEB_ORIGINS.has(origin)) { send(403, { error: "Untrusted local connection." }); return; }
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Vary", "Origin");
    response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    response.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
    response.setHeader("Access-Control-Allow-Private-Network", "true");
    if (request.method === "OPTIONS") { response.writeHead(204); response.end(); return; }
    if (!authenticate(key, request.headers.authorization)) { send(401, { error: "Enter the connection code displayed by the local assistant." }); return; }
    const url = new URL(request.url || "/", `http://127.0.0.1:${port}`);
    if (request.method === "GET" && url.pathname === "/health") { send(200, { ready: true, protocolVersion: 3 }); return; }
    if (request.method !== "POST" || request.headers["content-type"]?.split(";")[0] !== "application/json") { send(405, { error: "Use a JSON POST request." }); return; }
    const cancellation = /^\/sessions\/([a-f0-9-]{36})\/cancel-analysis$/.exec(url.pathname);
    if (cancellation) {
      try { await body(request); send(200, await runner.action(cancellation[1], "cancel-analysis")); }
      catch (error) { send(error instanceof AgentError ? error.status : 500, { error: error instanceof AgentError ? error.message : "No se pudo cancelar la lectura." }); }
      return;
    }
    if (busy) { send(409, { error: "The local assistant is finishing the previous action." }); return; }
    busy = true;
    try {
      const payload = await body(request);
      if (url.pathname === "/disconnect") { await runner.close(); send(200, { closed: true }); return; }
      if (url.pathname === "/sessions") { send(201, await runner.start(validateLaunch(payload, origin))); return; }
      const match = /^\/sessions\/([a-f0-9-]{36})\/(scan|analyze|analyze-local|vision-status|fill|answer|next|confirm-submitted|close|split-screen|capture)$/.exec(url.pathname);
      if (!match) throw new AgentError("Local action not found.", 404);
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new AgentError("Expected a JSON object.");
      send(200, await runner.action(match[1], match[2] as LocalAction, payload as Record<string, unknown>));
    } catch (error) {
      send(error instanceof AgentError ? error.status : 500, { error: error instanceof AgentError ? error.message : "The local browser could not complete the action. Check the browser or restart the helper." });
    } finally { busy = false; }
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  return { server, key };
}
