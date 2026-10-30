import type { CompanyApplicationPolicy, PortalSupportStatus, PortalType } from "./types";

export const portalSupport: Record<PortalType, PortalSupportStatus> = {
  WORKDAY: "SUPPORTED",
  GREENHOUSE: "SUPPORTED",
  MICROSOFT_CAREERS: "BETA",
  AMAZON_JOBS: "BETA",
  ORACLE_CAREERS: "BETA",
  GENERIC: "BETA",
  LEVER: "UNSUPPORTED",
  ASHBY: "UNSUPPORTED",
  SMARTRECRUITERS: "BETA",
  GOOGLE_CAREERS: "UNSUPPORTED",
  UNKNOWN: "UNSUPPORTED"
};

export const companyPortalRegistry: CompanyApplicationPolicy[] = [
  {
    company_id: "intel", company_name: "Intel",
    known_domains: ["intel.wd1.myworkdayjobs.com", "jobs.intel.com"],
    portal_type: "WORKDAY", application_adapter: "WorkdayAdapter", company_policy_key: "INTEL",
    company_specific_rules: { compliance_confirmation_required: true },
    known_question_aliases: {
      FORMER_INTEL_EMPLOYEE: ["previously employed by intel", "former intel employee"],
      INTEL_IP_INTEREST: ["interest in intel intellectual property"]
    }, support_status: "SUPPORTED"
  },
  {
    company_id: "ge_aerospace", company_name: "GE Aerospace",
    known_domains: ["geaerospace.wd5.myworkdayjobs.com", "careers.geaerospace.com"],
    portal_type: "WORKDAY", application_adapter: "WorkdayAdapter", company_policy_key: "GE_AEROSPACE",
    company_specific_rules: { government_questions_confirmation_required: true },
    known_question_aliases: {
      FORMER_GE_EMPLOYEE: ["previously employed by ge", "former ge employee"],
      GOVERNMENT_EMPLOYEE: ["currently or formerly employed by a government"],
      FAMILY_GOVERNMENT_EMPLOYEE: ["family member employed by a government"]
    }, support_status: "SUPPORTED"
  },
  {
    company_id: "zipline", company_name: "Zipline",
    known_domains: ["zipline.com", "www.zipline.com", "boards.greenhouse.io", "job-boards.greenhouse.io"],
    portal_type: "GREENHOUSE", application_adapter: "GreenhouseAdapter", company_policy_key: "ZIPLINE",
    company_specific_rules: { canonical_company_only: true, greenhouse_board_token: "flyzipline" }, known_question_aliases: {}, support_status: "SUPPORTED"
  },
  {
    company_id: "microsoft", company_name: "Microsoft",
    known_domains: ["jobs.careers.microsoft.com", "careers.microsoft.com"],
    portal_type: "MICROSOFT_CAREERS", application_adapter: "MicrosoftCareersAdapter", company_policy_key: "MICROSOFT",
    company_specific_rules: { preserve_saved_profile: true }, known_question_aliases: {}, support_status: "BETA"
  },
  {
    company_id: "amazon_aws", company_name: "Amazon / AWS",
    known_domains: ["amazon.jobs", "www.amazon.jobs"],
    portal_type: "AMAZON_JOBS", application_adapter: "AmazonJobsAdapter", company_policy_key: "AMAZON",
    company_specific_rules: { preserve_saved_profile: true, pause_on_assessment: true }, known_question_aliases: {}, support_status: "BETA"
  },
  {
    company_id: "oracle", company_name: "Oracle",
    known_domains: ["careers.oracle.com", "oraclecloud.com"],
    portal_type: "ORACLE_CAREERS", application_adapter: "OracleCareersAdapter", company_policy_key: "ORACLE",
    company_specific_rules: { preserve_saved_profile: true, special_program_gate: true }, known_question_aliases: {}, support_status: "BETA"
  }
];

function normalizedCompany(value: string): string {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export function companyPolicy(company: string): CompanyApplicationPolicy {
  const id = normalizedCompany(company);
  const aliases: Record<string, string> = {
    intel_corporation: "intel", ge: "ge_aerospace", general_electric: "ge_aerospace",
    amazon: "amazon_aws", aws: "amazon_aws", amazon_web_services: "amazon_aws", microsoft_corporation: "microsoft"
  };
  const resolved = aliases[id] || id;
  return companyPortalRegistry.find((entry) => entry.company_id === resolved) || {
    company_id: resolved || "unknown", company_name: company || "Unknown company", known_domains: [],
    portal_type: "GENERIC", application_adapter: "GenericApplicationAdapter", company_policy_key: "GENERIC",
    company_specific_rules: {}, known_question_aliases: {}, support_status: "BETA"
  };
}
