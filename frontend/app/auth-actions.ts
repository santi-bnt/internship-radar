"use server";

import { auditSecurityEvent } from "@/lib/audit";
import { auth, signIn, signOut } from "@/auth";

export async function signInWithGoogle(): Promise<void> {
  await signIn("google", { redirectTo: "/" });
}

export async function signOutUser(): Promise<void> {
  const session = await auth();
  auditSecurityEvent("logout", {
    email: session?.user?.email,
    primaryUserId: session?.user?.primaryUserId,
  });
  await signOut({ redirectTo: "/login" });
}

export async function switchGoogleAccount(): Promise<void> {
  const session = await auth();
  auditSecurityEvent("account_switch_requested", {
    email: session?.user?.email,
    primaryUserId: session?.user?.primaryUserId,
  });
  await signOut({ redirectTo: "/login?switch=1" });
}
