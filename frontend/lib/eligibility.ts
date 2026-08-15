import type { Job } from "@/lib/types";

export function appendEligibilityFilters(
  params: URLSearchParams,
  options: {
    showIneligible: boolean;
    eligibility: string[];
    remoteScopes: string[];
    sponsorship: string[];
  },
): URLSearchParams {
  options.eligibility.forEach((value) => params.append("eligibility", value));
  options.remoteScopes.forEach((value) => params.append("remote_scope", value));
  options.sponsorship.forEach((value) => params.append("sponsorship", value));
  if (options.showIneligible) params.set("include_ineligible", "true");
  return params;
}

export function primaryEligibilityReason(job: Pick<Job, "analysis">): string | null {
  if (job.analysis?.eligibility_status !== "NOT_ELIGIBLE") return null;
  return job.analysis.blocker_reasons[0] ?? "A hard eligibility requirement is not met.";
}
