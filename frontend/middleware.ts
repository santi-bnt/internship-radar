import type { NextFetchEvent } from "next/server";
import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";
import { isAppAccessEnabled } from "@/lib/access";
import { auditSecurityEvent } from "@/lib/audit";
import { frameSecurityPolicy } from "@/lib/frame-policy";
import { isAuthorizedEmail } from "@/lib/identity";

const PUBLIC_PATHS = ["/login", "/maintenance", "/access-denied", "/api/auth"];

function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`)) ||
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt"
  );
}

function secureResponse(response: NextResponse, pathname: string): NextResponse {
  const framePolicy = frameSecurityPolicy(pathname);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", framePolicy.xFrameOptions);
  response.headers.set("Content-Security-Policy", framePolicy.contentSecurityPolicy);
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return response;
}

const authenticatedMiddleware = auth((request) => {
  const pathname = request.nextUrl.pathname;
  const session = request.auth;
  const authorized =
    Boolean(session?.user?.primaryUserId) && isAuthorizedEmail(session?.user?.email);

  if (!authorized) {
    auditSecurityEvent(session?.user ? "access_rejected" : "authentication_required", {
      email: session?.user?.email,
      resource: pathname,
    });
    if (pathname.startsWith("/api/")) {
      return secureResponse(
        NextResponse.json(
          { detail: session?.user ? "Access denied." : "Authentication required." },
          { status: session?.user ? 403 : 401, headers: { "Cache-Control": "no-store" } },
        ),
        pathname,
      );
    }
    const destination = new URL(session?.user ? "/access-denied" : "/login", request.url);
    return secureResponse(NextResponse.redirect(destination, 307), pathname);
  }

  return secureResponse(NextResponse.next(), pathname);
});

export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  const pathname = request.nextUrl.pathname;
  if (isPublicPath(pathname)) return secureResponse(NextResponse.next(), pathname);

  if (!isAppAccessEnabled()) {
    if (pathname.startsWith("/api/")) {
      return secureResponse(
        NextResponse.json(
          { detail: "Internship Radar is temporarily unavailable." },
          {
            status: 503,
            headers: { "Cache-Control": "no-store", "Retry-After": "3600" },
          },
        ),
        pathname,
      );
    }
    return secureResponse(
      NextResponse.redirect(new URL("/maintenance", request.url), 307),
      pathname,
    );
  }

  return (
    authenticatedMiddleware as unknown as (
      request: NextRequest,
      event: NextFetchEvent,
    ) => Promise<Response> | Response
  )(request, event);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
