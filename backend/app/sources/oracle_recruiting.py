from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


class OracleRecruitingAdapter(JobSourceAdapter):
    """Oracle Recruiting Cloud Candidate Experience public API adapter."""

    SEARCH_KEYWORDS = (
        "software intern",
        "engineering intern",
        "hardware intern",
        "firmware intern",
        "student developer",
        "new college grad",
    )

    @property
    def source_name(self) -> str:
        return f"{self.company} Oracle Recruiting"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.source_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            landing = await client.get(self.source_url)
            landing.raise_for_status()
            site_number = self._site_number(landing.text)
            parts = urlsplit(str(landing.url))
            endpoint = (
                f"{parts.scheme}://{parts.netloc}"
                "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            )
            jobs: dict[str, dict[str, Any]] = {}
            errors: list[str] = []
            keywords = self.search_terms(self.SEARCH_KEYWORDS)
            for keyword in keywords:
                try:
                    response = await client.get(
                        endpoint,
                        params={
                            "onlyData": "true",
                            "expand": "requisitionList",
                            "finder": (
                                f"findReqs;siteNumber={site_number},keyword={keyword},"
                                "limit=100,sortBy=RELEVANCY"
                            ),
                        },
                    )
                    response.raise_for_status()
                    search = (response.json().get("items") or [{}])[0]
                    for raw in search.get("requisitionList") or []:
                        job_id = str(raw.get("Id") or "")
                        title = clean_text(raw.get("Title"))
                        if job_id and is_target_internship_title(title):
                            jobs[job_id] = raw
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    errors.append(f"{keyword}: {exc}")
            if not jobs and errors:
                raise RuntimeError("Oracle Recruiting searches failed: " + "; ".join(errors))
            return list(jobs.values())

    @staticmethod
    def _site_number(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        base = soup.find("base", attrs={"data-sitenumber": True})
        value = clean_text(base.get("data-sitenumber")) if base else ""
        if not value:
            match = re.search(r'data-sitenumber=["\']([^"\']+)', html, re.IGNORECASE)
            value = clean_text(match.group(1)) if match else ""
        if not value:
            raise RuntimeError("Oracle Recruiting site number was not present in the public page.")
        return value

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        job_id = str(raw["Id"])
        apply_url = f"{self.source_url.rstrip('/')}/job/{job_id}"
        description = clean_text(raw.get("ShortDescriptionStr"))
        qualifications = clean_text(raw.get("ExternalQualificationsStr"))
        responsibilities = clean_text(raw.get("ExternalResponsibilitiesStr"))
        combined = "\n\n".join(part for part in (description, responsibilities) if part)
        return self.build_job(
            raw,
            external_id=job_id,
            title=raw.get("Title", ""),
            location=raw.get("PrimaryLocation", ""),
            country=raw.get("PrimaryLocationCountry", ""),
            description=combined,
            requirements=qualifications,
            apply_url=apply_url,
            posted_at=raw.get("PostedDate"),
            expires_at=raw.get("PostingEndDate"),
            original_source_url=apply_url,
            official_apply_url=apply_url,
            official_status="open",
            verification_status="verified",
            verification_method="oracle_recruiting_cloud_api",
            status_reason="Found in Oracle Recruiting Cloud's public job-search API.",
            last_verified_at=datetime.now(timezone.utc),
        )
