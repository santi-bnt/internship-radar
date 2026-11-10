"""Optional web/X-ray discovery reusing the server-side provider boundary."""
from urllib.parse import urlsplit
from app.core.config import settings
from app.services.opportunity_discovery import DiscoveryQuery, TavilyProvider
from app.services.discovery_records import detect_ats
from app.services.official_source_resolver import OfficialSourceResolver
from app.services.safe_job_fetch import validate_job_url
from app.sources.external import ExternalDiscoverySource


class WebSearchSource(ExternalDiscoverySource):
    source_name = "Web Search"

    def queries(self):
        base = self.search_terms()[0]
        level = "undergraduate" if self.search_criteria.get("student_level") == "BACHELORS" else "student"
        types = " ".join((self.search_criteria.get("opportunity_types") or ["internship"])[:2])
        return [f'(site:boards.greenhouse.io OR site:job-boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com) {base}', f'{base} {level} {types} international students']

    async def fetch_jobs(self):
        if settings.opportunity_search_provider != "tavily" or not settings.opportunity_search_api_key:
            raise ValueError("Web discovery provider is not configured")
        results = {}
        for query in self.queries():
            for item in await TavilyProvider().raw_results(DiscoveryQuery(query=query, countries=(self.search_criteria.get("countries") or [])[:5])):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                try:
                    validate_job_url(url)
                except ValueError:
                    continue
                host = (urlsplit(url).hostname or "").lower()
                official = detect_ats(url) != "unknown" or host.endswith((".edu", ".ac.uk")) or host in {"eee.epfl.ch", "allenai.org", "www.mcgill.ca"} or host in self.search_criteria.get("_official_domains", [])
                if not official:
                    continue
                results[url] = {"sourceName": self.source_name, "sourceUrl": url, "canonicalUrl": url,
                    "title": str(item.get("title") or host)[:300], "company": "Unknown",
                    "description": str(item.get("content") or "")[:20000],
                    "metadata": {"evidenceKind": "search_snippet", "query": query}}
                if len(results) >= 8:
                    return list(results.values())
        return list(results.values())

    async def collect(self):
        resolver = OfficialSourceResolver(self.search_criteria.get("_official_domains", []))
        return [await resolver.resolve(self.normalize_job(raw)) for raw in await self.fetch_jobs()]


class ResearchOpportunitySource(WebSearchSource):
    source_name = "University Research Discovery"

    def queries(self):
        base = self.search_terms()[0]
        level = "undergraduate" if self.search_criteria.get("student_level") == "BACHELORS" else "student"
        countries = " ".join(self.search_criteria.get("countries") or [])
        return [f'{base} summer {level} research university international students', f'{base} visiting research {countries}']
