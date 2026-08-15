import { ShieldX } from "lucide-react";

import { signOutUser } from "@/app/auth-actions";

export default function AccessDeniedPage() {
  return (
    <section className="auth-card" aria-labelledby="denied-title">
      <span className="maintenance-mark denied-mark" aria-hidden="true">
        <ShieldX size={30} />
      </span>
      <p className="eyebrow">Private workspace</p>
      <h1 id="denied-title">Access denied</h1>
      <p>This Google account is not authorized to use Internship Radar.</p>
      <form action={signOutUser}>
        <button className="button secondary auth-button" type="submit">
          Sign out and try another account
        </button>
      </form>
    </section>
  );
}
