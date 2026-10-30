const GREENHOUSE_EMBED_ORIGIN = "https://boards.greenhouse.io";

export function portalPermissionOrigins(urlValue: string): string[] {
  const url = new URL(urlValue);
  if (url.protocol !== "https:") throw new Error("Apply Assistant only activates on secure HTTPS career portals.");
  const origins = [`${url.origin}/*`];
  if (url.hostname === "zipline.com" || url.hostname.endsWith(".zipline.com")) {
    origins.push(`${GREENHOUSE_EMBED_ORIGIN}/*`);
  }
  return origins;
}

export function trustedGreenhouseEmbedUrl(urlValue: string | null | undefined): string | null {
  if (!urlValue) return null;
  try {
    const url = new URL(urlValue);
    if (url.origin !== GREENHOUSE_EMBED_ORIGIN || url.pathname !== "/embed/job_app") return null;
    if (!url.searchParams.get("for") || !/^\d+$/.test(url.searchParams.get("token") || "")) return null;
    return url.href;
  } catch {
    return null;
  }
}
