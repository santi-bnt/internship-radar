import { ApiError } from "@/lib/api";

export const BACKEND_STARTUP_TIMEOUT_MS = 90_000;
export const BACKEND_STARTUP_RETRY_DELAY_MS = 3_000;

const RETRIABLE_STARTUP_STATUSES = new Set([502, 503, 504]);

export function isRetriableStartupError(
  error: unknown,
  elapsedMs: number,
): boolean {
  if (elapsedMs >= BACKEND_STARTUP_TIMEOUT_MS) return false;
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return (
        elapsedMs + startupRetryDelayMs(error, elapsedMs) <
        BACKEND_STARTUP_TIMEOUT_MS
      );
    }
    return RETRIABLE_STARTUP_STATUSES.has(error.status);
  }
  return error instanceof TypeError;
}

export function startupRetryDelayMs(
  error: unknown,
  elapsedMs: number,
): number {
  const remainingMs = Math.max(0, BACKEND_STARTUP_TIMEOUT_MS - elapsedMs);
  const requestedDelayMs =
    error instanceof ApiError &&
    error.status === 429 &&
    error.retryAfterSeconds !== null
      ? error.retryAfterSeconds * 1000
      : BACKEND_STARTUP_RETRY_DELAY_MS;
  return Math.min(Math.max(BACKEND_STARTUP_RETRY_DELAY_MS, requestedDelayMs), remainingMs);
}

export function formatStartupElapsed(elapsedMs: number): string {
  return `${(Math.max(0, elapsedMs) / 1000).toFixed(1)}s`;
}
