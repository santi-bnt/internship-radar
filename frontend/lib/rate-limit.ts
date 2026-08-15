type RateLimitEntry = {
  count: number;
  resetAt: number;
};

type RateLimitRule = {
  key: string;
  limit: number;
  windowMs: number;
};

const buckets = new Map<string, RateLimitEntry>();

export function sensitiveOperation(pathname: string, method: string): RateLimitRule | null {
  if (method === "POST" && pathname === "/api/jobs/search") {
    return { key: "search", limit: 5, windowMs: 60 * 60 * 1000 };
  }
  if (method === "POST" && /\/api\/jobs\/\d+\/resume\/generate$/.test(pathname)) {
    return { key: "resume", limit: 10, windowMs: 60 * 60 * 1000 };
  }
  if (method === "POST" && pathname.startsWith("/api/notifications/test-")) {
    return { key: "test-email", limit: 5, windowMs: 60 * 60 * 1000 };
  }
  if (
    method === "GET" &&
    /\/api\/generated-resumes\/\d+\/(pdf|tex)$/.test(pathname)
  ) {
    return { key: "resume-download", limit: 30, windowMs: 60 * 1000 };
  }
  if (
    ["PUT", "POST", "DELETE", "PATCH"].includes(method) &&
    (pathname === "/api/profile" ||
      pathname === "/api/resume-profile" ||
      pathname.startsWith("/api/target-companies"))
  ) {
    return { key: "settings", limit: 30, windowMs: 60 * 60 * 1000 };
  }
  return null;
}

export function checkRateLimit(
  primaryUserId: string,
  rule: RateLimitRule,
): { allowed: boolean; retryAfter: number } {
  const now = Date.now();
  const bucketKey = `${primaryUserId}:${rule.key}`;
  const entry = buckets.get(bucketKey);
  if (!entry || entry.resetAt <= now) {
    buckets.set(bucketKey, { count: 1, resetAt: now + rule.windowMs });
    return { allowed: true, retryAfter: 0 };
  }
  if (entry.count >= rule.limit) {
    return {
      allowed: false,
      retryAfter: Math.max(1, Math.ceil((entry.resetAt - now) / 1000)),
    };
  }
  entry.count += 1;
  return { allowed: true, retryAfter: 0 };
}
