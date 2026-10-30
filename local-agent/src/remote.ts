import type { StoredApplicationSession } from "../../extension/src/shared/types";
import { AgentError } from "./security";

/** The local browser never receives the scoped backend token. */
export class SessionApi {
  constructor(private readonly session: StoredApplicationSession) {}

  async request(path: string, init?: RequestInit, maxBytes = 2_000_000): Promise<Uint8Array> {
    if (Date.parse(this.session.expiresAt) <= Date.now()) throw new AgentError("Application session expired. Reconnect from Internship Radar.", 401);
    const response = await fetch(`${this.session.apiBaseUrl}/api/extension/application-session${path}`, {
      ...init, headers: { "Content-Type": "application/json", ...init?.headers, Authorization: `Bearer ${this.session.token}` },
      signal: AbortSignal.timeout(30_000), redirect: "error", credentials: "omit",
    });
    if (!response.ok) throw new AgentError(`The application service returned ${response.status}. Reconnect or try again.`, response.status === 401 ? 401 : 502);
    if (Number(response.headers.get("content-length")) > maxBytes) throw new AgentError("Application response exceeded the size limit.", 502);
    const reader = response.body?.getReader();
    if (!reader) throw new AgentError("Empty application response.", 502);
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > maxBytes) throw new AgentError("Application response exceeded the size limit.", 502);
        chunks.push(value);
      }
    } finally { await reader.cancel().catch(() => undefined); }
    return Buffer.concat(chunks);
  }

  async json<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
    return JSON.parse(Buffer.from(await this.request(path, body === undefined ? undefined : {
      method, body: JSON.stringify(body),
    })).toString("utf8")) as T;
  }

  async resume(): Promise<Uint8Array> {
    const bytes = await this.request("/resume.pdf", undefined, 20_000_000);
    if (Buffer.from(bytes.subarray(0, 5)).toString() !== "%PDF-") throw new AgentError("The session CV is not a valid PDF.", 502);
    return bytes;
  }
}
