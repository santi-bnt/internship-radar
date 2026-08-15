import { createHmac, randomUUID } from "node:crypto";

import { normalizeEmail } from "@/lib/identity";

const AUDIENCE = "internship-radar-api";
const PURPOSE = "user_request";
const TOKEN_TTL_SECONDS = 60;

type UserIdentityPayload = {
  v: 1;
  sub: string;
  email: string;
  iat: number;
  exp: number;
  aud: typeof AUDIENCE;
  purpose: typeof PURPOSE;
  nonce: string;
};

function base64Url(value: string): string {
  return Buffer.from(value, "utf8").toString("base64url");
}

export function createUserIdentityToken(primaryUserId: string, email: string): string {
  const secret = process.env.USER_IDENTITY_SIGNING_SECRET?.trim();
  if (!secret) throw new Error("User identity signing is not configured.");

  const now = Math.floor(Date.now() / 1000);
  const payload: UserIdentityPayload = {
    v: 1,
    sub: primaryUserId,
    email: normalizeEmail(email),
    iat: now,
    exp: now + TOKEN_TTL_SECONDS,
    aud: AUDIENCE,
    purpose: PURPOSE,
    nonce: randomUUID(),
  };
  const encodedPayload = base64Url(JSON.stringify(payload));
  const signature = createHmac("sha256", secret).update(encodedPayload).digest("base64url");
  return `${encodedPayload}.${signature}`;
}
