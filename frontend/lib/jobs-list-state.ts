export type JobsListFilters = {
  q: string;
  countries: string[];
  arrangements: string[];
  employment: string[];
  areas: string[];
  statuses: string[];
  importance: string[];
  verification: string[];
  eligibility: string[];
  remoteScopes: string[];
  sponsorship: string[];
  date: string;
  minScore: string;
};

export type JobsListState = {
  lifecycleStatus: "active" | "saved" | "applied" | "expired" | "not_interested" | "archived";
  filters: JobsListFilters;
  targetGroup: string;
  companyFilter: string;
  showIneligible: boolean;
  searchRunId: number | null;
  ratingOrder: "highest" | "lowest";
  page: number;
};

// Start unfiltered so jobs with incomplete or multi-location country metadata
// are not silently hidden from the main opportunity list.
const DEFAULT_COUNTRIES: string[] = [];
const LIFECYCLE_STATUSES = new Set<JobsListState["lifecycleStatus"]>([
  "active", "saved", "applied", "expired", "not_interested", "archived",
]);

export const INITIAL_JOBS_LIST_FILTERS: JobsListFilters = {
  q: "",
  countries: [...DEFAULT_COUNTRIES],
  arrangements: [],
  employment: [],
  areas: [],
  statuses: [],
  importance: [],
  verification: [],
  eligibility: [],
  remoteScopes: [],
  sponsorship: [],
  date: "Any date",
  minScore: "",
};

export const INITIAL_JOBS_LIST_STATE: JobsListState = {
  lifecycleStatus: "active",
  filters: INITIAL_JOBS_LIST_FILTERS,
  targetGroup: "",
  companyFilter: "",
  showIneligible: false,
  searchRunId: null,
  ratingOrder: "highest",
  page: 1,
};

function activeSearchId(params: URLSearchParams): number | null {
  const value = params.get("search");
  if (!value || !/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function positivePage(value: string | null): number {
  const page = Number(value);
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

function values(params: URLSearchParams, name: string): string[] {
  return params.getAll(name).filter(Boolean);
}

/** Read a jobs-list URL into a complete, shareable list state. */
export function readJobsListState(search: string): JobsListState {
  const params = new URLSearchParams(search);
  const lifecycle = params.get("lifecycle");
  const countries = values(params, "country");
  const ratingOrder = params.get("rating_order");
  return {
    lifecycleStatus: lifecycle && LIFECYCLE_STATUSES.has(lifecycle as JobsListState["lifecycleStatus"])
      ? lifecycle as JobsListState["lifecycleStatus"]
      : "active",
    filters: {
      q: params.get("q") ?? "",
      countries: params.get("country_any") === "true" ? [] : countries.length ? countries : [...DEFAULT_COUNTRIES],
      arrangements: values(params, "remote_type"),
      employment: values(params, "employment"),
      areas: values(params, "area"),
      statuses: values(params, "recommendation"),
      importance: values(params, "company_importance"),
      verification: values(params, "verification"),
      eligibility: values(params, "eligibility"),
      remoteScopes: values(params, "remote_scope"),
      sponsorship: values(params, "sponsorship"),
      date: params.get("date") ?? "Any date",
      minScore: params.get("min_score") ?? "",
    },
    targetGroup: params.get("target_group") ?? "",
    companyFilter: params.get("company") ?? "",
    showIneligible: params.get("include_ineligible") === "true",
    searchRunId: activeSearchId(params),
    ratingOrder: ratingOrder === "lowest" ? "lowest" : "highest",
    page: positivePage(params.get("page")),
  };
}

function appendAll(params: URLSearchParams, name: string, selected: string[]) {
  selected.forEach((value) => params.append(name, value));
}

/** Serialize every user-visible jobs-list filter so details can safely return here. */
export function jobsListPath(state: JobsListState): string {
  const params = new URLSearchParams();
  const { filters } = state;
  if (state.lifecycleStatus !== "active") params.set("lifecycle", state.lifecycleStatus);
  if (state.searchRunId) params.set("search", String(state.searchRunId));
  if (state.targetGroup) params.set("target_group", state.targetGroup);
  if (state.companyFilter) params.set("company", state.companyFilter);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.countries.length === 0) params.set("country_any", "true");
  else appendAll(params, "country", filters.countries);
  appendAll(params, "remote_type", filters.arrangements);
  appendAll(params, "employment", filters.employment);
  appendAll(params, "area", filters.areas);
  appendAll(params, "recommendation", filters.statuses);
  appendAll(params, "company_importance", filters.importance);
  appendAll(params, "verification", filters.verification);
  appendAll(params, "eligibility", filters.eligibility);
  appendAll(params, "remote_scope", filters.remoteScopes);
  appendAll(params, "sponsorship", filters.sponsorship);
  if (state.showIneligible) params.set("include_ineligible", "true");
  if (filters.date !== "Any date") params.set("date", filters.date);
  if (filters.minScore) params.set("min_score", filters.minScore);
  params.set("rating_order", state.ratingOrder);
  if (state.page > 1) params.set("page", String(state.page));
  return `/jobs${params.size ? `?${params.toString()}` : ""}`;
}
