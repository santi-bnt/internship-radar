import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

import { auditSecurityEvent } from "@/lib/audit";
import {
  isAuthorizedEmail,
  normalizeEmail,
  resolvePrimaryUser,
} from "@/lib/identity";

function isVerifiedGoogleProfile(profile: unknown): boolean {
  if (!profile || typeof profile !== "object") return false;
  return (profile as { email_verified?: unknown }).email_verified === true;
}

function allowedRedirect(url: string, baseUrl: string): string {
  const configuredOrigin = process.env.NEXT_PUBLIC_APP_URL?.trim();
  const allowedOrigins = new Set([baseUrl]);
  if (configuredOrigin) {
    try {
      allowedOrigins.add(new URL(configuredOrigin).origin);
    } catch {
      // Ignore malformed configuration and retain the trusted Auth.js base URL.
    }
  }
  if (process.env.NODE_ENV !== "production") allowedOrigins.add("http://localhost:3000");

  try {
    const destination = url.startsWith("/") ? new URL(url, baseUrl) : new URL(url);
    return allowedOrigins.has(destination.origin) ? destination.toString() : baseUrl;
  } catch {
    return baseUrl;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Google({
      authorization: { params: { prompt: "select_account" } },
    }),
  ],
  pages: {
    signIn: "/login",
    error: "/access-denied",
  },
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60,
    updateAge: 60 * 60,
  },
  callbacks: {
    async signIn({ account, profile, user }) {
      const email = normalizeEmail(user.email ?? profile?.email);
      const allowed =
        account?.provider === "google" &&
        isVerifiedGoogleProfile(profile) &&
        isAuthorizedEmail(email) &&
        resolvePrimaryUser(email) !== null;
      auditSecurityEvent(allowed ? "login_accepted" : "login_rejected", { email });
      return allowed;
    },
    async jwt({ token, account, profile }) {
      if (account) {
        const email = normalizeEmail(token.email ?? profile?.email);
        const primaryUserId =
          account.provider === "google" && isVerifiedGoogleProfile(profile)
            ? resolvePrimaryUser(email)
            : null;
        if (!primaryUserId) {
          delete token.primaryUserId;
          delete token.authenticatedEmail;
          return token;
        }
        token.primaryUserId = primaryUserId;
        token.authenticatedEmail = email;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.email =
          typeof token.authenticatedEmail === "string" ? token.authenticatedEmail : "";
        session.user.primaryUserId =
          typeof token.primaryUserId === "string" ? token.primaryUserId : "";
      }
      return session;
    },
    async redirect({ url, baseUrl }) {
      return allowedRedirect(url, baseUrl);
    },
  },
  events: {
    async signOut(message) {
      const email =
        "token" in message && typeof message.token?.authenticatedEmail === "string"
          ? message.token.authenticatedEmail
          : null;
      auditSecurityEvent("logout", { email });
    },
  },
});
