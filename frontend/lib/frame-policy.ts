const RESUME_PDF_PROXY_PATH =
  /^\/api\/backend\/api\/generated-resumes\/\d+\/pdf\/?$/;

export type FrameSecurityPolicy = {
  xFrameOptions: "DENY" | "SAMEORIGIN";
  contentSecurityPolicy: "frame-ancestors 'none'" | "frame-ancestors 'self'";
};

export function frameSecurityPolicy(pathname: string): FrameSecurityPolicy {
  if (RESUME_PDF_PROXY_PATH.test(pathname)) {
    return {
      xFrameOptions: "SAMEORIGIN",
      contentSecurityPolicy: "frame-ancestors 'self'",
    };
  }

  return {
    xFrameOptions: "DENY",
    contentSecurityPolicy: "frame-ancestors 'none'",
  };
}
