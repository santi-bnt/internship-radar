import type { ApplicationSessionLaunch } from "./types";
export type { AssistantPageState, AgentFieldResolution } from "../../extension/src/shared/types";

const LOCAL_URL = "http://127.0.0.1:43123";

export async function checkLocalAssistant(key: string): Promise<void> {
  const health = await localAssistant<{ ready?: boolean; protocolVersion?: number }>(key, "/health", undefined, AbortSignal.timeout(4000));
  if (!health.ready || !health.protocolVersion || health.protocolVersion < 3) {
    throw new Error("El asistente local sigue ejecutando una versión anterior. Ciérralo con Ctrl+C, vuelve a ejecutar .\\start-local-assistant.ps1 y pega el nuevo código de conexión.");
  }
}

export async function localAssistant<T>(key: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${LOCAL_URL}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${key.trim()}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit", redirect: "error", cache: "no-store", signal: signal || AbortSignal.timeout(90_000),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "The local assistant could not complete this action.");
  return result as T;
}

export function localLaunchPayload(launch: ApplicationSessionLaunch, origin: string) {
  return {
    sessionId: launch.session.id, token: launch.application_session_token, expiresAt: launch.token_expires_at,
    apiBaseUrl: `${origin}/api/backend`, applicationUrl: launch.session.application_url,
  };
}

export async function startLocalApplication(
  key: string, launch: ApplicationSessionLaunch, origin: string, isCurrent: () => boolean,
): Promise<{ id: string; key: string } | null> {
  const result = await localAssistant<{ id: string }>(key, "/sessions", localLaunchPayload(launch, origin));
  if (!isCurrent()) {
    await localAssistant(key, `/sessions/${result.id}/close`, {}).catch(() => undefined);
    return null;
  }
  return { id: result.id, key: key.trim() };
}
