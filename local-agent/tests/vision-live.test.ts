import { expect, it } from "vitest";
import { chromium } from "playwright";
import { LocalVisionClient, sanitizedFormHtml } from "../src/vision";

// Explicit opt-in: a real local model and GPU/CPU are required. No employer or real candidate data.
it.skipIf(process.env.RADAR_LIVE_VISION_TEST !== "1")("reads both HTML and a screenshot-only question with actual local Ollama", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 960, height: 600 } });
    await page.setContent('<h1>Application questions</h1><label for="name">Full name</label><input id="name"><p>Relevant experience</p><canvas width="900" height="230"></canvas>');
    await page.locator("canvas").evaluate((element) => {
      const context = (element as HTMLCanvasElement).getContext("2d")!;
      context.fillStyle = "white"; context.fillRect(0, 0, 900, 230);
      context.fillStyle = "black"; context.font = "24px sans-serif";
      context.fillText("Describe your Python project experience.", 15, 40);
      context.strokeRect(15, 60, 820, 130);
    });
    const fields = [{ fieldId: "full-name", label: "Full name", controlType: "text", availableOptions: [] }];
    const image = await page.screenshot({ type: "jpeg", quality: 85 });
    const result = await new LocalVisionClient().interpret({ image: image.toString("base64"), html: sanitizedFormHtml(fields),
      fields: [{ id: "full-name", label: "Full name" }], evidence: [
        { id: "contact.full_name", kind: "FACT", label: "Full name", text: "Example Candidate" },
        { id: "project:0", kind: "PROJECT", label: "Python Monitor", text: "Python Monitor: Built a Python sensor monitoring application as an academic project." },
      ] }, AbortSignal.timeout(180000));
    expect(result.screen_state, JSON.stringify(result)).toBe("APPLICATION");
    expect(result.questions.some((question) => question.dom_field_id === "full-name")).toBe(true);
    const visual = result.questions.find((question) => /python.*project|project.*experience/i.test(question.label));
    expect(visual).toBeTruthy();
    expect(visual?.evidence_ids).toContain("project:0");
  } finally { await browser.close(); }
}, 190000);
