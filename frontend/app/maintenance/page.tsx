import { LockKeyhole, Radar } from "lucide-react";

export default function MaintenancePage() {
  return (
    <section className="maintenance-card" aria-labelledby="maintenance-title">
      <span className="maintenance-mark" aria-hidden="true">
        <Radar size={30} />
      </span>
      <p className="eyebrow">Private workspace</p>
      <h1 id="maintenance-title">Internship Radar is temporarily unavailable</h1>
      <p>
        Access is disabled while secure sign-in is being configured. No internship,
        application, profile, or resume data is publicly available.
      </p>
      <div className="maintenance-status">
        <LockKeyhole size={17} aria-hidden="true" />
        Protected maintenance mode
      </div>
    </section>
  );
}
