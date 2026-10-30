import { afterEach, describe, expect, it, vi } from "vitest";
import { chromium, type Browser } from "playwright";
import { readFile } from "node:fs/promises";
import { LocalBrowserRunner } from "../src/runner";
import { SessionApi } from "../src/remote";
import { makePayload } from "../../extension/tests/fixtures";

// No external job page is requested. Every test navigation is fulfilled by
// Playwright; public/private DNS policy is tested separately.
vi.mock("../src/security", async (load) => ({
  ...await load<typeof import("../src/security")>(), validatePortalUrl: vi.fn(async (url: string) => new URL(url)),
}));

describe("local browser session driver", () => {
  let runner: LocalBrowserRunner | undefined;
  afterEach(async () => { await runner?.close(); vi.restoreAllMocks(); });

  it("runs the actual session, CV and question pipeline with isolated browser state", async () => {
    const payload = makePayload("GENERIC");
    payload.session.application_url = "https://example.com/apply";
    const connection = { sessionId: payload.session.id, token: "scoped-session-token", expiresAt: new Date(Date.now() + 60_000).toISOString(), apiBaseUrl: "http://localhost:3000/api/backend", applicationUrl: payload.session.application_url };
    let browser: Browser | undefined;
    const launch = chromium.launch.bind(chromium);
    vi.spyOn(chromium, "launch").mockImplementation(async (options) => {
      browser = await launch(options);
      const newContext = browser.newContext.bind(browser);
      vi.spyOn(browser, "newContext").mockImplementation(async (options) => {
        const context = await newContext(options);
        const newPage = context.newPage.bind(context);
        vi.spyOn(context, "newPage").mockImplementation(async () => {
          const page = await newPage();
          await page.route("https://example.com/**", (route) => route.fulfill({ contentType: "text/html", body: `<h1>Application</h1><form>
            <div class="field"><label for="name">Full name</label><input id="name"></div>
            <div class="field"><label for="why">Describe your Python experience</label><textarea id="why"></textarea></div>
            <div class="field"><label for="resume">Resume</label><input id="resume" type="file"></div>
            <button type="submit">Submit application</button></form>` }));
          return page;
        });
        return context;
      });
      return browser;
    });
    const remote = vi.spyOn(SessionApi.prototype, "json").mockImplementation(async (path, body) => {
      if (!path) return payload;
      if (path === "/agent/analyze") {
        const fields = (body as { fields: Array<{ field_id: string; raw_label: string }> }).fields;
        expect(JSON.stringify(body)).not.toContain("current_value");
        return { resolutions: fields.filter((field) => !field.raw_label.includes("Resume")).map((field) => ({
          field_id: field.field_id, canonical_field: field.raw_label === "Full name" ? "FULL_NAME" : "EXPERIENCE_ANSWER",
          question_category: field.raw_label === "Full name" ? "PROFILE_FACT" : "EXPERIENCE_QUESTION",
          action: field.raw_label === "Full name" ? "AUTO_FILL" : "GENERATE_REVIEW",
          selected_value: field.raw_label === "Full name" ? payload.profile.contact.full_name : "Built a Python backend in a personal project.",
          confidence: 0.95, requires_review: true, evidence_ids: [],
        })) };
      }
      return {};
    });
    vi.spyOn(SessionApi.prototype, "resume").mockResolvedValue(Buffer.from("%PDF-1.4 fixture"));
    runner = new LocalBrowserRunner(await readFile(new URL("../dist/browser.js", import.meta.url), "utf8"), true);
    const session = await runner.start(connection);
    const state = await runner.action(session.id, "fill");
    expect("fields" in state && state.fields.length).toBe(3);
    const page = browser!.contexts()[0].pages()[0];
    const applicationUrl = page.url();
    expect(await runner.action(session.id, "split-screen", { left: 0, top: 0, width: 960, height: 900 })).toEqual({ arranged: true });
    expect(page.url()).toBe(applicationUrl);
    expect(browser!.contexts()[0].pages()).toHaveLength(1);
    await expect(runner.action(session.id, "split-screen", { left: 0, top: 0, width: -1, height: 900 })).rejects.toThrow("dimensions");
    expect(await page.locator("#name").inputValue()).toBe(payload.profile.contact.full_name);
    expect(await page.locator("#resume").evaluate((element) => (element as HTMLInputElement).files?.[0]?.name)).toBe(payload.session.resume_filename);
    expect(await page.evaluate(() => typeof (globalThis as unknown as Record<string, unknown>).__radarLocal)).toBe("undefined");
    expect(remote).toHaveBeenCalledWith("/agent/analyze", expect.anything());
    await expect(runner.start(connection)).rejects.toThrow("Close the connected");
    await expect(runner.action("another-session", "scan")).rejects.toThrow("not found");
    await expect(runner.action(session.id, "confirm-submitted")).rejects.toThrow("Submit manually");
    await page.goto("https://example.com/next");
    await expect(runner.action(session.id, "answer", { fieldId: "id=why|occurrence=0", answer: "Stale answer" })).rejects.toThrow("Read the questions");
  }, 30_000);

  it("rejects a payload for another CV or session before launching a browser", async () => {
    const payload = makePayload("GENERIC");
    payload.resume.id = 999;
    vi.spyOn(SessionApi.prototype, "json").mockResolvedValue(payload);
    const launch = vi.spyOn(chromium, "launch");
    runner = new LocalBrowserRunner("", true);
    await expect(runner.start({ sessionId: 1, token: "token", expiresAt: new Date(Date.now() + 60_000).toISOString(), apiBaseUrl: "http://localhost:3000/api/backend", applicationUrl: payload.session.application_url })).rejects.toThrow("identity");
    expect(launch).not.toHaveBeenCalled();
  });
});
