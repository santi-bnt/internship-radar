import { afterEach, describe, expect, it, vi } from "vitest";
import { chromium, type Browser } from "playwright";
import { readFile } from "node:fs/promises";
import { LocalBrowserRunner } from "../src/runner";
import { LocalVisionClient, type VisionResult } from "../src/vision";
import { SessionApi } from "../src/remote";
import { makePayload } from "../../extension/tests/fixtures";

vi.mock("../src/security", async (load) => ({ ...await load<typeof import("../src/security")>(), validatePortalUrl: vi.fn(async (url: string) => new URL(url)) }));

describe("hybrid local analysis in a real browser session", () => {
  let runner: LocalBrowserRunner;
  let browser: Browser;
  afterEach(async () => { await runner?.close(); vi.restoreAllMocks(); });
  async function fixture() {
    const payload = makePayload("GENERIC");
    payload.session.application_url = "https://example.com/application";
    const launch = chromium.launch.bind(chromium);
    vi.spyOn(chromium, "launch").mockImplementation(async (options) => {
      browser = await launch(options);
      const newContext = browser.newContext.bind(browser);
      vi.spyOn(browser, "newContext").mockImplementation(async (options) => {
        const context = await newContext(options), newPage = context.newPage.bind(context);
        vi.spyOn(context, "newPage").mockImplementation(async () => {
          const page = await newPage();
          await page.route("https://example.com/**", (route) => route.fulfill({ contentType: "text/html", body:
            '<title>Application</title><label for="why">Describe your project experience</label><textarea id="why">PRIVATE_SAVED_ANSWER</textarea><canvas id="question" width="600" height="80"></canvas><script>document.querySelector("canvas").getContext("2d").fillText("Which verified skills do you have?", 10, 30)</script>' }));
          return page;
        });
        return context;
      });
      return browser;
    });
    const remote = vi.spyOn(SessionApi.prototype, "json").mockResolvedValue(payload);
    const vision = new LocalVisionClient();
    const inference = vi.spyOn(vision, "interpret").mockImplementation(async (input) => ({ screen_state: "APPLICATION", questions: [
      { label: input.fields[0].label, dom_field_id: input.fields[0].id, control_type: "textarea", required: true,
        options: [], confidence: 0.95, canonical_field: "PROJECTS", evidence_ids: ["project:0"] },
      { label: "Which verified skills do you have?", dom_field_id: "", control_type: "text", required: false,
        options: [], confidence: 0.9, canonical_field: "SKILLS", evidence_ids: ["skill:0"] },
    ] }));
    const connection = { sessionId: payload.session.id, token: "scoped-secret-token", expiresAt: new Date(Date.now() + 60000).toISOString(), apiBaseUrl: "http://localhost:3000/api/backend", applicationUrl: payload.session.application_url };
    runner = new LocalBrowserRunner(await readFile(new URL("../dist/browser.js", import.meta.url), "utf8"), true, vision);
    const session = await runner.start(connection);
    return { session, inference, remote, connection, page: browser.contexts()[0].pages()[0] };
  }

  it.skipIf(process.env.RADAR_LIVE_VISION_TEST !== "1")("runs the full hybrid reader against actual loopback Ollama", async () => {
    const { session, inference, remote } = await fixture();
    inference.mockRestore();
    const state = await runner.action(session.id, "analyze-local");
    expect("localVision" in state && state.localVision?.engine).toBe("LOCAL_HTML_VISION");
    expect("agentDecisions" in state && state.agentDecisions.length).toBeGreaterThan(0);
    expect(remote).toHaveBeenCalledTimes(1);
  }, 190000);

  it("combines DOM and screenshot questions locally and never forwards the form/image to SessionApi", async () => {
    const { session, inference, remote, page } = await fixture();
    const state = await runner.action(session.id, "analyze-local");
    expect("localVision" in state && state.localVision).toMatchObject({ engine: "LOCAL_HTML_VISION", domFields: 1, imageQuestions: 1 });
    expect("agentDecisions" in state && state.agentDecisions).toHaveLength(2);
    expect("pageObservation" in state && state.pageObservation?.readOnly).toBe(true);
    const input = inference.mock.calls[0][0];
    expect(input.image.startsWith("/9j/")).toBe(true);
    expect(input.html).toContain("Describe your project experience");
    expect(JSON.stringify(input)).not.toContain("PRIVATE_SAVED_ANSWER");
    expect(remote).toHaveBeenCalledTimes(1);
    expect(await page.locator("textarea").inputValue()).toBe("PRIVATE_SAVED_ANSWER");
    await expect(runner.action(session.id, "answer", { fieldId: "why", answer: "anything" })).rejects.toThrow("manualmente");
  });

  it("discards a result after same-URL navigation and does not reuse it for the new form", async () => {
    const { session, inference, page } = await fixture();
    inference.mockImplementationOnce(async () => {
      await page.reload();
      return { screen_state: "APPLICATION", questions: [] };
    });
    await expect(runner.action(session.id, "analyze-local")).rejects.toThrow("cambiaron");
    const state = await runner.action(session.id, "scan");
    expect("localVision" in state).toBe(false);
  });

  it("does not fall back to cloud analysis if the local model is unavailable", async () => {
    const { session, inference, remote } = await fixture();
    inference.mockRejectedValueOnce(new Error("Local model unavailable"));
    await expect(runner.action(session.id, "analyze-local")).rejects.toThrow("unavailable");
    expect(remote).toHaveBeenCalledTimes(1);
  });

  it("invalidates local image suggestions when the viewport changes", async () => {
    const { session, page } = await fixture();
    await runner.action(session.id, "analyze-local");
    await page.setViewportSize({ width: 1000, height: 700 });
    const scan = await runner.action(session.id, "scan");
    expect("agentDecisions" in scan && scan.agentDecisions).toHaveLength(0);
    expect("localVision" in scan).toBe(false);
  });

  it("rejects output if the bound session expires during local inference", async () => {
    const { session, inference, connection } = await fixture();
    inference.mockImplementationOnce(async () => {
      connection.expiresAt = new Date(Date.now() - 1000).toISOString();
      return { screen_state: "APPLICATION", questions: [] } as VisionResult;
    });
    await expect(runner.action(session.id, "analyze-local")).rejects.toThrow("expired");
  });

  it("keeps login, assessment and final review screens manual", async () => {
    const { session, inference, remote } = await fixture();
    inference.mockResolvedValueOnce({ screen_state: "ASSESSMENT", questions: [] });
    await expect(runner.action(session.id, "analyze-local")).rejects.toThrow(/revisa/i);
    expect(remote).toHaveBeenCalledTimes(1);
  });

  it("cancels local inference while preserving the application session", async () => {
    const { session, inference } = await fixture();
    inference.mockImplementationOnce(async (_input, signal) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
    }));
    const pending = runner.action(session.id, "analyze-local");
    await vi.waitFor(() => expect(inference).toHaveBeenCalledTimes(1));
    expect(await runner.action(session.id, "cancel-analysis")).toEqual({ cancelled: true });
    await expect(pending).rejects.toThrow("cancelled");
    expect("fields" in await runner.action(session.id, "scan")).toBe(true);
  });

  it("does not reuse a previous candidate's evidence when a new scoped session starts", async () => {
    const { session, inference, remote } = await fixture();
    await runner.action(session.id, "analyze-local");
    await runner.close();
    const second = makePayload("GENERIC");
    second.profile.contact.full_name = "Second independent candidate";
    second.ai_settings.owner_user_id = "second-owner";
    second.session.id = 99;
    second.session.application_url = "https://example.com/application";
    remote.mockResolvedValueOnce(second);
    const next = await runner.start({ sessionId: 99, token: "second-scoped-token", expiresAt: new Date(Date.now() + 60000).toISOString(),
      apiBaseUrl: "http://localhost:3000/api/backend", applicationUrl: second.session.application_url });
    await runner.action(next.id, "analyze-local");
    const evidence = inference.mock.calls[1][0].evidence;
    expect(evidence.find((item) => item.id === "contact.full_name")?.text).toBe("Second independent candidate");
    expect(evidence.some((item) => item.text.includes("Santiago Example"))).toBe(false);
  });
});
