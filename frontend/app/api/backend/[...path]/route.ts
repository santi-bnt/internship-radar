import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";
import { isAppAccessEnabled, isLocalDevelopmentMode, isPublicDemoMode } from "@/lib/access";
import { auditSecurityEvent } from "@/lib/audit";
import { frameSecurityPolicy } from "@/lib/frame-policy";
import { isAuthorizedEmail } from "@/lib/identity";
import {
  checkRateLimit,
  sensitiveOperation,
} from "@/lib/rate-limit";
import { createUserIdentityToken } from "@/lib/user-identity-token";

const INTERNAL_API_URL =
  process.env.FASTAPI_INTERNAL_URL ??
  process.env.INTERNAL_API_URL ??
  "http://127.0.0.1:8000";

function errorResponse(detail: string, status: number, headers?: HeadersInit) {
  return NextResponse.json(
    { detail },
    { status, headers: { "Cache-Control": "no-store", ...headers } },
  );
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const publicDemo = isPublicDemoMode();
  if (!isAppAccessEnabled() && !publicDemo) {
    return errorResponse("Internship Radar is temporarily unavailable.", 503);
  }

  const { path } = await context.params;
  if (
    path.length === 0 ||
    path.some((segment) => !segment || segment === "." || segment === "..")
  ) {
    return errorResponse("Resource not found.", 404);
  }
  const backendPath = `/${path.join("/")}`;
  const extensionRequest = backendPath.startsWith("/api/extension/");
  if (publicDemo && (request.method !== "GET" || extensionRequest)) {
    return errorResponse("Read-only public demo. Run a private installation to import jobs, edit profiles or use the application assistant.", 403);
  }

  const localDevelopment = isLocalDevelopmentMode();
  const session = publicDemo || localDevelopment || extensionRequest ? null : await auth();
  if (!publicDemo && !localDevelopment && !extensionRequest) {
    if (!session?.user) {
      auditSecurityEvent("bff_authentication_required", {
        resource: request.nextUrl.pathname,
      });
      return errorResponse("Authentication required.", 401);
    }
    if (
      !session.user.primaryUserId ||
      !session.user.email ||
      !isAuthorizedEmail(session.user.email)
    ) {
      auditSecurityEvent("bff_access_rejected", {
        email: session.user.email,
        resource: request.nextUrl.pathname,
      });
      return errorResponse("Access denied.", 403);
    }
  }

  const primaryUserId = publicDemo ? process.env.DEMO_USER_ID?.trim() || "public-demo" : localDevelopment
    ? process.env.PRIMARY_USER_ID?.trim() || "primary-user"
    : extensionRequest ? "extension-session" : session!.user.primaryUserId!;
  const authenticatedEmail = publicDemo ? process.env.DEMO_USER_EMAIL?.trim() || "demo@example.com" : localDevelopment
    ? process.env.LOCAL_DEVELOPMENT_EMAIL?.trim() || "local@internship-radar.test"
    : extensionRequest ? "extension-session@internship-radar.invalid" : session!.user.email!;

  const internalSecret = process.env.INTERNAL_API_SECRET?.trim();
  const identitySecret = process.env.USER_IDENTITY_SIGNING_SECRET?.trim();
  if (!localDevelopment && !extensionRequest && (!internalSecret || !identitySecret)) {
    console.error("[security] Private backend authentication is not configured.");
    return errorResponse("Operation failed.", 503);
  }

  const rule = extensionRequest ? null : sensitiveOperation(backendPath, request.method);
  if (rule) {
    const rateLimit = checkRateLimit(primaryUserId, rule);
    if (!rateLimit.allowed) {
      auditSecurityEvent("rate_limit_rejected", {
        email: authenticatedEmail,
        primaryUserId,
        resource: rule.key,
      });
      const message = rule.key === "resume"
        ? `Resume generation limit reached. Try again in ${Math.ceil(rateLimit.retryAfter / 60)} minutes.`
        : "Too many requests. Try again later.";
      return NextResponse.json(
        {
          error: rule.key === "resume" ? "resume_generation_rate_limit" : "rate_limit",
          detail: message,
          message,
          retry_after_seconds: rateLimit.retryAfter,
        },
        { status: 429, headers: { "Cache-Control": "no-store", "Retry-After": String(rateLimit.retryAfter) } },
      );
    }
  }

  const baseUrl = new URL(INTERNAL_API_URL);
  const target = new URL(backendPath, `${baseUrl.origin}/`);
  if (target.origin !== baseUrl.origin) return errorResponse("Resource not found.", 404);
  request.nextUrl.searchParams.forEach((value, key) =>
    target.searchParams.append(key, value),
  );

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const authorization = request.headers.get("authorization");
  if (extensionRequest && authorization) headers.set("authorization", authorization);
  if (!extensionRequest && internalSecret) headers.set("x-internal-api-secret", internalSecret);
  if (!extensionRequest && identitySecret) {
    headers.set(
      "x-user-identity",
      createUserIdentityToken(primaryUserId, authenticatedEmail),
    );
  }

  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch (error) {
    console.error(
      "[bff] Backend request failed:",
      error instanceof Error ? error.message : "unknown error",
    );
    return errorResponse("Operation failed.", 502);
  }

  const outgoing = new Headers({ "Cache-Control": "no-store" });
  const framePolicy = frameSecurityPolicy(request.nextUrl.pathname);
  outgoing.set("X-Frame-Options", framePolicy.xFrameOptions);
  outgoing.set("Content-Security-Policy", framePolicy.contentSecurityPolicy);
  for (const name of ["content-type", "content-disposition", "retry-after"]) {
    const value = response.headers.get(name);
    if (value) outgoing.set(name, value);
  }
  return new NextResponse(response.body, {
    status: response.status,
    headers: outgoing,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
