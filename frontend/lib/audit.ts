import { maskEmail } from "@/lib/identity";

type AuditDetails = {
  email?: string | null;
  primaryUserId?: string | null;
  resource?: string;
};

export function auditSecurityEvent(event: string, details: AuditDetails = {}): void {
  const safeDetails = {
    event,
    email: details.email ? maskEmail(details.email) : undefined,
    primaryUserId: details.primaryUserId ? "primary" : undefined,
    resource: details.resource?.slice(0, 160),
  };
  console.info("[security-audit]", JSON.stringify(safeDetails));
}
