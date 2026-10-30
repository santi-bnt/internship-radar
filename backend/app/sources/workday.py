from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

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

    async def fetch_exact_public_ids(
        self,
        public_ids: set[str],
        *,
        require_all: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch only known public requisitions from the official CXS API."""
        requested = {str(item).strip() for item in public_ids if str(item).strip()}
        jobs_url = f"{self.api_url}/jobs"
        validate_public_url(jobs_url)
        found: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            for public_id in sorted(requested):
                response = await client.post(
                    jobs_url,
                    json={
                        "appliedFacets": {}, "limit": self.PAGE_SIZE,
                        "offset": 0, "searchText": public_id,
                    },
                )
                response.raise_for_status()
                listings = response.json().get("jobPostings", [])
                if not isinstance(listings, list):
                    raise ValueError("Workday returned an unexpected payload")
                for listing in listings:
                    path = listing.get("externalPath")
                    if not path:
                        continue
                    detail_url = f"{self.api_url}{path}"
                    validate_public_url(detail_url)
                    detail = await client.get(detail_url)
                    detail.raise_for_status()
                    payload = detail.json()
                    record = payload.get("jobPostingInfo", payload)
                    record_id = str(record.get("jobReqId") or record.get("jobRequisitionId") or "")
                    if record_id == public_id:
                        record["_listing"] = listing
                        found[public_id] = record
                        break
        missing = sorted(requested - set(found))
        if missing and require_all:
            raise RuntimeError(
                "Workday did not verify the requested public posting IDs: "
                + ", ".join(missing)
            )
        return [found[public_id] for public_id in sorted(found)]

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        jobs_url = f"{self.api_url}/jobs"
        validate_public_url(jobs_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            listings_by_path: dict[str, dict[str, Any]] = {}
            for query in self.search_terms()[:8]:
                offset = 0
                total = 1
                while offset < total and offset < 100:
                    response = await client.post(
                        jobs_url,
                        json={
                            "appliedFacets": {},
                            "limit": self.PAGE_SIZE,
                            "offset": offset,
                            "searchText": query,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    page = payload.get("jobPostings", [])
                    if not isinstance(page, list):
                        raise ValueError("Workday returned an unexpected payload")
                    for item in page:
                        listings_by_path[str(item.get("externalPath") or item.get("title"))] = item
                    total = int(payload.get("total") or len(page))
                    offset += len(page)
                    if not page:
                        break
            listings = [
                item for item in listings_by_path.values()
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
        description = _workday_content(raw.get("jobDescription") or raw.get("description"))
        plain_description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        sections = _workday_sections(plain_description)
        requirements = _workday_content(
            raw.get("jobRequirements")
            or raw.get("requirements")
            or raw.get("qualifications")
        )
        if not requirements:
            requirements = "\n".join(
                sections[key]
                for key in (
                    "job family definition", "education & experience",
                    "education and experience", "knowledge & skills",
                    "knowledge and skills",
                )
                if sections.get(key)
            ) or plain_description
        preferred = _workday_content(
            raw.get("preferredQualifications")
            or raw.get("preferred_qualifications")
            or sections.get("preferred qualifications", "")
        )
        # Workday's API often keeps the entire formatted posting in one HTML
        # jobDescription field. Derive the work model from that official text
        # and preserve the structured sections for the requirements panel.
        employment_type = raw.get("timeType", "Internship")
        official_status = "closed" if raw.get("canApply") is False or raw.get("posted") is False else "open"
        return self.build_job(
            raw,
            external_id=raw.get("jobReqId") or raw.get("jobRequisitionId"),
            title=raw.get("title") or listing.get("title", ""),
            location=location,
            description=description,
            requirements=requirements,
            preferred_qualifications=preferred,
            apply_url=public_url,
            employment_type=employment_type,
            posted_at=raw.get("startDate") or listing.get("postedOn"),
            official_posted_at=raw.get("startDate") or listing.get("postedOn"),
            original_source_url=public_url,
            official_apply_url=public_url,
            official_status=official_status,
            verification_status="verified",
            verification_method="official_workday_api",
            status_reason=(
                "Present in the company's official Workday job board."
                if official_status == "open"
                else "The official Workday posting is no longer accepting applications."
            ),
            last_verified_at=datetime.now(timezone.utc),
        )


_WORKDAY_SECTION_PATTERN = re.compile(
    r"(?i)(job family definition|responsibilities|education\s*&\s*experience|"
    r"education\s+and\s+experience|knowledge\s*&\s*skills|"
    r"knowledge\s+and\s+skills|preferred qualifications)\s*:"
)


def _workday_content(value: Any) -> str:
    """Normalize the string/object/list shapes used in Workday posting JSON."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("html", "text", "value", "content", "descriptor"):
            if value.get(key):
                return _workday_content(value[key])
        return ""
    if isinstance(value, list):
        return "\n".join(filter(None, (_workday_content(item) for item in value)))
    return ""


def _workday_sections(description: str) -> dict[str, str]:
    matches = list(_WORKDAY_SECTION_PATTERN.finditer(description))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = re.sub(r"\s+", " ", match.group(1).casefold())
        end = matches[index + 1].start() if index + 1 < len(matches) else len(description)
        value = description[match.end():end].strip(" \t\r\n:•")
        if value:
            sections[key] = value
    return sections
