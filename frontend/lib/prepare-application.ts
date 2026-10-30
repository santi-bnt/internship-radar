import { api, ApiError } from "./api";
import type { ApplicationReadiness, GeneratedResume } from "./types";

/** Each application requests a fresh version through the normal generation queue. */
export async function prepareApplication(
  jobId: number,
  signal: AbortSignal,
  onProgress: (message: string) => void,
  existingResume?: GeneratedResume,
): Promise<ApplicationReadiness> {
  let resume: GeneratedResume;
  if (existingResume) {
    if (existingResume.job_id !== jobId || existingResume.status !== "compiled") {
      throw new Error("The saved CV is not a compiled resume for this job.");
    }
    resume = existingResume;
    onProgress(`Using saved CV version ${resume.version} for this job.`);
  } else {
  onProgress("Generating a new CV tailored to this job…");
  resume = await api<GeneratedResume>(`/api/jobs/${jobId}/resume/generate`, {
    method: "POST",
    body: JSON.stringify({ resume_target: "recommended", regenerate: true }),
    signal,
  });
  const deadline = Date.now() + 20 * 60_000;
  while (true) {
    signal.throwIfAborted();
    if (resume.job_id !== jobId) throw new Error("The generated CV does not belong to this job.");
    if (resume.status === "compiled") break;
    if (!["queued", "generating", "pending"].includes(resume.status)) {
      throw new Error(resume.generation_error || "The new CV could not be generated. Try again.");
    }
    if (Date.now() >= deadline) {
      throw new Error("Your CV is still processing. Check its progress in Recommended Resume before trying again.");
    }
    onProgress(resume.status === "generating"
      ? "Writing, compiling and validating your new job-specific CV…"
      : "Your new CV is queued. You can keep browsing while it is prepared…");
    await new Promise<void>((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(signal.reason); };
      const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 1500);
      signal.addEventListener("abort", abort, { once: true });
    });
    try {
      const versions = await api<GeneratedResume[]>(`/api/jobs/${jobId}/resumes`, { signal });
      const current = versions.find((version) => version.id === resume.id);
      if (!current) throw new Error("The new CV version is unavailable. Please try again.");
      resume = current;
    } catch (error) {
      // Retry only reads; never create another generation on a polling failure.
      if (!(error instanceof ApiError && [429, 502, 503, 504].includes(error.status))) throw error;
    }
  }
  }
  onProgress(existingResume ? "Preparing your application with the saved CV…" : "Preparing your application with the new CV…");
  const readiness = await api<ApplicationReadiness>(
    `/api/jobs/${jobId}/application-readiness?resume_version_id=${resume.id}`, { signal },
  );
  if (readiness.resume?.id !== resume.id || readiness.resume.job_id !== jobId) {
    throw new Error("The application could not be linked to the newly generated CV.");
  }
  return readiness;
}
