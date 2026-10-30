from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title

logger = logging.getLogger(__name__)


RULES = {
    "google": re.compile(r"(?:/about/careers/applications/)?jobs/results/\d+[^?#]*"),
    "meta": re.compile(r"/jobs/\d+"),
    "arm": re.compile(r"/(?:[a-z]{2}/)?job/[^?#]+"),
    "synopsys": re.compile(r"/job/[^?#]+"),
    "amd": re.compile(r"/(?:students/)?jobs/\d+[^?#]*"),
    "qualcomm": re.compile(r"/careers/job/[^?#]+"),
}

QUERY_PARAMETERS = {
    "google": "q",
    "meta": "q",
    "arm": "k",
    "synopsys": "k",
    "amd": "keywords",
    "qualcomm": "query",
}


class OfficialCareersAdapter(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return f"{self.company} Careers"

    def search_urls(self) -> list[str]:
        parameter = QUERY_PARAMETERS[self.source_identifier]
        parsed = urlsplit(self.source_url)
        urls: list[str] = []
        for term in self.search_terms()[:6]:
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query[parameter] = term
            urls.append(
                urlunsplit(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        urlencode(query),
                        parsed.fragment,
                    )
                )
            )
        return list(dict.fromkeys(urls))

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.source_url)
        if self.source_identifier == "google":
            return await self._fetch_google_jobs()
        if self.source_identifier == "amd":
            return await self._fetch_amd_api_jobs()
        pattern = RULES[self.source_identifier]
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            discovered: dict[str, dict[str, str]] = {}
            listing_links_seen = False
            for search_url in self.search_urls():
                validate_public_url(search_url)
                response = await client.get(search_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    href = anchor["href"]
                    if not pattern.search(href):
                        continue
                    listing_links_seen = True
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
                if listing_links_seen:
                    return []
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

    async def _fetch_google_jobs(self) -> list[dict[str, Any]]:
        from app.sources.google_careers import GOOGLE_SEARCH_URL, parse_google_listing

        discovered: dict[str, dict[str, Any]] = {}
        diagnostics: list[str] = []
        invalid_rows: list[str] = []
        failed_pages = 0
        required_ids = {
            str(item) for item in self.search_criteria.get("required_external_ids", [])
            if str(item).isdigit()
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds,
                                     headers={"User-Agent": settings.user_agent}, follow_redirects=True) as client:
            # Exhaustive bounded intern search replaces six overlapping searches.
            # Each response already includes the complete job-specific content.
            for page in range(1, 11):
                logger.info("Google Careers internship search: fetching page %s/10 (attempt 1).", page)
                try:
                    response = await client.get(GOOGLE_SEARCH_URL, params={
                        "q": "intern", "employment_type": "INTERN", "hl": "en", "page": page,
                    })
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    failed_pages += 1
                    logger.error("Google Careers page %s failed with HTTP %s.", page, exc.response.status_code)
                    raise
                except httpx.HTTPError as exc:
                    failed_pages += 1
                    logger.error("Google Careers page %s request failed: %s", page, exc)
                    raise
                validate_public_url(str(response.url))
                page_diagnostics: list[str] = []
                page_invalid_rows: list[str] = []
                jobs, total, page_size = parse_google_listing(
                    response.text, required_external_ids=required_ids,
                    diagnostics=page_diagnostics, invalid_rows=page_invalid_rows,
                )
                diagnostics.extend(page_diagnostics)
                invalid_rows.extend(page_invalid_rows)
                if required_ids:
                    # An explicit candidate-requested import must not widen
                    # into the regular discovery feed from the same page.
                    jobs = [job for job in jobs if str(job.get("external_id")) in required_ids]
                discovered.update({job["external_id"]: job for job in jobs})
                if page * page_size >= total:
                    if diagnostics:
                        logger.warning(
                            "Google Careers reported %s warning(s), including %s skipped malformed row(s).",
                            len(diagnostics), len(invalid_rows),
                        )
                    if not discovered and invalid_rows:
                        raise RuntimeError(
                            "Google Careers returned internship rows, but none had a supported official "
                            f"application URL ({len(invalid_rows)} malformed row(s)); import aborted."
                        )
                    logger.info(
                        "Google Careers search complete: %s valid job(s), %s warning(s), %s skipped row(s), "
                        "%s failed page(s).", len(discovered), len(diagnostics), len(invalid_rows), failed_pages,
                    )
                    return list(discovered.values())
        raise RuntimeError("Google Careers exceeded the bounded pagination limit; discovery is incomplete.")

    async def _fetch_amd_api_jobs(self) -> list[dict[str, Any]]:
        """Use the public JSON endpoint that powers AMD's current careers UI."""
        api_url = "https://careers.amd.com/api/jobs"
        validate_public_url(api_url)
        discovered: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            for term in self.search_terms()[:6]:
                response = await client.get(api_url, params={"keywords": term, "page": 1})
                response.raise_for_status()
                payload = response.json()
                for wrapped in payload.get("jobs", []):
                    item = wrapped.get("data", wrapped)
                    title = clean_text(str(item.get("title") or ""))
                    if not is_target_internship_title(title):
                        continue
                    job_id = clean_text(str(item.get("req_id") or item.get("slug") or ""))
                    if not job_id:
                        continue
                    canonical_url = clean_text(str(
                        item.get("meta_data", {}).get("canonical_url")
                        or f"https://careers.amd.com/jobs/{job_id}?lang=en-us"
                    ))
                    discovered[job_id] = {
                        "title": title,
                        "url": canonical_url,
                        "location_hint": clean_text(str(
                            item.get("full_location") or item.get("location_name") or ""
                        )),
                        "description": clean_text(str(item.get("description") or "")),
                        "requirements": clean_text(str(item.get("qualifications") or "")),
                        "posted_at": item.get("posted_date"),
                        "external_id": job_id,
                    }
        if not discovered:
            raise RuntimeError("AMD official careers API exposed no matching internship jobs.")
        return list(discovered.values())

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        job_id = raw.get("external_id") or next(
            iter(re.findall(r"\d{5,}", raw["url"])), None
        )
        job = self.build_job(
            raw,
            external_id=job_id,
            title=raw["title"],
            location=raw.get("location_hint", ""),
            country=raw.get("country") or None,
            description=raw.get("description", ""),
            requirements=raw.get("requirements") or raw.get("description", ""),
            apply_url=raw["url"],
            original_source_url=raw["url"],
            official_apply_url=raw["url"],
            preferred_qualifications=raw.get("preferred_qualifications", ""),
            official_status="open",
            verification_status="verified",
            verification_method="official_careers_page",
            status_reason="Title and application page found on the official company careers site.",
            last_verified_at=datetime.now(timezone.utc),
            posted_at=raw.get("posted_at"),
        )
        if self.source_identifier == "google" and raw.get("application_url"):
            # Multi-location listings must not be split into a fictitious single
            # city/region (or overflow the bounded region database column).
            job.city = raw.get("city", "")
            job.region = raw.get("region", "")
            job.application_url = raw["application_url"]
            job.apply_url = raw["application_url"]
            job.application_url_source = "GOOGLE_PUBLIC_LISTING"
            job.canonical_official_url = raw["url"]
            job.source_confidence_score = 100
        return job
