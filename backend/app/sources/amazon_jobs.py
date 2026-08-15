from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalization import validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


class AmazonJobsAdapter(JobSourceAdapter):
    API_URL = "https://www.amazon.jobs/en/search.json"

    @property
    def source_name(self) -> str:
        return "Amazon Jobs"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.API_URL)
        params = {"base_query": "intern", "result_limit": 100, "sort": "recent"}
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.API_URL, params=params)
            response.raise_for_status()
        payload = response.json()
        jobs = payload.get("jobs", [])
        if not isinstance(jobs, list):
            raise ValueError("Amazon Jobs returned an unexpected payload")
        return [job for job in jobs if is_target_internship_title(job.get("title", ""))]

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        path = raw.get("job_path") or raw.get("url") or ""
        url = path if str(path).startswith("http") else f"https://www.amazon.jobs{path}"
        description = " ".join(
            str(raw.get(key) or "")
            for key in ("description", "basic_qualifications", "preferred_qualifications")
        )
        country_code = str(raw.get("location", "")).split(",", 1)[0].strip().upper()
        country = {
            "US": "United States",
            "USA": "United States",
            "CA": "Canada",
            "CAN": "Canada",
            "MX": "Mexico",
            "MEX": "Mexico",
        }.get(country_code, "")
        return self.build_job(
            raw,
            external_id=raw.get("id") or raw.get("job_id"),
            title=raw.get("title", ""),
            location=raw.get("location", ""),
            country=country,
            description=description,
            requirements=raw.get("basic_qualifications", ""),
            preferred_qualifications=raw.get("preferred_qualifications", ""),
            apply_url=url,
            posted_at=raw.get("posted_date"),
            official_posted_at=raw.get("posted_date"),
            original_source_url=url,
            official_apply_url=url,
            official_status="open",
            verification_status="verified",
            verification_method="official_amazon_jobs_api",
            status_reason="Present in the official Amazon Jobs search API.",
            last_verified_at=datetime.now(timezone.utc),
        )
