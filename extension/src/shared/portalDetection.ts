import { companyPolicy, portalSupport } from "./companyRegistry";
import type { PortalDetection, PortalType } from "./types";

type DetectionRule = { portal: PortalType; evidence: string; score: number; matches: () => boolean };

function has(selector: string): boolean {
  try { return Boolean(document.querySelector(selector)); } catch { return false; }
}

export function detectPortal(urlValue = window.location.href, company = ""): PortalDetection {
  const url = new URL(urlValue);
  const host = url.hostname.toLocaleLowerCase();
  const path = url.pathname.toLocaleLowerCase();
  const policy = companyPolicy(company);
  const rules: DetectionRule[] = [
    { portal: "WORKDAY", score: 0.99, evidence: "Workday DOM automation identifiers", matches: () => has("[data-automation-id], [data-uxi-widget-type]") && has("[data-automation-id*='formField'], [data-automation-id*='jobPosting']") },
    { portal: "GREENHOUSE", score: 0.99, evidence: "Greenhouse application form fingerprint", matches: () => has("#application_form, #application-form, form.application--form, form[action*='/embed/job_app'], form[action*='greenhouse'], [data-mapped='true'], [class*='greenhouse'] form") },
    { portal: "MICROSOFT_CAREERS", score: 0.98, evidence: "Microsoft Careers application fingerprint", matches: () => has("[data-automation-id*='microsoft'], form[action*='careers.microsoft']") || (policy.portal_type === "MICROSOFT_CAREERS" && has("[data-testid*='application']")) },
    { portal: "AMAZON_JOBS", score: 0.98, evidence: "Amazon Jobs application fingerprint", matches: () => has("[data-test-id*='application'], form[action*='amazon.jobs']") || (policy.portal_type === "AMAZON_JOBS" && has("[data-testid*='application']")) },
    { portal: "ORACLE_CAREERS", score: 0.98, evidence: "Oracle recruiting candidate-experience fingerprint", matches: () => has("[data-oj-binding-provider], oj-input-text, [class*='candidate-experience'], form[action*='oraclecloud']") },
    { portal: "WORKDAY", score: 0.94, evidence: "Workday hostname", matches: () => host.includes("myworkdayjobs.com") || path.includes("/workday/") },
    { portal: "GREENHOUSE", score: 0.94, evidence: "Greenhouse hostname", matches: () => host.includes("greenhouse.io") || host === "grnh.se" },
    { portal: "MICROSOFT_CAREERS", score: 0.94, evidence: "Microsoft Careers hostname", matches: () => host === "jobs.careers.microsoft.com" || host === "careers.microsoft.com" },
    { portal: "AMAZON_JOBS", score: 0.94, evidence: "Amazon Jobs hostname", matches: () => host === "amazon.jobs" || host.endsWith(".amazon.jobs") },
    { portal: "ORACLE_CAREERS", score: 0.94, evidence: "Oracle recruiting hostname", matches: () => host === "careers.oracle.com" || host.endsWith(".oraclecloud.com") },
    { portal: "LEVER", score: 0.94, evidence: "Lever hostname", matches: () => host === "jobs.lever.co" || host.endsWith(".lever.co") },
    { portal: "ASHBY", score: 0.94, evidence: "Ashby hostname", matches: () => host === "jobs.ashbyhq.com" || host.endsWith(".ashbyhq.com") },
    { portal: "SMARTRECRUITERS", score: 0.94, evidence: "SmartRecruiters hostname", matches: () => host.includes("smartrecruiters.com") },
    { portal: "GOOGLE_CAREERS", score: 0.94, evidence: "Google Careers URL", matches: () => host.includes("google.com") && path.includes("/about/careers") }
  ];
  const matched = rules.find((rule) => rule.matches());
  if (matched) return { portalType: matched.portal, confidence: matched.score, evidence: [matched.evidence], companyId: policy.company_id, supportStatus: portalSupport[matched.portal] };

  const registryMatch = policy.known_domains.some((domain) => host === domain || host.endsWith(`.${domain}`));
  if (registryMatch) {
    return { portalType: policy.portal_type, confidence: 0.76, evidence: [`Company registry match for ${policy.company_id}`], companyId: policy.company_id, supportStatus: policy.support_status };
  }
  return { portalType: "GENERIC", confidence: 0.55, evidence: ["Unknown career portal; limited safe-field mode"], companyId: policy.company_id, supportStatus: "BETA" };
}
