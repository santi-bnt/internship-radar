from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalization import validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


class SmartRecruitersAdapter(JobSourceAdapter):
    PAGE_SIZE = 100

    @property
    def source_name(self) -> str:
        return "SmartRecruiters"

    @property
    def api_url(self) -> str:
        return (
            "https://api.smartrecruiters.com/v1/companies/"
            f"{self.source_identifier}/postings"
        )

    @staticmethod
    def _is_supported_location(listing: dict[str, Any]) -> bool:
        location = listing.get("location") or {}
        country = str(location.get("country") or "").lower()
        return country in {
            "ca", "can", "canada", "mx", "mex", "mexico", "us", "usa",
            "united states", "united states of america",
        } or bool(location.get("remote"))

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.api_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            listings: list[dict[str, Any]] = []
            offset = 0
            total = 1
            while offset < total:
                response = await client.get(
                    self.api_url,
                    params={"limit": self.PAGE_SIZE, "offset": offset, "q": "intern"},
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("content", [])
                if not isinstance(page, list):
                    raise ValueError("SmartRecruiters returned an unexpected payload")
                listings.extend(page)
                total = int(payload.get("totalFound") or len(page))
                offset += len(page)
                if not page:
                    break

            selected = [
                item
                for item in listings
                if is_target_internship_title(item.get("name", ""))
                and self._is_supported_location(item)
            ]
            semaphore = asyncio.Semaphore(5)

            async def fetch_detail(listing: dict[str, Any]) -> dict[str, Any] | None:
                posting_id = listing.get("id")
                if not posting_id:
                    return None
                detail_url = f"{self.api_url}/{posting_id}"
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

            details = await asyncio.gather(*(fetch_detail(item) for item in selected))
        return [detail for detail in details if detail is not None]

    @staticmethod
    def _section(raw: dict[str, Any], name: str) -> str:
        sections = ((raw.get("jobAd") or {}).get("sections") or {})
        section = sections.get(name) or {}
        title = str(section.get("title") or "").strip()
        content = str(section.get("text") or "").strip()
        if title and content:
            return f"<h3>{title}</h3>{content}"
        return content

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        location_data = raw.get("location") or {}
        location = location_data.get("fullLocation") or ", ".join(
            value
            for value in (
                location_data.get("city"),
                location_data.get("region"),
                location_data.get("country"),
            )
            if value
        )
        if location_data.get("remote"):
            location = f"Remote - {location}" if location else "Remote"
        description = "".join(
            self._section(raw, name)
            for name in ("companyDescription", "jobDescription", "additionalInformation")
        )
        requirements = self._section(raw, "qualifications")
        employment = (raw.get("typeOfEmployment") or {}).get("label") or "Internship"
        apply_url = raw.get("applyUrl") or raw.get("postingUrl") or ""
        posting_url = raw.get("postingUrl") or apply_url
        return self.build_job(
            raw,
            external_id=raw.get("uuid") or raw.get("id"),
            company=self.company,
            title=raw.get("name", ""),
            location=location,
            description=description,
            requirements=requirements,
            apply_url=apply_url,
            employment_type=employment,
            posted_at=raw.get("releasedDate"),
            official_posted_at=raw.get("releasedDate"),
            original_source_url=posting_url,
            official_apply_url=apply_url,
            official_status="open" if raw.get("active", True) else "closed",
            verification_status="verified",
            verification_method="official_smartrecruiters_api",
            status_reason="Present in the company's official SmartRecruiters job board.",
            last_verified_at=datetime.now(timezone.utc),
        )
