const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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
  return normalized !== "" && authorizedEmails().has(normalized);
}

export function resolvePrimaryUser(email: string | null | undefined): string | null {
  const primaryUserId = process.env.PRIMARY_USER_ID?.trim() ?? "";
  return isAuthorizedEmail(email) && primaryUserId ? primaryUserId : null;
}

export function maskEmail(email: string | null | undefined): string {
  const normalized = normalizeEmail(email);
  const [local, domain] = normalized.split("@");
  if (!local || !domain) return "unknown";
  return `${local[0]}***@${domain}`;
}
