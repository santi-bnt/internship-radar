from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, detect_country, parse_datetime, validate_public_url
from app.services.verification import (
    VerificationResult,
    extract_external_target,
    is_plausible_official_url,
    verify_official_application,
)
from app.sources.base import JobSourceAdapter, NormalizedJob


class EmbeddedJobsAdapter(JobSourceAdapter):
    listing_url = "https://embedded.jobs/internship-embedded-systems-jobs"

    def __init__(self, company: str, source_identifier: str, source_url: str):
        super().__init__(company, source_identifier, source_url)
        self._robots: RobotFileParser | None = None

    @property
    def source_name(self) -> str:
        return "EmbeddedJobs"

    async def _robots_allows(self, url: str) -> bool:
        if self._robots is not None:
            return self._robots.can_fetch(settings.user_agent, url)
        robots_url = "https://embedded.jobs/robots.txt"
        parser = RobotFileParser(robots_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(robots_url)
        if response.status_code == 404:
            parser.parse([])
        elif response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            raise RuntimeError(f"EmbeddedJobs robots.txt returned HTTP {response.status_code}")
        self._robots = parser
        return parser.can_fetch(settings.user_agent, url)

    async def _get(self, url: str) -> httpx.Response:
        validate_public_url(url)
        if not await self._robots_allows(url):
            raise PermissionError(f"robots.txt does not allow fetching {url}")
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "").lower()
        visible_text = clean_text(soup.get_text(" ", strip=True)).lower()
        challenge_title = any(
            phrase in title for phrase in ("captcha", "just a moment", "access denied", "verify you are human")
        )
        short_challenge = len(visible_text) < 1200 and any(
            phrase in visible_text
            for phrase in ("captcha", "verify you are human", "sign in to continue", "log in to continue")
        )
        if challenge_title or short_challenge:
            raise PermissionError("EmbeddedJobs presented a login or human-verification barrier")
        return response

    @staticmethod
    def _card_text(anchor) -> tuple[str, str, str, str, list[str]]:
        container = anchor
        for _ in range(7):
            parent = container.parent
            if parent is None:
                break
            container = parent
            candidate_text = clean_text(container.get_text(" ", strip=True))
            if "@" in candidate_text and len(candidate_text) >= 45:
                break
        text = clean_text(container.get_text(" ", strip=True))
        title = re.sub(r"^View\s+", "", clean_text(anchor.get_text(" ", strip=True)), flags=re.IGNORECASE)
        logo = container.find("img", alt=re.compile(r"\blogo\b", re.IGNORECASE))
        company = re.sub(r"\s+logo.*$", "", logo.get("alt", ""), flags=re.IGNORECASE) if logo else ""
        if not company:
            company_match = re.search(r"@\s*([^•]+?)(?=\s+[A-Z][^•,]+,\s*(?:United States|Canada|Mexico)|\s+(?:intern|entry|junior))", text)
            company = clean_text(company_match.group(1)) if company_match else "Unknown company"
        country = detect_country(text)
        location_match = re.search(
            r"([A-Za-zÀ-ÿ .'-]+(?:,\s*[A-Za-zÀ-ÿ .'-]+)*,\s*(?:United States|Canada|Mexico))",
            text,
        )
        location = clean_text(location_match.group(1)) if location_match else ("Remote" if "remote" in text.lower() else country)
        skill_text = text.split("⏱︎")[-1] if "⏱︎" in text else ""
        skills = [token for token in skill_text.split() if 1 < len(token) < 30][:15]
        return title, company, location, text, skills

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        response = await self._get(self.listing_url)
        soup = BeautifulSoup(response.text, "html.parser")
        jobs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for anchor in soup.select('a[href*="/job/"]'):
            href = urljoin(self.listing_url, anchor.get("href", ""))
            if not href or href in seen:
                continue
            seen.add(href)
            title, company, location, text, skills = self._card_text(anchor)
            if not title:
                continue
            jobs.append(
                {
                    "external_id": urlparse(href).path.rstrip("/").split("/")[-1],
                    "title": title,
                    "company": company,
                    "location": location,
                    "country": detect_country(location),
                    "employment_type": "Internship",
                    "description": text,
                    "skills": skills,
                    "embedded_url": href,
                }
            )
        return jobs

    @staticmethod
    def _job_posting(payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            if payload.get("@type") == "JobPosting":
                return payload
            for value in payload.values():
                found = EmbeddedJobsAdapter._job_posting(value)
                if found:
                    return found
        if isinstance(payload, list):
            for value in payload:
                found = EmbeddedJobsAdapter._job_posting(value)
                if found:
                    return found
        return None

    async def fetch_job_details(self, job: dict[str, Any] | str) -> dict[str, Any]:
        summary = {"embedded_url": job} if isinstance(job, str) else dict(job)
        response = await self._get(summary["embedded_url"])
        soup = BeautifulSoup(response.text, "html.parser")
        posting = None
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                posting = self._job_posting(json.loads(script.string or "{}"))
            except json.JSONDecodeError:
                continue
            if posting:
                break

        details = dict(summary)
        if posting:
            organization = posting.get("hiringOrganization") or {}
            location_data = posting.get("jobLocation") or {}
            if isinstance(location_data, list):
                location_data = location_data[0] if location_data else {}
            address = location_data.get("address") or {}
            location = ", ".join(
                str(address.get(key, "")).strip()
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(key)
            )
            details.update(
                {
                    "title": posting.get("title") or details.get("title"),
                    "company": organization.get("name") or details.get("company"),
                    "location": location or details.get("location", ""),
                    "description": posting.get("description") or details.get("description", ""),
                    "employment_type": posting.get("employmentType") or details.get("employment_type", "Internship"),
                    "source_posted_at": posting.get("datePosted"),
                    "expires_at": posting.get("validThrough"),
                    "skills": posting.get("skills") or details.get("skills", []),
                }
            )
        anchor_links = [
            (
                urljoin(summary["embedded_url"], anchor.get("href", "")),
                clean_text(anchor.get_text(" ", strip=True)),
            )
            for anchor in soup.find_all("a", href=True)
            if anchor.get("href")
        ]
        links = [link for link, _ in anchor_links]
        details["_links"] = links
        details["_apply_links"] = [
            link
            for link, label in anchor_links
            if any(token in label.lower() for token in ("apply", "application", "submit"))
        ]
        details["_page_text"] = clean_text(soup.get_text(" ", strip=True))
        details["country"] = detect_country(details.get("location", ""))
        return details

    def find_official_application(self, raw: dict[str, Any]) -> str | None:
        for link in raw.get("_apply_links", []):
            candidate = extract_external_target(link)
            if is_plausible_official_url(candidate):
                return candidate
        ats_hosts = (
            "greenhouse.io",
            "lever.co",
            "myworkdayjobs.com",
            "icims.com",
            "smartrecruiters.com",
            "jobvite.com",
            "ashbyhq.com",
            "oraclecloud.com",
            "successfactors.com",
        )
        for link in raw.get("_links", []):
            candidate = extract_external_target(link)
            host = (urlparse(candidate).hostname or "").lower()
            if any(host.endswith(ats_host) for ats_host in ats_hosts) and is_plausible_official_url(candidate):
                return candidate
        return None

    async def verify_official_status(
        self,
        official_url: str,
        title: str,
        external_id: str | None = None,
        expires_at=None,
    ) -> VerificationResult:
        return await verify_official_application(official_url, title, external_id, expires_at)

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        official_url = raw.get("official_apply_url")
        verified_official_url = (
            official_url
            if raw.get("official_status") == "open"
            and raw.get("verification_status") == "verified"
            else None
        )
        embedded_url = raw.get("embedded_url", self.listing_url)
        return self.build_job(
            raw,
            external_id=raw.get("external_id"),
            company=raw.get("company"),
            title=raw.get("title", ""),
            location=raw.get("location", ""),
            description=raw.get("description", ""),
            requirements=raw.get("requirements", ""),
            preferred_qualifications=raw.get("preferred_qualifications", ""),
            apply_url=verified_official_url or embedded_url,
            country=raw.get("country", ""),
            remote_type=raw.get("remote_type", ""),
            employment_type=raw.get("employment_type", "Internship"),
            posted_at=raw.get("source_posted_at"),
            official_posted_at=raw.get("official_posted_at"),
            expires_at=raw.get("expires_at"),
            original_source_url=embedded_url,
            official_apply_url=verified_official_url,
            official_status=raw.get("official_status", "unknown"),
            verification_status=raw.get("verification_status", "unverified"),
            verification_method=raw.get("verification_method", "embedded_jobs_discovery"),
            status_reason=raw.get("status_reason", "External listing could not be confirmed."),
            last_verified_at=raw.get("last_verified_at"),
            is_active=raw.get("official_status") not in {"closed", "expired", "unavailable"},
        )

    async def collect(self) -> list[NormalizedJob]:
        summaries = await self.fetch_jobs()
        collected: list[NormalizedJob] = []
        detail_rate_limited = False
        for summary in summaries[: settings.embedded_jobs_max_details]:
            country = summary.get("country")
            location_text = summary.get("location", "").lower()
            if country not in {"Mexico", "United States", "Canada", "Remote"} and "remote" not in location_text:
                continue
            details = dict(summary)
            if not detail_rate_limited:
                await asyncio.sleep(max(settings.embedded_jobs_delay_seconds, settings.source_rate_limit_seconds))
                try:
                    details = await self.fetch_job_details(summary)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        detail_rate_limited = True
                        details.update({
                            "official_status": "unknown",
                            "verification_status": "unverified",
                            "verification_method": "embedded_jobs_listing_rate_limited",
                            "status_reason": (
                                "EmbeddedJobs listing found; detail verification was deferred "
                                "because the site rate-limited additional requests."
                            ),
                        })
                    else:
                        raise
            elif detail_rate_limited:
                details.update({
                    "official_status": "unknown",
                    "verification_status": "unverified",
                    "verification_method": "embedded_jobs_listing_rate_limited",
                    "status_reason": (
                        "EmbeddedJobs listing found; detail verification was deferred "
                        "because the site rate-limited additional requests."
                    ),
                })
            official_url = self.find_official_application(details)
            if official_url:
                result = await self.verify_official_status(
                    official_url,
                    details.get("title", ""),
                    details.get("external_id"),
                    parse_datetime(details.get("expires_at")),
                )
                details.update(
                    {
                        "official_apply_url": result.official_apply_url,
                        "official_status": result.official_status,
                        "verification_status": result.verification_status,
                        "verification_method": result.verification_method,
                        "status_reason": result.status_reason,
                        "last_verified_at": result.last_verified_at,
                    }
                )
            elif not details.get("verification_method"):
                details.update(
                    {
                        "official_status": "unknown",
                        "verification_status": "unverified",
                        "verification_method": "embedded_jobs_discovery",
                        "status_reason": "External listing could not be confirmed on an official company page.",
                    }
                )
            collected.append(self.normalize_job(details))
        return collected
