from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


RULES = {
    "google": re.compile(r"(?:/about/careers/applications/)?jobs/results/\d+[^?#]*"),
    "meta": re.compile(r"/jobs/\d+"),
    "arm": re.compile(r"/job/[^?#]+"),
    "synopsys": re.compile(r"/job/[^?#]+"),
    "amd": re.compile(r"/careers(?:-home)?/job/[^?#]+"),
    "qualcomm": re.compile(r"/careers/job/[^?#]+"),
}


class OfficialCareersAdapter(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return f"{self.company} Careers"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.source_url)
        pattern = RULES[self.source_identifier]
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            discovered: dict[str, dict[str, str]] = {}
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                if not pattern.search(href):
                    continue
                title = clean_text(anchor.get_text(" ", strip=True))
                if not title and self.source_identifier == "google":
                    slug = href.split("?", 1)[0].rsplit("/", 1)[-1]
                    title = re.sub(r"^\d+-", "", slug).replace("-", " ").title()
                if not is_target_internship_title(title):
                    continue
                base_url = (
                    "https://www.google.com/about/careers/applications/"
                    if self.source_identifier == "google"
                    else str(response.url)
                )
                url = urljoin(base_url, href)
                discovered[url] = {
                    "title": title,
                    "location_hint": clean_text(anchor.parent.get_text(" ", strip=True)),
                }
            if not discovered:
                raise RuntimeError(
                    f"{self.company} official careers page exposed no internship links; "
                    "the source may require JavaScript or be temporarily unavailable."
                )
            semaphore = asyncio.Semaphore(4)

            async def fetch_detail(url: str, item: dict[str, str]) -> dict[str, Any] | None:
                try:
                    async with semaphore:
                        detail = await client.get(url)
                        detail.raise_for_status()
                    detail_soup = BeautifulSoup(detail.text, "html.parser")
                    text = clean_text(detail_soup.get_text(" ", strip=True))
                    return {**item, "url": str(detail.url), "description": text}
                except httpx.HTTPError:
                    return None

            details = await asyncio.gather(
                *(fetch_detail(url, item) for url, item in discovered.items())
            )
        return [item for item in details if item]

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        job_id = next(iter(re.findall(r"\d{6,}", raw["url"])), None)
        return self.build_job(
            raw,
            external_id=job_id,
            title=raw["title"],
            location=raw.get("location_hint", ""),
            description=raw.get("description", ""),
            requirements=raw.get("description", ""),
            apply_url=raw["url"],
            original_source_url=raw["url"],
            official_apply_url=raw["url"],
            official_status="open",
            verification_status="verified",
            verification_method="official_careers_page",
            status_reason="Title and application page found on the official company careers site.",
            last_verified_at=datetime.now(timezone.utc),
        )
