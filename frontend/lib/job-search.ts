import type {
  SearchCriteria,
  SearchRemoteScope,
  SearchRoleCategory,
  SearchRun,
} from "@/lib/types";

/** A running search has no stable result membership yet. */
export function canShowSearchRunResults(run: Pick<SearchRun, "search_type" | "status">): boolean {
  return run.search_type === "custom" && (run.status === "completed" || run.status === "partial");
}

export const COMPANY_SUGGESTIONS = [
  "Oracle",
  "Intel",
  "NVIDIA",
  "AMD",
  "Qualcomm",
  "NXP",
  "Microsoft",
  "Amazon",
  "Google",
  "Duolingo",
  "Roblox",
  "Uber",
  "Synopsys",
  "Cadence",
  "Arm",
];

export const ROLE_OPTIONS: Array<{ value: SearchRoleCategory; label: string }> = [
  { value: "SOFTWARE_ENGINEERING", label: "Software" },
  { value: "EMBEDDED_FIRMWARE", label: "Embedded / Firmware" },
  { value: "ROBOTICS", label: "Robotics" },
  { value: "AI_MACHINE_LEARNING", label: "AI / ML" },
  { value: "COMPUTER_VISION", label: "Computer Vision" },
  { value: "BACKEND", label: "Backend" },
  { value: "FULL_STACK", label: "Full Stack" },
  { value: "FPGA_DIGITAL_DESIGN", label: "FPGA / Digital Design" },
  { value: "HARDWARE_VALIDATION", label: "Hardware Validation" },
  { value: "ELECTRICAL_VALIDATION", label: "Electrical Validation" },
  { value: "DATA_ALGORITHMS", label: "Data / Algorithms" },
  { value: "RESEARCH_ENGINEERING", label: "Research / Research Engineering" },
  { value: "OTHER", label: "Other" },
];

export const REMOTE_SCOPE_LABELS: Record<SearchRemoteScope, string> = {
  MEXICO: "Mexico",
  LATAM: "LATAM",
  GLOBAL: "Global",
  US_ONLY: "US-only",
  UNKNOWN: "Unknown",
};

export const DEFAULT_SEARCH_CRITERIA: SearchCriteria = {
  companies: [],
  target_companies_only: false,
  work_models: ["ANY"],
  remote_scopes: ["MEXICO", "LATAM", "GLOBAL"],
  countries: [],
  states: [],
  cities: [],
  role_categories: [],
  include_keywords: [],
  exclude_keywords: ["Senior", "Staff", "Principal"],
  only_realistically_eligible: true,
  include_unknown_eligibility: true,
  source_mode: "OFFICIAL_AND_COMMUNITY",
  posted_within_days: 14,
  limit: 50,
};

export type SearchPreset = {
  id: string;
  label: string;
  description: string;
  criteria: SearchCriteria;
};

function copyCriteria(overrides: Partial<SearchCriteria> = {}): SearchCriteria {
  return {
    ...DEFAULT_SEARCH_CRITERIA,
    ...overrides,
    companies: [...(overrides.companies ?? DEFAULT_SEARCH_CRITERIA.companies)],
    work_models: [...(overrides.work_models ?? DEFAULT_SEARCH_CRITERIA.work_models)],
    remote_scopes: [...(overrides.remote_scopes ?? DEFAULT_SEARCH_CRITERIA.remote_scopes)],
    countries: [...(overrides.countries ?? DEFAULT_SEARCH_CRITERIA.countries)],
    states: [...(overrides.states ?? DEFAULT_SEARCH_CRITERIA.states)],
    cities: [...(overrides.cities ?? DEFAULT_SEARCH_CRITERIA.cities)],
    role_categories: [...(overrides.role_categories ?? DEFAULT_SEARCH_CRITERIA.role_categories)],
    include_keywords: [...(overrides.include_keywords ?? DEFAULT_SEARCH_CRITERIA.include_keywords)],
    exclude_keywords: [...(overrides.exclude_keywords ?? DEFAULT_SEARCH_CRITERIA.exclude_keywords)],
  };
}

export const SEARCH_PRESETS: SearchPreset[] = [
  {
    id: "recommended",
    label: "Recommended for Me",
    description: "Mexico and compatible remote technical internships.",
    criteria: copyCriteria({
      work_models: ["ANY"],
      countries: ["Mexico"],
      role_categories: ["SOFTWARE_ENGINEERING", "EMBEDDED_FIRMWARE", "ROBOTICS"],
    }),
  },
  {
    id: "remote",
    label: "Remote Opportunities",
    description: "Remote roles compatible with Mexico, LATAM, or global work.",
    criteria: copyCriteria({
      work_models: ["REMOTE"],
      remote_scopes: ["MEXICO", "LATAM", "GLOBAL"],
      role_categories: ["SOFTWARE_ENGINEERING", "EMBEDDED_FIRMWARE"],
    }),
  },
  {
    id: "targets",
    label: "Target Companies",
    description: "All enabled priority companies and their official sources.",
    criteria: copyCriteria({ target_companies_only: true }),
  },
  {
    id: "oracle",
    label: "Oracle",
    description: "Oracle software and embedded internships.",
    criteria: copyCriteria({
      companies: ["Oracle"],
      role_categories: ["SOFTWARE_ENGINEERING", "EMBEDDED_FIRMWARE"],
    }),
  },
  {
    id: "guadalajara",
    label: "Guadalajara",
    description: "Technical internships in Guadalajara and Jalisco.",
    criteria: copyCriteria({
      states: ["Jalisco"],
      cities: ["Guadalajara"],
      role_categories: [
        "SOFTWARE_ENGINEERING",
        "EMBEDDED_FIRMWARE",
        "ROBOTICS",
        "HARDWARE_VALIDATION",
      ],
    }),
  },
];

export function cloneSearchCriteria(criteria?: Partial<SearchCriteria> | null): SearchCriteria {
  return copyCriteria(criteria ?? {});
}

export function readActiveSearchId(search: string): number | null {
  const value = new URLSearchParams(search).get("search");
  if (!value || !/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export function writeActiveSearchId(id: number | null): string {
  return id ? `/?search=${id}` : "/";
}

function roleLabel(value: SearchRoleCategory): string {
  return ROLE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export function summarizeSearchCriteria(criteria: SearchCriteria): string[] {
  criteria = cloneSearchCriteria(criteria);
  const company = criteria.target_companies_only
    ? "Target companies"
    : criteria.companies.length
      ? criteria.companies.join(" + ")
      : "Any company";
  const workModel = criteria.work_models.includes("ANY")
    ? "Any work model"
    : criteria.work_models
        .map((item) => item === "ON_SITE" ? "On-site" : item[0] + item.slice(1).toLowerCase())
        .join(", ");
  const remote = criteria.work_models.includes("REMOTE")
    ? `Remote: ${criteria.remote_scopes.map((scope) => REMOTE_SCOPE_LABELS[scope]).join(", ")}`
    : "";
  const location = [...criteria.cities, ...criteria.states, ...criteria.countries].join(", ");
  const roles = criteria.role_categories.length
    ? `Roles: ${criteria.role_categories.map(roleLabel).join(", ")}`
    : "All technical roles";
  const eligibility = criteria.only_realistically_eligible
    ? criteria.include_unknown_eligibility
      ? "Eligibility: Eligible + Unknown"
      : "Eligibility: Eligible only"
    : "Eligibility: All statuses";
  return [company, workModel, remote, location ? `Location: ${location}` : "", roles, eligibility].filter(Boolean);
}

export function searchHistoryLabel(run: SearchRun): string {
  const criteria = cloneSearchCriteria(run.criteria_json);
  const primary = criteria.companies.length
    ? criteria.companies.join(" + ")
    : criteria.work_models.includes("REMOTE")
      ? "Remote opportunities"
      : criteria.cities[0] || criteria.states[0] || "Custom search";
  const roles = criteria.role_categories.slice(0, 2).map(roleLabel).join("/");
  return roles ? `${primary} — ${roles}` : primary;
}

export type CurrentResultFilters = {
  q: string;
  minScore: string;
  ratingOrder: "highest" | "lowest";
  recommendation: string;
  remoteType: string;
  eligibility: string;
  date: string;
  targetGroup: string;
};

export const EMPTY_CURRENT_FILTERS: CurrentResultFilters = {
  q: "",
  minScore: "",
  ratingOrder: "highest",
  recommendation: "",
  remoteType: "",
  eligibility: "",
  date: "Any date",
  targetGroup: "",
};

export function readDashboardResultsState(search: string): {
  searchRunId: number | null;
  filters: CurrentResultFilters;
} {
  const params = new URLSearchParams(search);
  const ratingOrder = params.get("rating_order");
  return {
    searchRunId: readActiveSearchId(search),
    filters: {
      q: params.get("q") ?? "",
      minScore: params.get("min_score") ?? "",
      ratingOrder: ratingOrder === "lowest" ? "lowest" : "highest",
      recommendation: params.get("recommendation") ?? "",
      remoteType: params.get("remote_type") ?? "",
      eligibility: params.get("eligibility") ?? "",
      date: params.get("date") ?? "Any date",
      targetGroup: params.get("target_group") ?? "",
    },
  };
}

export function dashboardResultsPath(
  searchRunId: number | null,
  filters: CurrentResultFilters,
): string {
  const params = new URLSearchParams();
  if (searchRunId) params.set("search", String(searchRunId));
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.minScore) params.set("min_score", filters.minScore);
  params.set("rating_order", filters.ratingOrder);
  if (filters.recommendation) params.set("recommendation", filters.recommendation);
  if (filters.remoteType) params.set("remote_type", filters.remoteType);
  if (filters.eligibility) params.set("eligibility", filters.eligibility);
  if (filters.date !== "Any date") params.set("date", filters.date);
  if (filters.targetGroup) params.set("target_group", filters.targetGroup);
  return `/${params.size ? `?${params.toString()}` : ""}`;
}

export function buildResultsQuery(
  searchRunId: number | null,
  filters: CurrentResultFilters,
  pageSize = 50,
): string {
  const params = new URLSearchParams({ active: "true", page_size: String(pageSize), search_fields: "listing" });
  if (searchRunId) params.set("search_run_id", String(searchRunId));
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.minScore) params.set("min_score", filters.minScore);
  params.set("rating_order", filters.ratingOrder);
  if (filters.recommendation) params.append("recommendation", filters.recommendation);
  if (filters.remoteType) params.append("remote_type", filters.remoteType);
  if (filters.eligibility) params.append("eligibility", filters.eligibility);
  if (filters.date !== "Any date") params.set("date", filters.date);
  if (filters.targetGroup) params.set("target_group", filters.targetGroup);
  return `/api/jobs?${params.toString()}`;
}

export function buildPriorityResultsQuery(filters: CurrentResultFilters): string {
  return `${buildResultsQuery(null, filters, 10)}&priority=true&include_ineligible=true`;
}
