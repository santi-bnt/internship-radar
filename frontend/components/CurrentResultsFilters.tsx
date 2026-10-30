"use client";

import { Filter, RotateCcw } from "lucide-react";

import { EMPTY_CURRENT_FILTERS } from "@/lib/job-search";
import type { CurrentResultFilters } from "@/lib/job-search";

export function CurrentResultsFilters({
  value,
  onChange,
}: {
  value: CurrentResultFilters;
  onChange: (filters: CurrentResultFilters) => void;
}) {
  const active = Object.entries(value).some(([key, item]) =>
    key === "date"
      ? item !== "Any date"
      : key === "ratingOrder"
        ? item !== "highest"
        : Boolean(item),
  );
  return (
    <section className="current-result-filters" aria-label="Filter current results">
      <div className="current-filter-title">
        <Filter size={16} />
        <div><strong>Filters</strong><span>Filter saved jobs here. Source scans are in Sources.</span></div>
      </div>
      <div className="current-filter-controls">
        <input
          aria-label="Filter company, role, or location"
          placeholder="Company, role, location"
          value={value.q}
          onChange={(event) => onChange({ ...value, q: event.target.value })}
        />
        <select aria-label="Minimum score" value={value.minScore} onChange={(event) => onChange({ ...value, minScore: event.target.value })}>
          <option value="">Any score</option><option value="70">70+</option><option value="80">80+</option><option value="90">90+</option>
        </select>
        <select aria-label="Recommendation filter" value={value.recommendation} onChange={(event) => onChange({ ...value, recommendation: event.target.value })}>
          <option value="">Any action</option><option value="Apply Now">Apply Now (including manual)</option><option value="Apply Today">Apply Today</option>
        </select>
        <select aria-label="Sort jobs by rating" value={value.ratingOrder} onChange={(event) => onChange({ ...value, ratingOrder: event.target.value as CurrentResultFilters["ratingOrder"] })}>
          <option value="highest">Highest rating first</option><option value="lowest">Lowest rating first</option>
        </select>
        <select aria-label="Work model filter" value={value.remoteType} onChange={(event) => onChange({ ...value, remoteType: event.target.value })}>
          <option value="">Any work model</option><option value="Remote">Remote</option><option value="Hybrid">Hybrid</option><option value="On-site">On-site</option>
        </select>
        <select aria-label="Eligibility filter" value={value.eligibility} onChange={(event) => onChange({ ...value, eligibility: event.target.value })}>
          <option value="">Any eligibility</option><option value="ELIGIBLE">Eligible</option><option value="LIKELY_ELIGIBLE">Likely eligible</option><option value="UNKNOWN">Unknown</option>
        </select>
        <select aria-label="Posted date filter" value={value.date} onChange={(event) => onChange({ ...value, date: event.target.value })}>
          <option>Any date</option><option>Last 24 hours</option><option>Last 3 days</option><option>Last 7 days</option><option>Last 14 days</option><option>Last 30 days</option>
        </select>
        {active && <button className="button ghost" type="button" onClick={() => onChange({ ...EMPTY_CURRENT_FILTERS })}><RotateCcw size={14} /> Reset</button>}
      </div>
    </section>
  );
}
