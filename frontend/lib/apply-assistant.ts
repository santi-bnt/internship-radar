import type { ApplicationReadiness, ApplicationSessionLaunch, Job } from "./types";

export const REQUIRED_READINESS_KEYS = new Set([
  "contact",
  "education",
  "location",
  "availability",
  "authorization",
  "skills",
  "projects",
  "resume",
  "portal",
]);

export function jobApplicationUrl(job: Job): string {
  const candidates = [job.application_url, job.official_apply_url, job.apply_url];
  return candidates.find((value) => isDirectJobUrl(value || "")) || "";
}

const DISCOVERY_HOSTS = new Set([
  "github.com",
  "www.github.com",
  "raw.githubusercontent.com",
  "simplify.jobs",
  "www.simplify.jobs",
  "applyguy.ai",
  "www.applyguy.ai",
]);

export function isDirectJobUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !DISCOVERY_HOSTS.has(url.hostname.toLowerCase());
  } catch {
    return false;
  }
}

export function isSupportedApplicationUrl(value: string): boolean {
  return isDirectJobUrl(value);
}

export function preliminaryPortalName(value: string): string {
  try {
    const host = new URL(value).hostname.toLocaleLowerCase();
    if (host.includes("myworkdayjobs.com")) return "Workday";
    if (host.includes("greenhouse.io") || host === "grnh.se") return "Greenhouse";
    if (host.includes("careers.microsoft.com")) return "Microsoft Careers";
    if (host === "amazon.jobs" || host.endsWith(".amazon.jobs")) return "Amazon Jobs";
    if (host === "careers.oracle.com" || host.endsWith(".oraclecloud.com")) return "Oracle Careers";
    return "Career Portal";
  } catch { return "Career Portal"; }
}

export function isAssistantAvailable(job: Job): boolean {
  return isSupportedApplicationUrl(jobApplicationUrl(job)) && ["active", "saved"].includes(job.status);
}

export function canStartApplication(readiness: ApplicationReadiness | null, advancedOverride: boolean): boolean {
  if (!readiness?.resume) return false;
  const requiredReady = readiness.checks
    .filter((item) => REQUIRED_READINESS_KEYS.has(item.key))
    .every((item) => item.ready);
  return requiredReady && (!readiness.hard_blocked || advancedOverride);
}

export function extensionConnectionMessage(launch: ApplicationSessionLaunch, origin: string) {
  return {
    source: "internship-radar-web",
    type: "CONNECT_APPLICATION_SESSION",
    payload: {
      sessionId: launch.session.id,
      token: launch.application_session_token,
      expiresAt: launch.token_expires_at,
      apiBaseUrl: `${origin}/api/backend`,
      applicationUrl: launch.session.application_url,
    },
  } as const;
}

export function extensionProbeMessage() {
  return {
    source: "internship-radar-web",
    type: "PING_APPLICATION_ASSISTANT",
  } as const;
}
