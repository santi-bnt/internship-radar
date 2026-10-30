import { afterEach, describe, expect, it, vi } from "vitest";
import { chromium, type Browser } from "playwright";
import { readFile } from "node:fs/promises";
import { LocalBrowserRunner } from "../src/runner";
import { SessionApi } from "../src/remote";
import { makePayload } from "../../extension/tests/fixtures";

vi.mock("../src/security", async (load) => ({
  ...await load<typeof import("../src/security")>(), validatePortalUrl: vi.fn(async (value: string) => {
    if (value.includes("127.0.0.1")) throw new Error("Private URL blocked");
    return new URL(value);
  }),
}));

describe("local page observation", () => {
  let runner: LocalBrowserRunner;
  let browser: Browser;
  afterEach(async () => { await runner?.close(); vi.restoreAllMocks(); });

  async function fixture(main: string, frame = "") {
    const payload = makePayload("GENERIC");
    // Ashby intentionally has no write adapter: reading must still work.
    payload.session.application_url = "https://jobs.ashbyhq.com/example/application";
    const launch = chromium.launch.bind(chromium);
    vi.spyOn(chromium, "launch").mockImplementation(async (options) => {
      browser = await launch(options);
      const newContext = browser.newContext.bind(browser);
      vi.spyOn(browser, "newContext").mockImplementation(async (options) => {
        const context = await newContext(options);
        const newPage = context.newPage.bind(context);
        vi.spyOn(context, "newPage").mockImplementation(async () => {
          const page = await newPage();
          await page.route("https://**/*", (route) => route.fulfill({ contentType: "text/html",
            body: route.request().url().includes("frame.example.com") ? frame : main }));
          return page;
        });
        return context;
      });
      return browser;
    });
    const remote = vi.spyOn(SessionApi.prototype, "json").mockImplementation(async (path, body) => {
      if (!path) return payload;
      if (path === "/agent/analyze") {
        const fields = (body as { fields: Array<{ field_id: string }> }).fields;
        return { resolutions: fields.map((field) => ({ field_id: field.field_id, action: "GENERATE_REVIEW",
          question_category: "EXPERIENCE_QUESTION", selected_value: "Verified personal project experience", confidence: 0.9 })) };
      }
      return {};
    });
    runner = new LocalBrowserRunner(await readFile(new URL("../dist/browser.js", import.meta.url), "utf8"), true);
    const session = await runner.start({ sessionId: payload.session.id, token: "scoped-session-token",
      expiresAt: new Date(Date.now() + 60000).toISOString(), apiBaseUrl: "http://localhost:3000/api/backend",
      applicationUrl: payload.session.application_url });
    return { session, remote, page: browser.contexts()[0].pages()[0] };
  }

  it("reads fields outside form tags, in cross-origin iframes and open shadow roots without sending saved answers", async () => {
    const { session, remote, page } = await fixture(`<title>Application questions</title>
      <label for="first">First name</label><input id="first" value="PRIVATE_SAVED_VALUE">
      <label for="password">Password</label><input id="password" type="password" value="PASSWORD_SECRET">
      <input name="otp" value="OTP_SECRET"><input type="hidden" value="HIDDEN_SECRET">
      <div id="widget"></div><script>document.querySelector('#widget').attachShadow({mode:'open'}).innerHTML = '<label for="why">Why this role?</label><textarea id="why">PRIVATE_ANSWER</textarea>';</script>
      <iframe src="https://frame.example.com/apply"></iframe>`,
    `<title>Embedded application</title><label for="experience">Relevant project experience</label><textarea id="experience">FRAME_ANSWER_SECRET</textarea>`);
    await page.frameLocator("iframe").locator("textarea").waitFor();
    const scan = await runner.action(session.id, "scan");
    expect("fields" in scan && scan.fields.map((field) => field.label)).toEqual(["First name", "Why this role?", "Relevant project experience"]);
    expect("pageObservation" in scan && scan.pageObservation).toMatchObject({ readOnly: true, framesScanned: 2 });
    const analyzed = await runner.action(session.id, "analyze");
    expect("agentDecisions" in analyzed && analyzed.agentDecisions).toHaveLength(3);
    const analysisBody = remote.mock.calls.find(([path]) => path === "/agent/analyze")?.[1];
    expect(JSON.stringify(analysisBody)).not.toMatch(/PRIVATE_|PASSWORD_SECRET|OTP_SECRET|HIDDEN_SECRET|FRAME_ANSWER_SECRET|current_value/);
    expect(await page.evaluate(() => typeof (globalThis as unknown as Record<string, unknown>).__radarLocal)).toBe("undefined");
    await expect(runner.action(session.id, "answer", { fieldId: "anything", answer: "Do not write" })).rejects.toThrow("manualmente");
    expect(await page.locator("#first").inputValue()).toBe("PRIVATE_SAVED_VALUE");
  });

  it("captures the actual browser viewport locally without sending an image to the backend", async () => {
    const { session, remote } = await fixture("<title>Visible employer portal</title><h1>Application</h1>");
    const count = remote.mock.calls.length;
    const capture = await runner.action(session.id, "capture");
    expect("imageUrl" in capture && capture.imageUrl.startsWith("data:image/jpeg;base64,/9j/")).toBe(true);
    expect("title" in capture && capture.title).toBe("Visible employer portal");
    expect(remote.mock.calls).toHaveLength(count);
  });

  it("reports an empty page instead of requesting suggestions for zero questions", async () => {
    const { session, remote } = await fixture("<title>Sign in first</title><p>Open the application form</p>");
    await expect(runner.action(session.id, "analyze")).rejects.toThrow("No se encontraron preguntas");
    expect(remote.mock.calls.some(([path]) => path === "/agent/analyze")).toBe(false);
  });

  it("invalidates suggestions when a single-page form changes without changing the URL", async () => {
    const { session, page } = await fixture('<label for="answer">Why this role?</label><textarea id="answer"></textarea>');
    const analyzed = await runner.action(session.id, "analyze");
    expect("agentDecisions" in analyzed && analyzed.agentDecisions).toHaveLength(1);
    await page.locator("label").evaluate((element) => { element.textContent = "What is your availability?"; });
    const changed = await runner.action(session.id, "scan");
    expect("agentDecisions" in changed && changed.agentDecisions).toHaveLength(0);
  });

  it("reads a public ATS redirect in read-only mode and recovers after a sign-in popup closes", async () => {
    const { session, page } = await fixture('<label for="why">Why this role?</label><textarea id="why"></textarea>');
    await page.goto("https://apply.example.net/application");
    const popup = await browser.contexts()[0].newPage();
    await popup.goto("https://login.example.net/");
    await popup.close();
    const scan = await runner.action(session.id, "scan");
    expect("pageObservation" in scan && scan.pageObservation).toMatchObject({ readOnly: true, url: "https://apply.example.net/application" });
    expect("fields" in scan && scan.fields).toHaveLength(1);
    expect(await page.evaluate(() => typeof (globalThis as unknown as Record<string, unknown>).__radarLocal)).toBe("undefined");
  });

  it("retains the manual assessment boundary in a visible embedded document", async () => {
    const { session, page, remote } = await fixture('<iframe src="https://frame.example.com/assessment"></iframe>',
      '<title>Coding assessment</title><textarea aria-label="Solve this challenge"></textarea>');
    await page.frameLocator("iframe").locator("textarea").waitFor();
    await expect(runner.action(session.id, "analyze")).rejects.toThrow("manual review");
    expect(remote.mock.calls.some(([path]) => path === "/agent/analyze")).toBe(false);
  });
});
