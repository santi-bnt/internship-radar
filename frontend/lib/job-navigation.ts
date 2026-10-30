const FALLBACK_LIST_PATH = "/jobs";
const ALLOWED_LIST_PATHS = new Set(["/", "/jobs"]);

/** Keep a return path local to Internship Radar; never redirect to another origin. */
export function safeJobListPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return FALLBACK_LIST_PATH;
  const parsed = new URL(value, "https://internship-radar.local");
  if (!ALLOWED_LIST_PATHS.has(parsed.pathname)) return FALLBACK_LIST_PATH;
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export function jobDetailHref(jobId: number, returnTo?: string): string {
  const path = safeJobListPath(returnTo);
  return `/jobs/${jobId}?from=${encodeURIComponent(path)}`;
}

export function jobListReturnPath(search: string): string {
  return safeJobListPath(new URLSearchParams(search).get("from"));
}

export function jobListPathWithNotice(path: string, notice: string): string {
  const safePath = safeJobListPath(path);
  const parsed = new URL(safePath, "https://internship-radar.local");
  parsed.searchParams.set("notice", notice);
  return `${parsed.pathname}${parsed.search}`;
}
