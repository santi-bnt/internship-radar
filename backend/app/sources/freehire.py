"""Optional, bounded personal/licensed API discovery, not a dataset mirror."""
import asyncio
from urllib.parse import quote
import httpx
from app.services.source_rate_limit import request_hooks
from app.core.config import settings
from app.services.official_source_resolver import OfficialSourceResolver
from app.sources.external import ExternalDiscoverySource


class FreehireSource(ExternalDiscoverySource):
    source_name = "Freehire"
    API_URL = "https://freehire.me/api/v1/jobs/search"

    async def fetch_jobs(self):
        if not settings.freehire_enabled or settings.freehire_use_mode not in {"personal", "licensed"}:
            raise ValueError("Freehire is disabled; configure personal or licensed API use on the backend")
        found = {}
        countries = {"United States": "US", "Canada": "CA", "Mexico": "MX", "Germany": "DE", "Switzerland": "CH"}
        async with httpx.AsyncClient(event_hooks=request_hooks(), timeout=settings.request_timeout_seconds, follow_redirects=False) as client:
            for index, term in enumerate(self.search_terms()[:2]):
                if index:
                    await asyncio.sleep(1)  # Far below the public no-key rate ceiling.
                params = {"q": term, "limit": 10, "offset": 0, "sort": "posted_at", "order": "desc", "employment_type": "internship"}
                selected = self.search_criteria.get("countries") or []
                if selected:
                    params["countries"] = ",".join(countries.get(c, c) for c in selected)
                response = await client.get(self.API_URL, params=params)
                response.raise_for_status()  # 429 is deferred by the shared scheduler.
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("Freehire response has no data list")
                for item in payload["data"]:
                    if isinstance(item, dict) and not item.get("closed_at") and item.get("url"):
                        found[str(item.get("external_id") or item.get("public_slug") or item["url"])] = item
        return list(found.values())[:20]

    def normalize_job(self, raw):
        slug = str(raw.get("public_slug") or "")
        original = str(raw.get("url") or "")
        source_url = f"https://freehire.me/api/v1/jobs/{quote(slug, safe='')}" if slug else original
        return super().normalize_job({
            "sourceName": "Freehire", "sourceUrl": source_url,
            "externalId": str(raw.get("external_id") or slug), "canonicalUrl": original,
            "title": str(raw.get("title") or ""), "company": str(raw.get("company") or "Unknown"),
            "location": str(raw.get("location") or "Unknown"), "description": str(raw.get("description") or "")[:100000],
            "postedAt": raw.get("posted_at"),
            "metadata": {"originalUrl": original, "sourceExternalId": str(raw.get("external_id") or slug), "attribution": "Discovered via Freehire; job content belongs to the original publisher.", "upstreamSource": raw.get("source"), "freehireUpdatedAt": raw.get("updated_at")},
        })

    async def collect(self):
        resolver = OfficialSourceResolver(self.search_criteria.get("_official_domains", []))
        return [await resolver.resolve(self.normalize_job(raw)) for raw in await self.fetch_jobs()]
