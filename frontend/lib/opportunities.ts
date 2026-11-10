export const areas = ["Robotics", "Artificial Intelligence", "Machine Learning", "Embedded Systems", "IoT", "Autonomous Systems", "Control", "Computer Vision", "Computer Systems", "Electrical Engineering", "FPGA"];
export const types = ["Unknown", "Research Internship", "Summer Research", "Industry Internship", "Visiting Research", "Fellowship", "Full Time"];
export const eligibility = ["International students accepted", "Unknown", "Not eligible"];
export const funding = ["Fully funded", "Paid", "Stipend", "Housing support", "Travel support", "Unfunded", "Unknown"];
export const letters = ["Required", "Optional", "Not required", "Unknown"];
export const statuses = ["Unknown", "Not Open Yet", "Open", "Recruiter Contacted", "Applying", "Applied", "Interview", "Accepted", "Rejected", "Closed"];
export const priorities = ["Very High", "High", "Medium", "Low"];
export const sorts = ["Best Match", "Deadline", "Priority", "Recently Added", "Recently Updated", "Country", "University"];
export type Opportunity = {
  id: number; program: string; organization: string; country: string; city: string;
  official_url: string; application_url: string; description: string; research_areas: string[];
  lab: string; professor: string; notes: string; program_type: string;
  international_eligibility: string; eligibility_notes: string; funding: string[]; funding_notes: string;
  recommendation_letters: string; recommendation_notes: string; status: string; priority: string; favorite: boolean;
  undergraduate_eligible: string; citizenship_restriction: string; host_required: string;
  required_documents: string[]; deadline: string | null; deadline_at: string | null; deadline_notes: string;
  supporting_urls: string[]; fit_score: number | null; fit_reasons: string[]; created_at: string; updated_at: string;
  employment_type: string; compatibility_level: string; compatibility_notes: string;
  provenance?: {kind: string; verified_on?: string; urls?: string[]; note?: string};
};
export type OpportunityInput = Omit<Opportunity, "id" | "fit_score" | "fit_reasons" | "created_at" | "updated_at" | "provenance">;
export function inputOf(value: Opportunity): OpportunityInput {
  const { id, fit_score, fit_reasons, created_at, updated_at, provenance, ...input } = value;
  void id; void fit_score; void fit_reasons; void created_at; void updated_at; void provenance;
  return input;
}
export const emptyOpportunity: OpportunityInput = {
  program: "", organization: "", country: "Unknown", city: "Unknown", official_url: "", application_url: "", description: "",
  research_areas: [], lab: "", professor: "", notes: "", program_type: "Unknown", international_eligibility: "Unknown",
  eligibility_notes: "", funding: ["Unknown"], funding_notes: "", recommendation_letters: "Unknown", recommendation_notes: "",
  status: "Unknown", priority: "Medium", favorite: false, undergraduate_eligible: "Unknown", citizenship_restriction: "Unknown", host_required: "Unknown",
  required_documents: [], deadline: null, deadline_at: null, deadline_notes: "", supporting_urls: [],
  employment_type: "Unknown", compatibility_level: "Unknown", compatibility_notes: "",
};
export type Filters = Record<string, string>;
const normalize = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const europe = new Set(["switzerland", "germany", "france", "united kingdom", "uk", "netherlands", "belgium", "spain", "italy", "sweden", "norway", "denmark", "finland", "austria", "ireland", "portugal", "poland", "czechia", "czech republic", "greece", "hungary", "romania", "iceland", "luxembourg", "estonia", "latvia", "lithuania", "slovenia", "slovakia", "croatia", "bulgaria", "cyprus", "malta", "serbia", "ukraine", "turkey"]);
export function countryGroup(country: string): string {
  const key = normalize(country);
  if (["united states", "united states of america", "usa", "us"].includes(key)) return "United States";
  if (key === "canada") return "Canada";
  return europe.has(key) ? "Europe" : "Other";
}
export function filterOpportunities(values: Opportunity[], query: string, filters: Filters, sort: string): Opportunity[] {
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  const filtered = values.filter(o => {
    const haystack = normalize([o.program, o.organization, o.country, o.city, ...o.research_areas, o.lab, o.professor, o.description, o.international_eligibility, o.eligibility_notes, o.notes].join(" "));
    return terms.every(t => haystack.includes(t)) && Object.entries(filters).every(([key, value]) => {
      if (!value) return true;
      if (key === "country") return countryGroup(o.country) === value;
      if (key === "favorite") return o.favorite;
      const actual = o[key as keyof Opportunity];
      return Array.isArray(actual) ? actual.includes(value as never) : actual === value;
    });
  });
  return filtered.sort((a,b) => {
    let delta = 0;
    if (sort === "Deadline") delta = (Date.parse(a.deadline_at || a.deadline || "") || Infinity) - (Date.parse(b.deadline_at || b.deadline || "") || Infinity);
    else if (sort === "Priority") delta = priorities.indexOf(a.priority) - priorities.indexOf(b.priority);
    else if (sort === "Recently Added") delta = Date.parse(b.created_at) - Date.parse(a.created_at);
    else if (sort === "Recently Updated") delta = Date.parse(b.updated_at) - Date.parse(a.updated_at);
    else if (sort === "Country") delta = a.country.localeCompare(b.country);
    else if (sort === "University") delta = a.organization.localeCompare(b.organization);
    else delta = (b.fit_score ?? -1) - (a.fit_score ?? -1);
    return (Number.isNaN(delta) ? 0 : delta) || a.program.localeCompare(b.program);
  });
}
export function safeWebsite(url: string): string | undefined {
  try { const u = new URL(url); return ["https:", "http:"].includes(u.protocol) ? u.href : undefined; } catch { return undefined; }
}
