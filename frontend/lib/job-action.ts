import type { Job, Recommendation } from "@/lib/types";

/** The candidate action can intentionally differ from eligibility analysis. */
export function displayedJobAction(job: Pick<Job, "candidate_action_recommendation" | "analysis">): Recommendation | string {
  return job.candidate_action_recommendation ?? job.analysis?.recommendation ?? "Review";
}
