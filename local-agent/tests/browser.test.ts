import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { chromium, type Browser, type BrowserContext, type CDPSession, type Page } from "playwright";
import { readFile } from "node:fs/promises";
import { makePayload } from "../../extension/tests/fixtures";
import type { AssistantPageState } from "../../extension/src/shared/types";

describe("extension-free browser form", () => {
  let browser: Browser;
  let context: BrowserContext;
  let page: Page;
  let client: CDPSession;
  let contextId: number;
  async function run<T>(method: string, args: unknown[] = []): Promise<T> {
    const result = await client.send("Runtime.evaluate", { contextId, expression: `globalThis.__radarLocal.${method}(...${JSON.stringify(args)})`, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error("Browser rejected action");
    return result.result.value as T;
  }
  beforeAll(async () => {
    browser = await chromium.launch({ headless: true });
    context = await browser.newContext();
    page = await context.newPage();
    await page.route("https://careers.example.com/**", (route) => route.fulfill({ contentType: "text/html", body: `
      <h1>Application</h1><form onsubmit="event.preventDefault();window.submissions=(window.submissions||0)+1">
      <div class="field"><label for="name">Full name</label><input id="name"></div>
      <div class="field"><label for="why">Describe your Python experience</label><textarea id="why" maxlength="300"></textarea></div>
      <div class="field"><label for="password">Password</label><input id="password" type="password" value="never-read-this"></div>
      <div class="field"><label for="resume">Resume upload</label><input id="resume" type="file"></div>
      <button type="submit">Submit Application</button></form>` }));
    await page.goto("https://careers.example.com/apply");
    client = await context.newCDPSession(page);
    const { frameTree } = await client.send("Page.getFrameTree");
    contextId = (await client.send("Page.createIsolatedWorld", { frameId: frameTree.frame.id, worldName: "internship-radar-test" })).executionContextId;
    await client.send("Runtime.evaluate", { contextId, expression: await readFile(new URL("../dist/browser.js", import.meta.url), "utf8") });
    await run("connect", [makePayload("GENERIC")]);
  }, 30_000);
  afterAll(async () => { await browser?.close(); });

  it("reads questions without an extension or exposing profile snapshots to the employer world", async () => {
    const state = await run<AssistantPageState>("review");
    expect(state.fields.some((field) => field.label.includes("Python"))).toBe(true);
    expect(JSON.stringify(state)).not.toContain("never-read-this");
    expect(await page.evaluate(() => typeof (globalThis as unknown as Record<string, unknown>).__radarLocal)).toBe("undefined");
  });
  it("fills the reviewed answer into its exact field without submitting", async () => {
    const state = await run<AssistantPageState>("review");
    const field = state.fields.find((item) => item.label.includes("Python"))!;
    await run("setDecisions", [[{
      field_id: field.fieldId, canonical_field: "EXPERIENCE_ANSWER", question_category: "EXPERIENCE_QUESTION", action: "GENERATE_REVIEW",
      selected_value: "Built a Python API.", confidence: 0.92, requires_review: true, evidence_ids: ["project_api"],
    }]]);
    expect(await run("answer", [field.fieldId, "My reviewed academic project used Python."])).toBe(true);
    expect(await page.locator("#why").inputValue()).toContain("reviewed academic project");
    expect(await page.evaluate(() => (globalThis as unknown as Record<string, unknown>).submissions || 0)).toBe(0);
    expect(await page.locator("#password").inputValue()).toBe("never-read-this");
  });
  it("attaches only the CV bound to the session", async () => {
    await run("fill", [[{ kind: "RESUME", filename: "New_Job_CV.pdf", mimeType: "application/pdf", base64: Buffer.from("%PDF-1.4 fixture").toString("base64"), versionId: 18 }]]);
    expect(await page.locator("#resume").evaluate((element) => (element as HTMLInputElement).files?.[0]?.name)).toBe("New_Job_CV.pdf");
    expect(await page.evaluate(() => (globalThis as unknown as Record<string, unknown>).submissions || 0)).toBe(0);
  });
  it("stops on the final review page", async () => {
    await page.locator("h1").evaluate((element) => { element.textContent = "Review your application"; });
    expect(await run("next")).toBe(false);
    await expect(run("fill", [[]])).rejects.toThrow("rejected");
  });
});
