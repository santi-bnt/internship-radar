import { beforeEach, describe, expect, it, vi } from "vitest";

import { GenericApplicationAdapter } from "../src/content/adapters/generic/GenericApplicationAdapter";
import { GreenhouseAdapter } from "../src/content/adapters/greenhouse/GreenhouseAdapter";
import { SmartRecruitersAdapter } from "../src/content/adapters/smartrecruiters/SmartRecruitersAdapter";
import { WorkdayAdapter } from "../src/content/adapters/workday/WorkdayAdapter";
import type { AgentFieldResolution } from "../src/shared/types";
import { makePayload } from "./fixtures";

const applicationFixture = `
  <form id="application_form" data-test="application" action="https://example.smartrecruiters.com/application">
    <div class="field" data-automation-id="formField"><label for="degree">Current degree</label><input id="degree" /></div>
    <div class="field" data-automation-id="formField"><label for="major">Field of study</label><select id="major"><option></option><option>Mechanical Engineering</option><option>Computer Science</option><option>Electrical Engineering</option><option>Other</option></select></div>
    <div class="field" data-automation-id="formField"><label for="graduation">Expected graduation date</label><input id="graduation" type="month" /></div>
    <div class="field" data-automation-id="formField"><label for="gpa">GPA</label><input id="gpa" /></div>
    <div class="field" data-automation-id="formField"><label for="areas">Areas of interest</label><textarea id="areas" maxlength="200"></textarea></div>
    <div class="field" data-automation-id="formField"><label for="python">Describe your Python experience</label><textarea id="python" maxlength="300"></textarea></div>
    <div class="field" data-automation-id="formField"><label for="why">Why this role?</label><textarea id="why" maxlength="300"></textarea></div>
    <fieldset data-automation-id="formField"><legend>Are you authorized to work in Mexico?</legend><label><input type="radio" name="auth" value="Yes" /> Yes</label><label><input type="radio" name="auth" value="No" /> No</label></fieldset>
    <fieldset data-automation-id="formField"><legend>Will you require sponsorship?</legend><label><input type="radio" name="sponsor" value="Yes" /> Yes</label><label><input type="radio" name="sponsor" value="No" /> No</label></fieldset>
    <div class="field" data-automation-id="formField"><label for="disability">Voluntary disability disclosure</label><select id="disability"><option>Choose</option><option>Yes</option><option>No</option></select></div>
    <div class="field" data-automation-id="formField"><label for="signature">Electronic attestation</label><input id="signature" /></div>
    <button id="submit" type="submit">Submit Application</button>
  </form>`;

describe("semantic application agent executor", () => {
  beforeEach(() => { document.body.innerHTML = applicationFixture; });

  it.each([
    ["Workday", () => new WorkdayAdapter(), "WORKDAY"],
    ["Greenhouse", () => new GreenhouseAdapter(), "GREENHOUSE"],
    ["SmartRecruiters", () => new SmartRecruitersAdapter(), "SMARTRECRUITERS"],
    ["Generic", () => new GenericApplicationAdapter(), "GENERIC"],
  ] as const)("executes validated structured decisions on %s without submitting", async (_name, factory, portal) => {
    const adapter = factory();
    const payload = makePayload(portal);
    const fields = adapter.detectFields(payload);
    const major = fields.find((field) => field.label.includes("Field of study"))!;
    const why = fields.find((field) => field.label.includes("Why this role"))!;
    const disability = document.getElementById("disability") as HTMLSelectElement;
    const signature = document.getElementById("signature") as HTMLInputElement;
    const submitted = vi.fn((event: Event) => event.preventDefault());
    document.getElementById("submit")!.addEventListener("click", submitted);
    const decisions: AgentFieldResolution[] = [
      {
        field_id: major.fieldId, canonical_field: "FIELD_OF_STUDY", question_category: "EDUCATION_MAPPING",
        action: "AUTO_FILL_REVIEW", selected_value: "Robotics and Digital Systems Engineering", selected_option: "Computer Science",
        confidence: 0.88, match_type: "RELATED_PROGRAMMING", reason_summary: "Robotics unavailable; closest programming option.",
        requires_review: true, evidence_ids: [], privacy_level: "NORMAL", provider: "DETERMINISTIC", execution_location: "LOCAL",
      },
      {
        field_id: why.fieldId, canonical_field: "JOB_SPECIFIC_ANSWER", question_category: "JOB_SPECIFIC_TEXT",
        action: "GENERATE_REVIEW", selected_value: "This role aligns with my verified Python and robotics project experience.",
        confidence: 0.92, match_type: "UNKNOWN", reason_summary: "Generated from verified evidence.",
        requires_review: true, evidence_ids: ["project_radar"], privacy_level: "NORMAL", provider: "DETERMINISTIC", execution_location: "LOCAL",
      },
    ];
    await adapter.fillThisPage(payload, [], decisions);
    expect((document.getElementById("major") as HTMLSelectElement).selectedOptions[0].textContent).toBe("Computer Science");
    expect((document.getElementById("why") as HTMLTextAreaElement).value).toContain("verified Python");
    expect(disability.value).toBe("Choose");
    expect(signature.value).toBe("");
    expect(submitted).not.toHaveBeenCalled();
  });

  it("rejects an unrecognized model action even if it is labeled as Submit", async () => {
    const adapter = new GenericApplicationAdapter();
    const payload = makePayload("GENERIC");
    const submit = vi.fn();
    document.getElementById("submit")!.addEventListener("click", submit);
    const field = adapter.detectFields(payload).find((item) => item.label.includes("Why this role"))!;
    const unsafe = [{
      field_id: field.fieldId, canonical_field: "FINAL_SUBMIT", question_category: "UNKNOWN",
      action: "SUBMIT", selected_value: "Submit Application", confidence: 1, match_type: "UNKNOWN",
      reason_summary: "Unsafe", requires_review: false, evidence_ids: [], privacy_level: "NORMAL",
      provider: "untrusted", execution_location: "LOCAL",
    }] as unknown as AgentFieldResolution[];
    await adapter.fillThisPage(payload, [], unsafe);
    expect(submit).not.toHaveBeenCalled();
  });

  it("executes the analyzed decision when a dynamic portal inserts another control", async () => {
    const adapter = new GenericApplicationAdapter();
    const payload = makePayload("GENERIC");
    const field = adapter.detectFields(payload).find((item) => item.label.includes("Why this role"))!;
    const decision: AgentFieldResolution = {
      field_id: field.fieldId,
      canonical_field: "JOB_SPECIFIC_ANSWER",
      question_category: "JOB_SPECIFIC_TEXT",
      action: "GENERATE_REVIEW",
      selected_value: "This answer is supported by verified project evidence.",
      selected_option: null,
      confidence: 0.92,
      match_type: "UNKNOWN",
      reason_summary: "Generated from verified evidence.",
      requires_review: true,
      evidence_ids: ["project_radar"],
      privacy_level: "NORMAL",
      provider: "DETERMINISTIC",
      execution_location: "LOCAL",
    };
    const inserted = document.createElement("input");
    inserted.setAttribute("aria-label", "Dynamically inserted helper field");
    document.getElementById("application_form")!.prepend(inserted);

    const result = await adapter.fillThisPage(payload, [], [decision]);

    expect((document.getElementById("why") as HTMLTextAreaElement).value).toContain("verified project evidence");
    expect(result.filled).toBe(1);
  });
});
