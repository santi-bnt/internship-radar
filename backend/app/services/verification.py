from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, normalized_token, validate_public_url


CLOSED_PHRASES = (
    "no longer available",
    "no longer accepting applications",
    "applications are no longer accepted",
    "this job has been filled",
    "this position is closed",
    "position has been filled",
    "job expired",
    "job unavailable",
    "position filled",
    "posting has expired",
)
BLOCKED_PHRASES = ("captcha", "verify you are human", "sign in to continue", "log in to continue")
APPLY_PHRASES = ("apply", "apply now", "submit application", "start application")
NON_OFFICIAL_HOSTS = {
    "embedded.jobs",
    "www.embedded.jobs",
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
    "glassdoor.com",
    "www.glassdoor.com",
    "joinhandshake.com",
    "www.joinhandshake.com",
    "buymeacoffee.com",
    "www.buymeacoffee.com",
    "calendly.com",
    "www.calendly.com",
    "t.me",
    "telegram.me",
    "github.com",
    "www.github.com",
    "raw.githubusercontent.com",
}


@dataclass(frozen=True)
class VerificationResult:
    official_status: str
    verification_status: str
    verification_method: str
    status_reason: str
    official_apply_url: str | None
    last_verified_at: datetime
    page_text: str = ""


def extract_external_target(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("url", "target", "redirect", "destination", "apply"):
        if query.get(key):
            return unquote(query[key][0])
    return url


def is_plausible_official_url(url: str) -> bool:
    try:
        validate_public_url(url)
    except ValueError:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host not in NON_OFFICIAL_HOSTS


def _title_present(title: str, page_text: str) -> bool:
    normalized_title = normalized_token(title)
    normalized_page = normalized_token(page_text)
    if normalized_title and normalized_title in normalized_page:
        return True
    important = [token for token in normalized_title.split() if len(token) > 3]
    token_ratio = sum(token in normalized_page for token in important) / max(1, len(important))
    if token_ratio >= 0.75:
        return True
    return SequenceMatcher(None, normalized_title, normalized_page[: max(500, len(normalized_title) * 8)]).ratio() >= 0.55


def _looks_like_general_careers(url: str, title_found: bool, job_id_found: bool) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    generic_paths = {"", "/careers", "/jobs", "/search", "/job-search", "/careers/search"}
    return path in generic_paths and not title_found and not job_id_found


def workday_detail_api_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if "myworkdayjobs.com" not in host:
        return None
    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    try:
        job_index = next(index for index, segment in enumerate(segments) if segment.lower() == "job")
    except StopIteration:
        return None
    if job_index < 1 or job_index + 1 >= len(segments):
        return None
    tenant = host.split(".", 1)[0]
    site = segments[job_index - 1]
    external_path = "/".join(segments[job_index:])
    return f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{tenant}/{site}/{external_path}"


async def _verify_workday_api(
    client: httpx.AsyncClient,
    final_url: str,
    expected_title: str,
    now: datetime,
) -> VerificationResult | None:
    detail_url = workday_detail_api_url(final_url)
    if not detail_url:
        return None
    try:
        validate_public_url(detail_url)
        response = await client.get(detail_url, headers={"Accept": "application/json"})
        if response.status_code != 200:
            return None
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    info = payload.get("jobPostingInfo", payload) if isinstance(payload, dict) else {}
    if not isinstance(info, dict):
        return None
    official_title = clean_text(str(info.get("title") or ""))
    description_html = str(info.get("jobDescription") or "")
    description = clean_text(BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True))
    location = clean_text(str(info.get("location") or ""))
    page_text = clean_text(" ".join(part for part in (official_title, location, description) if part))
    if not official_title or not _title_present(expected_title, f"{official_title} {page_text}"):
        return None
    official_url = clean_text(str(info.get("externalUrl") or final_url))
    return VerificationResult(
        "open",
        "verified",
        "official_workday_api",
        "The job is present in the official Workday job-posting API.",
        official_url,
        now,
        page_text,
    )


async def verify_official_application(
    url: str,
    title: str,
    external_id: str | None = None,
    expires_at: datetime | None = None,
) -> VerificationResult:
    now = datetime.now(timezone.utc)
    try:
        validate_public_url(url)
    except ValueError as exc:
        return VerificationResult("unknown", "verification_failed", "url_validation", str(exc), None, now)

    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            return VerificationResult(
                "expired",
                "verified",
                "deadline",
                "Deadline has passed.",
                url,
                now,
            )

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            final_url = str(response.url)
            if response.status_code < 400:
                workday_result = await _verify_workday_api(client, final_url, title, now)
                if workday_result is not None:
                    return workday_result
    except httpx.HTTPError as exc:
        return VerificationResult(
            "unknown",
            "verification_failed",
            "http_error",
            f"Official page request failed: {exc.__class__.__name__}.",
            url,
            now,
        )

    final_url = str(response.url)
    if response.status_code in {404, 410}:
        return VerificationResult(
            "unavailable",
            "verified",
            "http_status",
            f"Official page returned HTTP {response.status_code}.",
            final_url,
            now,
        )
    if response.status_code >= 400:
        return VerificationResult(
            "unknown",
            "verification_failed",
            "http_status",
            f"Official page returned HTTP {response.status_code}.",
            final_url,
            now,
        )

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = clean_text(soup.get_text(" ", strip=True))
    normalized_page = normalized_token(page_text)
    if any(phrase in normalized_page for phrase in BLOCKED_PHRASES):
        return VerificationResult(
            "unknown",
            "verification_failed",
            "access_blocked",
            "The official page requires login or human verification.",
            final_url,
            now,
            page_text,
        )
    closed_phrase = next((phrase for phrase in CLOSED_PHRASES if phrase in normalized_page), None)
    if closed_phrase:
        return VerificationResult(
            "closed",
            "verified",
            "official_page_text",
            f"Official page says: {closed_phrase}.",
            final_url,
            now,
            page_text,
        )

    title_found = _title_present(title, page_text)
    job_id_found = bool(external_id and normalized_token(external_id) in normalized_page)
    actionable_elements = soup.find_all(["a", "button", "input"])
    apply_found = bool(soup.find("form")) or any(
        any(phrase in normalized_token(element.get_text(" ", strip=True) or element.get("value", "")) for phrase in APPLY_PHRASES)
        for element in actionable_elements
    )

    if _looks_like_general_careers(final_url, title_found, job_id_found):
        return VerificationResult(
            "unknown",
            "verification_failed",
            "redirect_check",
            "The link redirects to a general careers page instead of the job.",
            final_url,
            now,
            page_text,
        )
    if title_found and apply_found:
        return VerificationResult(
            "open",
            "verified",
            "official_page",
            "Official application is still accepting submissions.",
            final_url,
            now,
            page_text,
        )
    if title_found:
        return VerificationResult(
            "unknown",
            "partially_verified",
            "official_page",
            "The title is present, but an application button or form was not confirmed.",
            final_url,
            now,
            page_text,
        )
    return VerificationResult(
        "unknown",
        "verification_failed",
        "official_page",
        "External listing could not be confirmed on the destination page.",
        final_url,
        now,
        page_text,
    )
