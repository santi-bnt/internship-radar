"""Web discovery boundary. No fabricated results and no client-side credentials."""
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from app.services.source_rate_limit import request_hooks
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.opportunities import OpportunityInput
from app.services.normalization import validate_public_url


class DiscoveryQuery(BaseModel):
    query: str = Field(default="robotics AI embedded IoT autonomous systems control undergraduate summer research internships international students", min_length=3, max_length=600)
    countries: list[str] = Field(default_factory=lambda: ["United States", "Canada"], max_length=5)


class SearchProvider(Protocol):
    async def search(self, query: DiscoveryQuery) -> list[OpportunityInput]: ...


class TavilyProvider:
    async def raw_results(self, query: DiscoveryQuery) -> list[dict]:
        # Only the backend talks to the fixed provider URL; result URLs are not fetched.
        async with httpx.AsyncClient(event_hooks=request_hooks(), timeout=20) as client:
            response = await client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {settings.opportunity_search_api_key}"}, json={"query": f"{query.query} {' '.join(query.countries)} official university institute company research program", "search_depth": "basic", "max_results": 20, "include_answer": False, "include_raw_content": False})
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("Invalid search provider response")
        return payload["results"]

    async def search(self, query: DiscoveryQuery) -> list[OpportunityInput]:
        results = []
        for item in await self.raw_results(query):
            if not isinstance(item, dict):
                continue
            url = item.get("url", "")
            if not isinstance(url, str):
                continue
            try:
                validate_public_url(url)
            except ValueError:
                continue
            host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
            known = ("allenai.org", "mcgill.ca", "utoronto.ca", "ubc.ca", "uwaterloo.ca", "ualberta.ca", "epfl.ch", "mpg.de", "nrc-cnrc.gc.ca")
            if not (host.endswith(".edu") or any(host == domain or host.endswith("." + domain) for domain in known)):
                continue
            # Snippets are evidence to review, not structured eligibility facts.
            results.append(OpportunityInput(program=str(item.get("title") or host)[:300], organization="Unknown", official_url=url, description=str(item.get("content") or "")[:20000], notes="Official-domain search result. Review the source before assigning program details or eligibility. Structured fields remain Unknown until confirmed."))
        return results


def provider() -> SearchProvider | None:
    if settings.opportunity_search_provider == "tavily" and settings.opportunity_search_api_key:
        return TavilyProvider()
    return None
