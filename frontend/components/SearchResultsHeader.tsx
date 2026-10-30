"use client";

import { Search, X } from "lucide-react";
import Link from "next/link";

import { summarizeSearchCriteria } from "@/lib/job-search";
import type { SearchRun } from "@/lib/types";

export function SearchResultsHeader({
  run,
  onClear,
}: {
  run: SearchRun;
  onClear: () => void;
}) {
  return (
    <section className="search-context-card">
      <div className="search-context-heading">
        <div>
          <p className="eyebrow">Previous source scan</p>
          <h2>{summarizeSearchCriteria(run.criteria_json)[0]}</h2>
        </div>
        <div className="search-context-actions">
          <Link className="button secondary" href="/jobs"><Search size={15} /> Search saved jobs</Link>
          <button className="button ghost" type="button" onClick={onClear}><X size={15} /> Clear Search</button>
        </div>
      </div>
      <div className="search-context-chips">
        {summarizeSearchCriteria(run.criteria_json).slice(1).map((summary) => (
          <span key={summary}>{summary}</span>
        ))}
      </div>
      <div className="search-result-counts">
        <strong>{run.result_count} jobs found</strong>
        <span>{run.eligible_count} eligible or likely eligible</span>
        <span>{run.verified_count} officially verified</span>
      </div>
    </section>
  );
}
