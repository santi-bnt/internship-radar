import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../lib/api";
import { prepareApplication } from "../lib/prepare-application";
import type { ApplicationReadiness, GeneratedResume } from "../lib/types";

vi.mock("../lib/api", async (original) => ({
  ...await original<typeof import("../lib/api")>(), api: vi.fn(),
}));
const request = vi.mocked(api);
const resume = (status: GeneratedResume["status"], id = 20, jobId = 7) => ({ id, job_id: jobId, status }) as GeneratedResume;
const ready = (id = 20) => ({ resume: resume("compiled", id) }) as ApplicationReadiness;

describe("application-specific CV preparation", () => {
  beforeEach(() => { vi.useFakeTimers(); request.mockReset(); });
  afterEach(() => vi.useRealTimers());

  it("requests a new generation and waits for that exact version, ignoring an older compiled CV", async () => {
    request.mockResolvedValueOnce(resume("queued"))
      .mockResolvedValueOnce([resume("compiled", 19), resume("generating")])
      .mockResolvedValueOnce([resume("compiled", 19), resume("compiled")])
      .mockResolvedValueOnce(ready());
    const pending = prepareApplication(7, new AbortController().signal, vi.fn());
    await vi.advanceTimersByTimeAsync(3000);
    expect((await pending).resume?.id).toBe(20);
    expect(request).toHaveBeenNthCalledWith(1, "/api/jobs/7/resume/generate", expect.objectContaining({
      method: "POST", body: JSON.stringify({ resume_target: "recommended", regenerate: true }),
    }));
    expect(request).toHaveBeenLastCalledWith("/api/jobs/7/application-readiness?resume_version_id=20", expect.anything());
  });

  it("does not fall back to an old CV if generation fails", async () => {
    request.mockResolvedValueOnce({ ...resume("failed"), generation_error: "Page-fit validation failed" });
    await expect(prepareApplication(7, new AbortController().signal, vi.fn())).rejects.toThrow("Page-fit validation failed");
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("retries temporary polling failures without launching duplicate generations", async () => {
    request.mockResolvedValueOnce(resume("queued"))
      .mockRejectedValueOnce(new ApiError("Busy", 503))
      .mockResolvedValueOnce([resume("compiled")])
      .mockResolvedValueOnce(ready());
    const pending = prepareApplication(7, new AbortController().signal, vi.fn());
    await vi.advanceTimersByTimeAsync(3000);
    await pending;
    expect(request.mock.calls.filter(([path]) => path.endsWith("/resume/generate"))).toHaveLength(1);
  });

  it("rejects a readiness response bound to a different CV", async () => {
    request.mockResolvedValueOnce(resume("compiled")).mockResolvedValueOnce(ready(19));
    await expect(prepareApplication(7, new AbortController().signal, vi.fn())).rejects.toThrow("newly generated CV");
  });

  it("rejects a generation returned for another job", async () => {
    request.mockResolvedValueOnce(resume("compiled", 20, 8));
    await expect(prepareApplication(7, new AbortController().signal, vi.fn())).rejects.toThrow("does not belong");
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("stops polling when the dialog closes without sending another generation", async () => {
    const controller = new AbortController();
    request.mockResolvedValueOnce(resume("queued"));
    const pending = prepareApplication(7, controller.signal, vi.fn());
    const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(1);
    controller.abort();
    await rejected;
    await vi.advanceTimersByTimeAsync(3000);
    expect(request).toHaveBeenCalledTimes(1);
  });
});
