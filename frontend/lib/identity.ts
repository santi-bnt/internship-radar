const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const JOSHUA_EMAIL = "secondary@example.com";
export const JOSHUA_USER_ID = "00000000-0000-5000-8000-000000000001";
export const ALONSO_EMAIL = "tertiary@example.com";
export const ALONSO_USER_ID = "00000000-0000-5000-8000-000000000002";

function configuredCandidateIds(): Readonly<Record<string, string>> {
  try {
    const value: unknown = JSON.parse(process.env.CANDIDATE_ACCOUNT_IDS || "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([email, owner]) => EMAIL_PATTERN.test(email)
      && typeof owner === "string" && owner.trim().length > 0 && owner.trim().length <= 160)
      .map(([email, owner]) => [email.trim().toLowerCase(), (owner as string).trim()]));
  } catch { return {}; }
}

export function normalizeEmail(email: string | null | undefined): string {
  return email?.trim().toLowerCase() ?? "";
}

export function authorizedEmails(): ReadonlySet<string> {
  const configured = process.env.AUTHORIZED_USER_EMAILS ?? "";
  return new Set(
    configured
      .split(",")
      .map(normalizeEmail)
      .filter((email) => EMAIL_PATTERN.test(email)),
  );
}

export function isAuthorizedEmail(email: string | null | undefined): boolean {
  const normalized = normalizeEmail(email);
  return normalized in configuredCandidateIds() || (normalized !== "" && authorizedEmails().has(normalized));
}

export function resolvePrimaryUser(email: string | null | undefined): string | null {
  const independentUserId = configuredCandidateIds()[normalizeEmail(email)];
  if (independentUserId) return independentUserId;
  const primaryUserId = process.env.PRIMARY_USER_ID?.trim() ?? "";
  return isAuthorizedEmail(email) && primaryUserId ? primaryUserId : null;
}

export function maskEmail(email: string | null | undefined): string {
  const normalized = normalizeEmail(email);
  const [local, domain] = normalized.split("@");
  if (!local || !domain) return "unknown";
  return `${local[0]}***@${domain}`;
}
