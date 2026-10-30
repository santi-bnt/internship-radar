import { describe, expect, it } from "vitest";

import { canStartApplication, extensionConnectionMessage, extensionProbeMessage, isAssistantAvailable, jobApplicationUrl, preliminaryPortalName } from "@/lib/apply-assistant";
import type { ApplicationReadiness, ApplicationSessionLaunch, Job } from "@/lib/types";

const job = {
  status: "active",
  official_apply_url: "https://example.wd1.myworkdayjobs.com/job/REQ-1",
  apply_url: "https://example.wd1.myworkdayjobs.com/job/REQ-1",
} as Job;

const readiness = {
  hard_blocked: false,
  resume: { id: 4 },
  checks: ["contact", "education", "location", "availability", "authorization", "skills", "projects", "resume", "portal"].map((key) => ({ key, label: key, ready: true })),
} as ApplicationReadiness;

describe("Apply Assistant web launcher", () => {
  it("requires an active job and application URL", () => {
    expect(isAssistantAvailable(job)).toBe(true);
    expect(isAssistantAvailable({ ...job, status: "applied" })).toBe(false);
    expect(isAssistantAvailable({ ...job, apply_url: "", official_apply_url: null })).toBe(false);
    expect(isAssistantAvailable({ ...job, official_apply_url: "https://jobs.example.com/apply" })).toBe(true);
    expect(isAssistantAvailable({
      ...job,
      application_url: "",
      apply_url: "http://jobs.example.com/apply",
      official_apply_url: "http://jobs.example.com/apply",
    })).toBe(false);
    expect(preliminaryPortalName("https://www.amazon.jobs/en/jobs/123")).toBe("Amazon Jobs");
  });

  it("uses employer links and rejects repository fallbacks", () => {
    expect(jobApplicationUrl({
      ...job,
      application_url: "",
      official_apply_url: null,
      apply_url: "https://careers.honeywell.com/job/155561",
    })).toBe("https://careers.honeywell.com/job/155561");
    expect(jobApplicationUrl({
      ...job,
      application_url: "",
      official_apply_url: null,
      apply_url: "https://github.com/SimplifyJobs/Summer2027-Internships",
    })).toBe("");
  });

  it("blocks missing readiness and hard-ineligible jobs unless explicitly overridden", () => {
    expect(canStartApplication(readiness, false)).toBe(true);
    expect(canStartApplication({ ...readiness, checks: readiness.checks.map((item) => item.key === "contact" ? { ...item, ready: false } : item) }, false)).toBe(false);
    expect(canStartApplication({ ...readiness, hard_blocked: true }, false)).toBe(false);
    expect(canStartApplication({ ...readiness, hard_blocked: true }, true)).toBe(true);
  });

  it("sends only the scoped session token and public BFF URL to the extension", () => {
    const launch = {
      session: { id: 7, application_url: job.apply_url },
      application_session_token: "short-lived-token",
      token_expires_at: "2026-08-23T18:30:00Z",
    } as ApplicationSessionLaunch;
    const message = extensionConnectionMessage(launch, "https://your-app.vercel.app");
    expect(message.payload.apiBaseUrl).toBe("https://your-app.vercel.app/api/backend");
    expect(message.payload.token).toBe("short-lived-token");
    expect(JSON.stringify(message)).not.toContain("INTERNAL_API_SECRET");
  });

  it("uses a payload-free probe before an application session is opened", () => {
    expect(extensionProbeMessage()).toEqual({
      source: "internship-radar-web",
      type: "PING_APPLICATION_ASSISTANT",
    });
  });
});
