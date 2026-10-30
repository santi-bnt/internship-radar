import { timingSafeEqual } from "node:crypto";
import { lookup } from "node:dns/promises";
import ipaddr from "ipaddr.js";
import type { StoredApplicationSession } from "../../extension/src/shared/types";

export const PORT = 43123;
export const WEB_ORIGINS = new Set([
  "https://your-app.vercel.app", "https://your-app.vercel.app", "http://localhost:3000", "http://127.0.0.1:3000",
]);

export class AgentError extends Error {
  constructor(message: string, readonly status = 400) { super(message); }
}

export function isPublicAddress(address: string): boolean {
  try { return ipaddr.process(address).range() === "unicast"; } catch { return false; }
}

export async function resolvePublicDestination(value: string, resolve = lookup) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) {
    throw new AgentError("Use a public HTTPS application URL.");
  }
  const host = url.hostname.replace(/^\[|\]$/g, "");
  if (!host.includes(".") || /(?:^|\.)(?:localhost|local|internal|lan)$/.test(host)) throw new AgentError("Internal application URLs are blocked.");
  const addresses = await resolve(host, { all: true, verbatim: true });
  if (!addresses.length || addresses.some((item) => !isPublicAddress(item.address))) {
    throw new AgentError("Private, local and reserved network addresses are blocked.");
  }
  return { url, addresses };
}

export async function validatePortalUrl(value: string, resolve = lookup): Promise<URL> {
  return (await resolvePublicDestination(value, resolve)).url;
}

export function validateLaunch(value: unknown, origin: string): StoredApplicationSession {
  const input = value as Partial<StoredApplicationSession> | null;
  if (!input || !Number.isSafeInteger(input.sessionId) || Number(input.sessionId) < 1
    || typeof input.token !== "string" || input.token.length < 20 || input.token.length > 8192
    || typeof input.apiBaseUrl !== "string" || typeof input.applicationUrl !== "string"
    || typeof input.expiresAt !== "string" || !Number.isFinite(Date.parse(input.expiresAt)) || Date.parse(input.expiresAt) <= Date.now()) {
    throw new AgentError("Invalid or expired application session. Start it again from Internship Radar.");
  }
  const base = new URL(input.apiBaseUrl);
  if (!WEB_ORIGINS.has(origin) || base.origin !== origin || base.pathname !== "/api/backend" || base.search || base.hash || base.username || base.password) {
    throw new AgentError("The application API must belong to the connected Internship Radar site.", 403);
  }
  return input as StoredApplicationSession;
}

export function authenticate(key: string, authorization: string | undefined): boolean {
  const actual = Buffer.from(authorization || "");
  const expected = Buffer.from(`Bearer ${key}`);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
