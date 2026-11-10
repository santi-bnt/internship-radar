"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search, SlidersHorizontal, Star, ExternalLink } from "lucide-react";
import { api, formatDate } from "@/lib/api";
import { areas, eligibility, filterOpportunities, Filters, funding, letters, Opportunity, OpportunityInput, priorities, safeWebsite, sorts, statuses, types } from "@/lib/opportunities";
import { OpportunityEditor } from "@/components/OpportunityEditor";
import DiscoveryPanel from "@/components/DiscoveryPanel";

type Result = OpportunityInput & {why_match: string};
type Discovery = {enabled: boolean; message: string; results: Result[]};
const filterOptions = [
  ["country", "Country", ["United States", "Canada", "Europe", "Other"]],
  ["research_areas", "Research area", areas], ["program_type", "Opportunity type", types],
  ["international_eligibility", "International eligibility", eligibility], ["funding", "Funding", funding],
  ["recommendation_letters", "Recommendation letters", letters], ["status", "Status", statuses], ["priority", "Priority", priorities],
] as const;

export default function OpportunitiesPage() {
  const readOnly = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
  const [items, setItems] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Filters>({});
  const [sort, setSort] = useState("Best Match");
  const [limit, setLimit] = useState(24);
  const [adding, setAdding] = useState(false);
  const [finding, setFinding] = useState(false);
  const [searchQuery, setSearchQuery] = useState("Robotics AI embedded systems IoT autonomous systems control undergraduate summer research internships international students");
  const [searchCountries, setSearchCountries] = useState("United States, Canada");
  const [searching, setSearching] = useState(false);
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [busy, setBusy] = useState<number | string | null>(null);
  useEffect(() => {let cancelled = false; (async () => {try {if (process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE !== "true") await api("/api/opportunities/bootstrap", {method: "POST"}); const data = await api<Opportunity[]>("/api/opportunities"); if (!cancelled) setItems(data);} catch (err) {if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load opportunities");} finally {if (!cancelled) setLoading(false);}})(); return () => {cancelled = true;};}, []);
  const results = useMemo(() => filterOpportunities(items, query, filters, sort), [items, query, filters, sort]);
  const replace = (item: Opportunity) => setItems(values => values.some(v => v.id === item.id) ? values.map(v => v.id === item.id ? item : v) : [item, ...values]);
  const mutate = async (o: Opportunity, action: string) => {setBusy(o.id); setError(""); try {replace(await api<Opportunity>(`/api/opportunities/${o.id}/${action}`, {method: "POST", body: action === "favorite" ? JSON.stringify({favorite: !o.favorite}) : undefined}));} catch (err) {setError(err instanceof Error ? err.message : "Update failed");} finally {setBusy(null);}};
  const create = async (value: OpportunityInput) => {const saved = await api<{created: boolean; opportunity: Opportunity}>("/api/opportunities", {method: "POST", body: JSON.stringify(value)}); replace(saved.opportunity); setAdding(false); return saved;};
  return <>
    <header className="page-header"><div><p className="eyebrow">Personal research workspace</p><h1>Opportunities</h1><p className="page-subtitle">Discover, save and follow research programs. United States first, Canada next, exceptional programs worldwide.</p></div><div className="header-actions"><button className="button" onClick={() => setFinding(!finding)}><Search size={16} />Find Opportunities</button><button className="button secondary" disabled={readOnly} onClick={() => setAdding(!adding)}>Add Opportunity</button><Link className="button secondary" href="/jobs">All Jobs</Link></div></header>
    {readOnly && <p className="notice">Read-only public demo. Saved search and filters remain available; editing and discovery require a private installation.</p>}
    {error && <p className="notice" role="alert">{error}</p>}
    {adding && <section className="card"><h2>Add an opportunity</h2><OpportunityEditor onSave={async v => {await create(v);}} onCancel={() => setAdding(false)} /></section>}
    {finding && <><section className="card opportunity-discovery"><DiscoveryPanel onSaved={replace} /></section><details className="card"><summary>Standalone research web search</summary><section className="card opportunity-discovery" aria-label="Find new opportunities"><h2>Find Opportunities</h2><p>Search new official university, institute and company pages. These results are separate from saved opportunities.</p><form onSubmit={async e => {e.preventDefault(); setSearching(true); setError(""); try {setDiscovery(await api<Discovery>("/api/opportunities/discover", {method: "POST", body: JSON.stringify({query: searchQuery, countries: searchCountries.split(",").map(s => s.trim()).filter(Boolean)})}));} catch (err) {setError(err instanceof Error ? err.message : "Discovery failed");} finally {setSearching(false);}}}><div className="form-grid"><label>Research interests and eligibility<input required minLength={3} maxLength={600} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} /></label><label>Countries (comma separated)<input value={searchCountries} onChange={e => setSearchCountries(e.target.value)} /></label></div><button className="button" disabled={searching}>{searching ? "Searching official pages…" : "Search Web"}</button></form>
      {discovery && <><p className="notice" role="status">{discovery.message}</p>{discovery.enabled && discovery.results.length === 0 && <p>No new official-domain results. Try a more specific query.</p>}<div className="opportunity-grid">{discovery.results.map(r => <article className="opportunity-card" key={r.official_url}><h3>{r.program}</h3><p>{r.organization} · {r.country}</p><p>{r.research_areas.join(", ") || "Research areas: Unknown"}</p><dl><div><dt>International eligibility</dt><dd>{r.international_eligibility}</dd></div><div><dt>Deadline</dt><dd>{r.deadline ? formatDate(r.deadline) : "Unknown"}</dd></div><div><dt>Funding</dt><dd>{r.funding.join(", ")}</dd></div></dl><p>{r.why_match}</p><p className="opportunity-snippet">{r.description}</p><div className="header-actions"><a className="button secondary" href={safeWebsite(r.official_url)} target="_blank" rel="noopener noreferrer">Official URL</a><button className="button" disabled={busy === r.official_url} onClick={async () => {setBusy(r.official_url); setError(""); try {const {why_match, ...value} = r; void why_match; await create(value); setDiscovery(d => d ? {...d, results: d.results.filter(x => x.official_url !== r.official_url)} : d);} catch (err) {setError(err instanceof Error ? err.message : "Add failed");} finally {setBusy(null);}}}>Add to Opportunities</button></div></article>)}</div></>}
    </section></details></>}
    <section className="card opportunity-controls" aria-label="Search and filters"><label className="opportunity-search"><span className="sr-only">Search saved opportunities</span><Search size={20} /><input type="search" placeholder="Search opportunities, universities, labs, countries or research areas..." value={query} onChange={e => {setQuery(e.target.value); setLimit(24);}} /></label>
      <div className="opportunity-toolbar"><details><summary><SlidersHorizontal size={16} />Filters {Object.values(filters).filter(Boolean).length ? `(${Object.values(filters).filter(Boolean).length})` : ""}</summary><div className="opportunity-filters">{filterOptions.map(([key, label, options]) => <label key={key}>{label}<select aria-label={label} value={filters[key] || ""} onChange={e => {setFilters(f => ({...f, [key]: e.target.value})); setLimit(24);}}><option value="">All</option>{options.map(o => <option key={o}>{o}</option>)}</select></label>)}</div></details><label>Sort by<select value={sort} onChange={e => setSort(e.target.value)}>{sorts.map(o => <option key={o}>{o}</option>)}</select></label><label className="opportunity-inline"><input type="checkbox" checked={!!filters.favorite} onChange={e => setFilters(f => ({...f, favorite: e.target.checked ? "yes" : ""}))} />Favorites</label><button className="button secondary" onClick={() => {setQuery(""); setFilters({}); setSort("Best Match"); setLimit(24);}}>Reset</button></div>
    </section>
    <p className="opportunity-caption" aria-live="polite">{loading ? "Loading opportunities…" : `${results.length} of ${items.length} saved opportunities`} · Fit measures interests and published program attributes, not admission or visa eligibility. Unknown information earns no bonus.</p>
    {!loading && !results.length && <section className="card"><h2>No matching opportunities</h2><p>Try clearing filters, add a program, or use Find Opportunities to discover new ones.</p></section>}
    <div className="opportunity-grid">{results.slice(0, limit).map(o => <article className="card opportunity-card" key={o.id}>
      <div className="opportunity-card-top"><span className="opportunity-badge">{o.country}</span><strong className="opportunity-score" title={o.fit_reasons.join("\n")}>{o.fit_score === null ? `${o.compatibility_level} match` : <>{o.fit_score}<small>/100 fit</small></>}</strong></div><h2><Link href={`/opportunities/${o.id}`}>{o.program}</Link></h2><p className="opportunity-org">{o.organization}{o.city !== "Unknown" ? ` · ${o.city}` : ""}</p><p className="opportunity-caption">{o.program_type}</p><div className="opportunity-tags">{o.research_areas.length ? o.research_areas.map(a => <span className="opportunity-badge area" key={a}>{a}</span>) : <span className="opportunity-badge">Research areas: Unknown</span>}</div>
      <dl><div><dt>Deadline</dt><dd>{o.deadline ? formatDate(o.deadline) : "Unknown"}{o.deadline_at && <small> {new Date(o.deadline_at).toLocaleString("en-GB", {timeZone: "UTC", hour: "2-digit", minute: "2-digit", timeZoneName: "short"})}</small>}</dd></div><div><dt>International</dt><dd><span className="opportunity-badge">{o.international_eligibility}</span></dd></div><div><dt>Funding</dt><dd>{o.funding.map(f => <span className="opportunity-badge" key={f}>{f}</span>)}</dd></div><div><dt>Recommendation</dt><dd>{o.recommendation_letters}</dd></div><div><dt>Status</dt><dd><span className="opportunity-badge status">{o.status}</span></dd></div><div><dt>Priority</dt><dd>{o.priority}</dd></div></dl>
      {o.compatibility_notes && <p className="opportunity-caption">{o.compatibility_notes}</p>}<div className="opportunity-card-actions"><Link className="button" href={`/opportunities/${o.id}`}>View Details</Link><a className="button secondary" href={safeWebsite(o.official_url)} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} />Official Website</a><button className="button secondary" disabled={busy === o.id || ["Applied", "Interview", "Accepted", "Rejected"].includes(o.status)} onClick={() => mutate(o, "applied")}>{o.status === "Applied" ? "Applied" : "Mark as Applied"}</button><button className="button secondary" aria-pressed={o.favorite} disabled={readOnly || busy === o.id} onClick={() => mutate(o, "favorite")}><Star size={14} fill={o.favorite ? "currentColor" : "none"} />{o.favorite ? "Favorited" : "Favorite"}</button></div>
    </article>)}</div>
    {results.length > limit && <button className="button secondary" onClick={() => setLimit(l => l + 24)}>Show more opportunities</button>}
  </>;
}
