import type { FieldPolicy } from "./types";

const aliases: Record<string, string[]> = {
  US_WORK_AUTHORIZATION: ["authorized to work in the us", "authorized to work in the united states", "legally authorized to work in the united states", "legally authorized to work for any employer in the united states", "not currently authorized to work in the united states"],
  US_SPONSORSHIP_REQUIRED: ["require sponsorship", "need sponsorship", "visa sponsorship", "immigration sponsorship"],
  MEXICO_WORK_AUTHORIZATION: ["authorized to work in mexico", "legally authorized to work in mexico"],
  WORK_AUTHORIZATION_CURRENT_COUNTRY: ["authorized to work in the country where this job is located", "authorized to work in this country"],
  SPONSORSHIP_CURRENT_COUNTRY: ["require sponsorship to work in mexico", "sponsorship to work in mexico", "require sponsorship to work in this country", "sponsorship in the country in which this position is based"],
  CITIZENSHIP: ["citizenship", "country of citizenship", "citizen of which country"],
  VETERAN_STATUS: ["veteran status", "protected veteran", "military veteran"],
  DISABILITY_STATUS: ["disability status", "have a disability", "self identify disability"],
  GOVERNMENT_EMPLOYEE: ["government employee", "employed by a government"],
  FAMILY_GOVERNMENT_EMPLOYEE: ["family member government", "relative government employee"],
  SECONDARY_EMPLOYMENT: ["secondary employment", "outside employment", "other employment"],
  NONCOMPETE_RESTRICTION: ["non compete", "noncompete", "restrictive covenant"],
  NDA_NONCOMPETE: ["non disclosure agreement", "nda", "non compete agreement"],
  EXPORT_CONTROL: ["export control", "export authorization", "itar", "ear regulation"],
  RELOCATION: ["willing to relocate", "relocation"],
  SALARY_EXPECTATION: ["salary expectation", "expected salary", "desired compensation"],
  CRIMINAL_LEGAL_DISCLOSURE: ["criminal conviction", "criminal record", "legal disclosure"],
  FORMER_INTEL_EMPLOYEE: ["former intel employee", "previously employed by intel", "worked for intel"],
  FORMER_GE_EMPLOYEE: ["former ge employee", "previously employed by ge", "worked for ge"],
  FORMER_EY_EMPLOYEE: ["former ey employee", "previously employed by ey"],
  EY_SAN_JOSE_FAMILY: ["ey san jose family", "relative at ey san jose"],
  INTEL_IP_INTEREST: ["intel intellectual property", "interest in intel ip", "intellectual property interest"],
  INTELLECTUAL_PROPERTY: ["intellectual property ownership", "own intellectual property", "intellectual property disclosure"],
  CONFLICT_OF_INTEREST: ["conflict of interest", "potential conflict", "personal or financial conflict"],
  FULL_TIME_SUMMER_AVAILABILITY: ["available for a full time onsite internship this summer", "available for full time summer internship", "work full time during the summer", "available may june through august september"],
  SPRING_SUMMER_COMBINED_AVAILABILITY: ["interested and available for a combined spring and summer internship", "combined spring and summer internship", "available january to august or september"],
  JOB_DISCOVERY_SOURCE: ["how you heard about zipline and this job", "how did you hear about us", "how did you hear about this job", "application source"]
};

const autoFillReviewKeys = new Set([
  "US_WORK_AUTHORIZATION",
  "US_SPONSORSHIP_REQUIRED",
  "MEXICO_WORK_AUTHORIZATION",
  "WORK_AUTHORIZATION_CURRENT_COUNTRY",
  "SPONSORSHIP_CURRENT_COUNTRY",
  "CITIZENSHIP",
  "FULL_TIME_SUMMER_AVAILABILITY",
  "SPRING_SUMMER_COMBINED_AVAILABILITY",
  "JOB_DISCOVERY_SOURCE"
]);

export function normalizeQuestion(value: string): string {
  return value.toLocaleLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
}

function similarity(left: string, right: string): number {
  if (left === right) return 1;
  if (left.includes(right)) return Math.min(0.98, 0.76 + right.length / Math.max(left.length, 1) * 0.22);
  const a = new Set(left.split(" "));
  const b = new Set(right.split(" "));
  const intersection = [...a].filter((word) => b.has(word)).length;
  return intersection / Math.max(new Set([...a, ...b]).size, 1);
}

export function matchQuestion(question: string, companyAliases: Record<string, string[]> = {}): { questionKey: string; confidence: number; policy: FieldPolicy } {
  const normalized = normalizeQuestion(question);
  if (!normalized) return { questionKey: "UNKNOWN", confidence: 0, policy: "MANUAL_ONLY" };
  let questionKey = "UNKNOWN";
  let confidence = 0;
  const keys = new Set([...Object.keys(aliases), ...Object.keys(companyAliases)]);
  for (const key of keys) {
    const values = [...(aliases[key] || []), ...(companyAliases[key] || [])];
    for (const alias of values) {
      const score = similarity(normalized, alias);
      if (score > confidence) ({ questionKey, confidence } = { questionKey: key, confidence: score });
    }
  }
  if (confidence < 0.72) return { questionKey: "UNKNOWN", confidence, policy: "MANUAL_ONLY" };
  return { questionKey, confidence, policy: autoFillReviewKeys.has(questionKey) ? "AUTO_FILL_REVIEW_REQUIRED" : "CONFIRM_REQUIRED" };
}

export const sensitiveQuestionKeys = new Set(Object.keys(aliases));
