import { Radar } from "lucide-react";
import { redirect } from "next/navigation";

import { signInWithGoogle } from "@/app/auth-actions";
import { auth } from "@/auth";
import { isAppAccessEnabled } from "@/lib/access";
import { isAuthorizedEmail } from "@/lib/identity";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; switch?: string }>;
}) {
  const session = await auth();
  if (
    isAppAccessEnabled() &&
    session?.user?.primaryUserId &&
    isAuthorizedEmail(session.user.email)
  ) {
    redirect("/");
  }
  const { error, switch: switchingAccount } = await searchParams;

  return (
    <section className="auth-card" aria-labelledby="login-title">
      <span className="maintenance-mark" aria-hidden="true">
        <Radar size={30} />
      </span>
      <p className="eyebrow">Private workspace</p>
      <h1 id="login-title">Internship Radar</h1>
      <p>Sign in to access this private internship and application workspace.</p>
      {error && (
        <p className="auth-error" role="alert">
          Sign-in could not be completed. Check the account and try again.
        </p>
      )}
      {switchingAccount === "1" && !error && (
        <p className="auth-notice" role="status">
          Signed out. Continue with Google to choose another authorized account.
        </p>
      )}
      <form action={signInWithGoogle}>
        <button className="button primary auth-button" type="submit">
          Sign in with Google
        </button>
      </form>
    </section>
  );
}
