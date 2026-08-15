from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalization import validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob


class GreenhouseAdapter(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Greenhouse"

    @property
    def api_url(self) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{self.source_identifier}/jobs"

    @staticmethod
    def is_internship_title(title: str) -> bool:
        normalized = title.lower().replace("_", " ")
        return any(
            term in normalized
            for term in ("intern", "internship", "co-op", "co op", "student")
        )

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.api_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.api_url)
            response.raise_for_status()
            listings = [
                job
                for job in response.json().get("jobs", [])
                if self.is_internship_title(job.get("title", ""))
            ]
            semaphore = asyncio.Semaphore(5)

            async def fetch_detail(listing: dict[str, Any]) -> dict[str, Any] | None:
                detail_url = f"{self.api_url}/{listing['id']}"
                validate_public_url(detail_url)
                try:
                    async with semaphore:
                        detail_response = await client.get(detail_url)
                        detail_response.raise_for_status()
                    detail = detail_response.json()
                    for key, value in listing.items():
                        detail.setdefault(key, value)
                    return detail
                except (httpx.HTTPError, ValueError):
                    return None

            details = await asyncio.gather(
                *(fetch_detail(listing) for listing in listings)
            )
        return [detail for detail in details if detail is not None]

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        location = (raw.get("location") or {}).get("name", "")
        return self.build_job(
            raw,
            external_id=raw.get("id"),
            title=raw.get("title", ""),
            location=location,
            description=raw.get("content", ""),
            apply_url=raw.get("absolute_url", ""),
            posted_at=raw.get("updated_at"),
            official_posted_at=raw.get("updated_at"),
            original_source_url=raw.get("absolute_url", ""),
            official_apply_url=raw.get("absolute_url", ""),
            official_status="open",
            verification_status="verified",
            verification_method="official_greenhouse_api",
            status_reason="Present on the official Greenhouse board with an active application URL.",
            last_verified_at=datetime.now(timezone.utc),
        )
