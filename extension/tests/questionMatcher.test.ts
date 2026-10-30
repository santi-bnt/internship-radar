import { describe, expect, it } from "vitest";

import { matchQuestion } from "../src/shared/questionMatcher";
import { fieldPolicy, isFinalSubmitText } from "../src/shared/policies";

describe("sensitive application questions", () => {
  const questions: Array<[string, string, "AUTO_FILL_REVIEW_REQUIRED" | "CONFIRM_REQUIRED"]> = [
    ["Are you legally authorized to work in the United States?", "US_WORK_AUTHORIZATION", "AUTO_FILL_REVIEW_REQUIRED"],
    ["Will you now or in the future require visa sponsorship?", "US_SPONSORSHIP_REQUIRED", "AUTO_FILL_REVIEW_REQUIRED"],
    ["Are you legally authorized to work in Mexico?", "MEXICO_WORK_AUTHORIZATION", "AUTO_FILL_REVIEW_REQUIRED"],
    ["Will you require sponsorship to work in Mexico?", "SPONSORSHIP_CURRENT_COUNTRY", "AUTO_FILL_REVIEW_REQUIRED"],
    ["What is your country of citizenship?", "CITIZENSHIP", "AUTO_FILL_REVIEW_REQUIRED"],
    ["Please select your protected veteran status", "VETERAN_STATUS", "CONFIRM_REQUIRED"],
    ["Do you have a disability?", "DISABILITY_STATUS", "CONFIRM_REQUIRED"],
    ["Are you or a family member a government employee?", "GOVERNMENT_EMPLOYEE", "CONFIRM_REQUIRED"],
    ["Do you have an interest in Intel intellectual property?", "INTEL_IP_INTEREST", "CONFIRM_REQUIRED"],
    ["Were you previously employed by Intel?", "FORMER_INTEL_EMPLOYEE", "CONFIRM_REQUIRED"]
  ];

  it.each(questions)("classifies the confirmation policy for %s", (question, expectedKey, expectedPolicy) => {
    const result = matchQuestion(question);
    expect(result.questionKey).toBe(expectedKey);
    expect(result.policy).toBe(expectedPolicy);
    expect(result.confidence).toBeGreaterThanOrEqual(0.72);
  });

  it("makes uncertain compliance questions manual only", () => {
    expect(matchQuestion("Tell us anything else").policy).toBe("MANUAL_ONLY");
  });

  it("does not infer unrelated start-date questions from confirmed seasonal availability", () => {
    expect(matchQuestion("Can you start January 5?").policy).toBe("MANUAL_ONLY");
  });

  it("never treats authentication, attestation, or final submission as autofill", () => {
    expect(fieldPolicy("MFA verification code").policy).toBe("MANUAL_ONLY");
    expect(fieldPolicy("Electronic signature and certification").policy).toBe("MANUAL_ONLY");
    expect(isFinalSubmitText("Certify and Submit")).toBe(true);
  });
});
