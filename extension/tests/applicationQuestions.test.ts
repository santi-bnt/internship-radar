import { describe, expect, it, vi } from "vitest";

import { ApplicationQuestions } from "../src/sidepanel/applicationQuestions";
import { GenericApplicationAdapter } from "../src/content/adapters/generic/GenericApplicationAdapter";
import { ApplicationAssistantCore } from "../src/content/ApplicationAssistantCore";
import type { AgentFieldResolution, AssistantPageState } from "../src/shared/types";
import { makePayload } from "./fixtures";

function decision(fieldId: string): AgentFieldResolution {
  return {
    field_id: fieldId, canonical_field: "EXPERIENCE_ANSWER", question_category: "EXPERIENCE_QUESTION",
    action: "GENERATE_REVIEW", selected_value: "Built a Python API.", confidence: 0.92,
    match_type: "UNKNOWN", reason_summary: "Supported by the verified API project.", requires_review: true,
    evidence_ids: ["project_api"], privacy_level: "NORMAL", provider: "DETERMINISTIC", execution_location: "LOCAL",
  };
}

describe("application question assistance", () => {
  it("shows several questions, preserves draft/focus across polls and applies the edited answer to its field only", async () => {
    const container = document.createElement("div");
    document.body.replaceChildren(container);
    const apply = vi.fn().mockResolvedValue(undefined);
    const panel = new ApplicationQuestions(container, apply);
    const state = {
      connected: true, applicationSessionId: 1, paused: false, isReviewPage: false, assessmentType: "",
      fields: ["Why this role?", "Describe your Python experience"].map((label, index) => ({
        fieldId: `field${index}`, label, controlType: "textarea", required: true, maxlength: 200,
      })),
      agentDecisions: [decision("field0"), decision("field1")],
    } as AssistantPageState;
    panel.render(state, "https://example.com/apply");
    expect(container.querySelectorAll("textarea")).toHaveLength(2);
    const editor = container.querySelector("textarea")!;
    editor.value = "My revised and reviewed answer.";
    editor.dispatchEvent(new Event("input"));
    editor.focus();
    panel.render(state, "https://example.com/apply");
    expect(document.activeElement).toBe(editor);
    expect(editor.value).toContain("revised");
    container.querySelector<HTMLButtonElement>("button.primary")!.click();
    await Promise.resolve();
    expect(apply).toHaveBeenCalledWith({ type: "APPLY_REVIEWED_ANSWER", payload: {
      fieldId: "field0", answer: "My revised and reviewed answer.",
    } });
    panel.render({ ...state, applicationSessionId: 2 }, "https://example.com/apply");
    expect(container.querySelector("textarea")!.value).toBe("Built a Python API.");
  });

  it("uses textContent for portal labels and prevents applying unknown/manual answers", () => {
    const container = document.createElement("div");
    const panel = new ApplicationQuestions(container, vi.fn());
    panel.render({
      connected: true, fields: [{ fieldId: "q", label: "<img src=x onerror=alert(1)>", controlType: "textarea" }],
      agentDecisions: [{ ...decision("q"), question_category: "UNKNOWN", action: "MANUAL_ONLY", selected_value: null }],
    } as AssistantPageState, "https://example.com/apply");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector<HTMLButtonElement>("button.primary")!.disabled).toBe(true);
  });

  it("applies reviewed edits with character limits and leaves unrelated fields untouched", async () => {
    document.body.innerHTML = `<form><div class="field"><label for="why">Why this role?</label><textarea id="why" maxlength="100">Old answer</textarea></div><input id="other" value="Keep me"></form>`;
    const adapter = new GenericApplicationAdapter();
    const field = adapter.detectFields(makePayload("GENERIC")).find((item) => item.label.includes("Why this role"))!;
    expect(await adapter.fillReviewedText(field.fieldId, "My reviewed answer")).toBe(true);
    expect((document.getElementById("why") as HTMLTextAreaElement).value).toBe("My reviewed answer");
    expect((document.getElementById("other") as HTMLInputElement).value).toBe("Keep me");
    await expect(adapter.fillReviewedText(field.fieldId, "x".repeat(101))).rejects.toThrow("character limit");
  });

  it("rejects applying stale and legal decisions through the question editor", async () => {
    document.body.innerHTML = `<form><div class="field"><label for="why">Why this role?</label><textarea id="why"></textarea></div></form>`;
    const core = new ApplicationAssistantCore(makePayload("GENERIC"));
    const field = core.review().fields[0];
    await expect(core.applyReviewedAnswer(decision("stale-field"), "Test")).rejects.toThrow("current application questions");
    await expect(core.applyReviewedAnswer({ ...decision(field.fieldId), question_category: "WORK_AUTHORIZATION" }, "Yes")).rejects.toThrow("current application questions");
    expect((document.getElementById("why") as HTMLTextAreaElement).value).toBe("");
  });
});
