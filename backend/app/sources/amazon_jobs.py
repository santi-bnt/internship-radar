from __future__ import annotations

from datetime import datetime, timezone
import re
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
        jobs_by_id: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            for query in self.search_terms()[:8]:
                response = await client.get(
                    self.API_URL,
                    params={"base_query": query, "result_limit": 100, "sort": "recent"},
                )
                response.raise_for_status()
                jobs = response.json().get("jobs", [])
                if not isinstance(jobs, list):
                    raise ValueError("Amazon Jobs returned an unexpected payload")
                for job in jobs:
                    if is_target_internship_title(job.get("title", "")):
                        key = str(job.get("id") or job.get("job_id") or job.get("job_path"))
                        jobs_by_id[key] = job
        return list(jobs_by_id.values())

    async def fetch_exact_public_ids(self, public_ids: set[str]) -> list[dict[str, Any]]:
        """Retrieve user-requested public postings without widening discovery."""
        requested = {str(item) for item in public_ids if str(item).isdigit()}
        found: dict[str, dict[str, Any]] = {}
        validate_public_url(self.API_URL)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            for public_id in sorted(requested):
                response = await client.get(
                    self.API_URL,
                    params={"base_query": public_id, "result_limit": 10, "sort": "recent"},
                )
                response.raise_for_status()
                payload = response.json()
                jobs = payload.get("jobs", [])
                if not isinstance(jobs, list):
                    raise ValueError("Amazon Jobs returned an unexpected payload")
                for raw in jobs:
                    path = str(raw.get("job_path") or raw.get("url") or "")
                    match = re.search(r"/jobs/(\d+)(?:/|$)", path)
                    exact_id = str(raw.get("job_id") or (match.group(1) if match else ""))
                    if exact_id == public_id:
                        found[public_id] = raw
        missing = sorted(requested - set(found))
        if missing:
            raise RuntimeError(
                "Amazon Jobs did not verify the requested public posting IDs: "
                + ", ".join(missing)
            )
        return [found[public_id] for public_id in sorted(requested)]

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        path = raw.get("job_path") or raw.get("url") or ""
        url = path if str(path).startswith("http") else f"https://www.amazon.jobs{path}"
        public_id_match = re.search(r"/jobs/(\d+)(?:/|$)", str(path))
        public_job_id = raw.get("job_id") or (public_id_match.group(1) if public_id_match else raw.get("id"))
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
            external_id=public_job_id,
            ats_requisition_id=str(public_job_id or ""),
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
