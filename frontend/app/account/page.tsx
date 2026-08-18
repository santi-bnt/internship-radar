import { LogOut, RefreshCw } from "lucide-react";
import { redirect } from "next/navigation";

import { signOutUser, switchGoogleAccount } from "@/app/auth-actions";
import { auth } from "@/auth";
import { isPublicDemoMode } from "@/lib/access";
import { isAuthorizedEmail } from "@/lib/identity";

export default async function AccountPage() {
  if (isPublicDemoMode()) {
    return (
      <>
        <header className="page-header">
          <div>
            <p className="eyebrow">Public showcase</p>
            <h1>Demo account</h1>
            <p className="page-subtitle">
              This deployment uses a fictional candidate and contains no private account data.
            </p>
          </div>
        </header>
        <section className="panel account-panel">
          <p>Authentication and personal email delivery are disabled in public demo mode.</p>
        </section>
      </>
    );
  }

  const session = await auth();
  if (!session?.user?.primaryUserId || !isAuthorizedEmail(session.user.email)) {
    redirect("/login");
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Secure account</p>
          <h1>Account</h1>
          <p className="page-subtitle">
            Authentication and contact addresses are intentionally kept separate.
          </p>
        </div>
      </header>
      <section className="panel account-panel">
        <dl>
          <div>
            <dt>Signed in with</dt>
            <dd>{session.user.email}</dd>
          </div>
          <div>
            <dt>Professional email</dt>
            <dd>{process.env.RESUME_EMAIL ?? "Not configured"}</dd>
          </div>
          <div>
            <dt>Notification email</dt>
            <dd>{process.env.NOTIFICATION_EMAIL ?? "Not configured"}</dd>
          </div>
        </dl>
        <div className="account-actions">
          <form action={switchGoogleAccount}>
            <button className="button primary" type="submit">
              <RefreshCw size={17} />
              Switch Google account
            </button>
          </form>
          <form action={signOutUser}>
            <button className="button secondary" type="submit">
              <LogOut size={17} />
              Sign out
            </button>
          </form>
        </div>
        <p className="account-help">
          Switching signs out this session, then lets you choose another authorized Google
          account.
        </p>
      </section>
    </>
  );
}
