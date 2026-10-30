import type { ApplicationAgentPlan, ExtensionPayload, StoredApplicationSession } from "../shared/types";

export class ExtensionApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ExtensionApiError";
  }
}

export function buildExtensionEndpoint(session: StoredApplicationSession, path: string): string {
  const base = new URL(session.apiBaseUrl);
  if (!["https:", "http:"].includes(base.protocol)) throw new ExtensionApiError("Invalid Internship Radar API URL.", 0);
  if (base.protocol === "http:" && base.hostname !== "localhost" && base.hostname !== "127.0.0.1") {
    throw new ExtensionApiError("Insecure Internship Radar API URL.", 0);
  }
  const joined = `${base.href.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
  const result = new URL(joined);
  if (result.origin !== base.origin) throw new ExtensionApiError("Application Session API origin mismatch.", 0);
  return result.href;
}

async function request<T>(session: StoredApplicationSession, path: string, init?: RequestInit): Promise<T> {
  if (Date.parse(session.expiresAt) <= Date.now()) throw new ExtensionApiError("Application session token expired. Reconnect from Internship Radar.", 401);
  const response = await fetch(buildExtensionEndpoint(session, path), {
    ...init,
    headers: {
      Authorization: `Bearer ${session.token}`,
      "Content-Type": "application/json",
      ...init?.headers
    },
    cache: "no-store",
    credentials: "omit",
    redirect: "error"
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json() as { detail?: string }).detail || message; } catch { /* use safe status */ }
    throw new ExtensionApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const extensionApi = {
  payload: (session: StoredApplicationSession) => request<ExtensionPayload>(session, "/api/extension/application-session"),
  analyzePage: (session: StoredApplicationSession, payload: Record<string, unknown>) => request<ApplicationAgentPlan>(session, "/api/extension/application-session/agent/analyze", { method: "POST", body: JSON.stringify(payload) }),
  approveMapping: (session: StoredApplicationSession, payload: Record<string, unknown>) => request(session, "/api/extension/application-session/agent/approve-mapping", { method: "POST", body: JSON.stringify(payload) }),
  progress: (session: StoredApplicationSession, payload: Record<string, unknown>) => request(session, "/api/extension/application-session/progress", { method: "PATCH", body: JSON.stringify(payload) }),
  confirmAnswer: (session: StoredApplicationSession, payload: Record<string, unknown>) => request(session, "/api/extension/application-session/confirm-answer", { method: "POST", body: JSON.stringify(payload) }),
  confirmSubmitted: (session: StoredApplicationSession, payload: { confirmation_text: string; confirmation_url: string }) => request(session, "/api/extension/application-session/confirm-submitted", { method: "POST", body: JSON.stringify(payload) }),
  resume: async (session: StoredApplicationSession): Promise<{ bytes: ArrayBuffer; disposition: string }> => {
    const response = await fetch(buildExtensionEndpoint(session, "/api/extension/application-session/resume.pdf"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
      credentials: "omit",
      redirect: "error"
    });
    if (!response.ok) throw new ExtensionApiError(`Resume download failed (${response.status}).`, response.status);
    return { bytes: await response.arrayBuffer(), disposition: response.headers.get("content-disposition") || "" };
  },
  portfolio: async (session: StoredApplicationSession): Promise<{ bytes: ArrayBuffer; disposition: string }> => {
    const response = await fetch(buildExtensionEndpoint(session, "/api/extension/application-session/portfolio.pdf"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
      credentials: "omit",
      redirect: "error"
    });
    if (!response.ok) throw new ExtensionApiError(`Project Portfolio download failed (${response.status}).`, response.status);
    return { bytes: await response.arrayBuffer(), disposition: response.headers.get("content-disposition") || "" };
  }
};
