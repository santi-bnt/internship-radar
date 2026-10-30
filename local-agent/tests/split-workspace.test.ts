import { describe, expect, it } from "vitest";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

describe("split-screen assistant window", () => {
  it("moves the live controls into a popup and restores them without losing edited answers", async () => {
    const frontend = fileURLToPath(new URL("../../frontend/", import.meta.url));
    const bundle = await build({
      absWorkingDir: frontend, bundle: true, write: false, platform: "browser", format: "iife", jsx: "automatic",
      stdin: { resolveDir: frontend, loader: "tsx", contents: `
        import { createRoot } from "react-dom/client";
        import Controls from "./components/LocalApplicationControls";
        createRoot(document.getElementById("root")).render(<Controls connection={{ id: "test-session", key: "test-key" }} onClose={() => {}} />);
      ` },
    });
    const state = {
      currentSection: "Application questions", applicationPageUrl: "https://example.com/apply",
      fields: [{ fieldId: "why", label: "Why this role?", controlType: "textarea", currentValue: "", required: true }],
      pendingQuestions: [], agentDecisions: [{ field_id: "why", question_category: "JOB_SPECIFIC_TEXT",
        action: "GENERATE_REVIEW", selected_value: "Verified project experience", reason_summary: "Supported by projects" }],
      isReviewPage: false, isConfirmationPage: false, assessmentType: null,
      pageObservation: { title: "Current employer application", url: "https://example.com/apply", readOnly: true,
        readAt: "2026-10-25T12:00:00Z", framesScanned: 2, unreadableFrames: 0, documentKey: "current-form" },
    };
    const browser = await chromium.launch({ headless: true });
    try {
      const context = await browser.newContext();
      let arranged: unknown;
      await context.route("http://127.0.0.1:43123/**", async (route) => {
        const split = route.request().url().endsWith("/split-screen");
        if (split) arranged = route.request().postDataJSON();
        await route.fulfill({ contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Private-Network": "true" },
          body: JSON.stringify(split ? { arranged: true } : state) });
      });
      await context.route("https://your-app.vercel.app/**", (route) => route.fulfill({
        contentType: "text/html", body: `<div id="root"></div><script>${bundle.outputFiles[0].text}</script>`,
      }));
      const page = await context.newPage();
      await page.goto("https://your-app.vercel.app/split-fixture");
      await page.getByText("Página que está leyendo: Current employer application").waitFor();
      expect(await page.getByRole("button", { name: "Completar perfil y adjuntar CV" }).count()).toBe(0);
      expect(await page.getByRole("button", { name: "Copiar respuesta", exact: true }).isVisible()).toBe(true);
      await page.locator("textarea").fill("My reviewed answer");
      const opened = page.waitForEvent("popup");
      await page.getByRole("button", { name: "Pantalla dividida: portal + asistente" }).click();
      const popup = await opened;
      await popup.getByRole("button", { name: "Volver al panel principal" }).waitFor();
      expect(await popup.locator("textarea").inputValue()).toBe("My reviewed answer");
      expect(popup.url()).toBe("about:blank");
      await page.waitForFunction(() => !document.querySelector("textarea"));
      expect(arranged).toMatchObject({ left: 0, top: 0 });
      await popup.getByRole("button", { name: "Volver al panel principal" }).click();
      await page.locator("textarea").waitFor();
      expect(await page.locator("textarea").inputValue()).toBe("My reviewed answer");
    } finally { await browser.close(); }
  }, 30_000);
});
