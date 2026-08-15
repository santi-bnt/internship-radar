from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.normalization import validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


class WorkdayAdapter(JobSourceAdapter):
    PAGE_SIZE = 20

    @property
    def source_name(self) -> str:
        return "Workday"

    def _parts(self) -> tuple[str, str, str]:
        tenant, site = self.source_identifier.split("|", 1)
        parsed = urlparse(self.source_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin, tenant, site

    @property
    def api_url(self) -> str:
        origin, tenant, site = self._parts()
        return f"{origin}/wday/cxs/{tenant}/{site}"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        jobs_url = f"{self.api_url}/jobs"
        validate_public_url(jobs_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            listings: list[dict[str, Any]] = []
            offset = 0
            total = 1
            while offset < total:
                response = await client.post(
                    jobs_url,
                    json={
                        "appliedFacets": {},
                        "limit": self.PAGE_SIZE,
                        "offset": offset,
                        "searchText": "intern",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("jobPostings", [])
                if not isinstance(page, list):
                    raise ValueError("Workday returned an unexpected payload")
                listings.extend(page)
                total = int(payload.get("total") or len(page))
                offset += len(page)
                if not page:
                    break
            listings = [
                item for item in listings
                if is_target_internship_title(item.get("title", ""))
            ]
            semaphore = asyncio.Semaphore(5)

            async def detail(listing: dict[str, Any]) -> dict[str, Any] | None:
                path = listing.get("externalPath")
                if not path:
                    return None
                detail_url = f"{self.api_url}{path}"
                validate_public_url(detail_url)
                try:
                    async with semaphore:
                        result = await client.get(detail_url)
                        result.raise_for_status()
                    data = result.json().get("jobPostingInfo", result.json())
                    data["_listing"] = listing
                    return data
                except (httpx.HTTPError, ValueError):
                    return None

            details = await asyncio.gather(*(detail(item) for item in listings))
        return [item for item in details if item]

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        listing = raw.get("_listing") or {}
        path = listing.get("externalPath") or raw.get("externalPath") or ""
        public_url = raw.get("externalUrl") or f"{self.source_url}{path}"
        if public_url.startswith("/"):
            public_url = f"{self.source_url.rstrip('/')}{public_url}"
        location = raw.get("location") or listing.get("locationsText") or ""
        description = raw.get("jobDescription") or ""
        return self.build_job(
            raw,
            external_id=raw.get("jobReqId") or raw.get("jobRequisitionId"),
            title=raw.get("title") or listing.get("title", ""),
            location=location,
            description=description,
            requirements=description,
            apply_url=public_url,
            employment_type=raw.get("timeType", "Internship"),
            posted_at=raw.get("startDate") or listing.get("postedOn"),
            official_posted_at=raw.get("startDate") or listing.get("postedOn"),
            original_source_url=public_url,
            official_apply_url=public_url,
            official_status="open",
            verification_status="verified",
            verification_method="official_workday_api",
            status_reason="Present in the company's official Workday job board.",
            last_verified_at=datetime.now(timezone.utc),
        )
