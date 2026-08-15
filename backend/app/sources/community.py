from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.normalization import clean_text, normalized_token, validate_public_url
from app.services.verification import is_plausible_official_url, verify_official_application
from app.sources.base import JobSourceAdapter, NormalizedJob, is_target_internship_title


SOURCE_FILES: dict[str, tuple[str, ...]] = {
    "simplify": (
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/main/README.md",
    ),
    "speedyapply": (
        "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/README.md",
        "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/INTERN_INTL.md",
    ),
    "faang_tracker": (
        "https://raw.githubusercontent.com/Emjumaev/FAANG-2027-Internships-Tracker/main/README.md",
    ),
    "applyguy": (
        "https://raw.githubusercontent.com/ApplyGuy/2027-Internships/main/data/internships.json",
    ),
    "community_aggregator": (
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/software-engineering.md",
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/data-science-ai-machine-learning.md",
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/hardware-engineering.md",
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/product-management.md",
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/quantitative-finance.md",
        "https://raw.githubusercontent.com/SuryaHarikrishnan/internship-tracker/master/listings/other.md",
    ),
}

SOURCE_NAMES = {
    "simplify": "SimplifyJobs",
    "speedyapply": "speedyapply",
    "faang_tracker": "FAANG 2027 Internship Tracker",
    "applyguy": "ApplyGuy 2027 Internships",
    "community_aggregator": "Community Internship Aggregator",
}

CONFIDENCE = {
    "simplify": 65.0,
    "speedyapply": 65.0,
    "faang_tracker": 65.0,
    "applyguy": 75.0,
    "community_aggregator": 50.0,
}

MEXICO_PRIORITY_TERMS = (
    "mexico", "guadalajara", "zapopan", "tlaquepaque", "jalisco", "cdmx",
    "mexico city", "monterrey", "queretaro", "querétaro", "tijuana",
    "remote mexico", "remote latam", "latin america", "global remote",
    "worldwide remote",
)

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
RAW_URL_PATTERN = re.compile(r"https?://[^\s|<>]+")
class CommunityRateLimitError(RuntimeError):
    pass


def _plain_cell(cell: str) -> str:
    without_links = LINK_PATTERN.sub(lambda match: match.group(1), cell)
    return clean_text(re.sub(r"<[^>]+>", " ", without_links).replace("<br>", " / "))


def _application_url(cell: str) -> str:
    links = [match.group(2).rstrip(".,") for match in LINK_PATTERN.finditer(cell)]
    if links:
        return links[-1]
    match = RAW_URL_PATTERN.search(cell)
    return match.group(0).rstrip(".,)\"'") if match else ""


def _preferred_url(urls: list[str]) -> str:
    if not urls:
        return ""
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        if host not in {"simplify.jobs", "www.simplify.jobs", "applyguy.ai", "www.applyguy.ai"}:
            return url
    return urls[0]


def extract_ats_requisition_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
    for key in ("gh_jid", "jobid", "job_id", "requisitionid", "reqid"):
        if query.get(key):
            return clean_text(query[key][0])

    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    if not segments:
        return ""
    if "greenhouse" in host:
        match = re.search(r"/jobs/(\d{5,})", parsed.path, re.IGNORECASE)
        return match.group(1) if match else ""
    if "lever.co" in host or "ashbyhq.com" in host:
        candidates = [segment for segment in segments if segment.lower() not in {"apply", "application"}]
        candidate = candidates[-1] if candidates else ""
        return candidate if re.fullmatch(r"[A-Za-z0-9-]{8,}", candidate) else ""
    if "myworkdayjobs.com" in host:
        last = segments[-1]
        match = re.search(
            r"(?:^|_)((?:REQ|JR|R)[A-Za-z0-9-]{3,}|\d{5,}(?:-\d+)?)$",
            last,
            re.IGNORECASE,
        )
        return match.group(1) if match else ""
    match = re.search(r"/(?:jobs?|positions?|requisitions?)/(?:job/)?([A-Za-z0-9_-]{5,})", parsed.path, re.IGNORECASE)
    return match.group(1) if match else ""


def community_markers(text: str) -> tuple[list[str], str, bool]:
    normalized = normalized_token(text)
    markers: list[str] = []
    sponsorship = "UNKNOWN"
    closed = False
    if "🛂" in text or "\U0001F6C2" in text or any(term in normalized for term in ("no sponsorship", "does not sponsor")):
        markers.append("SPONSORSHIP_UNAVAILABLE_HINT")
        sponsorship = "LIKELY_UNAVAILABLE"
    if "🇺🇸" in text or "\U0001F1FA\U0001F1F8" in text or "u s citizenship required" in normalized:
        markers.append("US_CITIZENSHIP_HINT")
    if "🎓" in text or "\U0001F393" in text or "advanced degree" in normalized:
        markers.append("ADVANCED_DEGREE_HINT")
    if "🔒" in text or "\U0001F512" in text or any(term in normalized for term in ("closed", "applications closed")):
        markers.append("CLOSED_HINT")
        closed = True
    if any(term in normalized for term in ("sponsorship available", "will sponsor")):
        markers.append("SPONSORSHIP_AVAILABLE_HINT")
        sponsorship = "LIKELY_AVAILABLE"
    return markers, sponsorship, closed


def _parse_html_table_jobs(content: str, origin: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if "<table" not in content.lower():
        return jobs
    soup = BeautifulSoup(content, "html.parser")
    for table in soup.find_all("table"):
        header_cells = table.find_all("th")
        headers = [normalized_token(cell.get_text(" ", strip=True)) for cell in header_cells]
        header_map: dict[str, int] = {}
        for position, header in enumerate(headers):
            if any(term in header for term in ("company", "employer")):
                header_map["company"] = position
            elif any(term in header for term in ("role", "title", "position")):
                header_map["title"] = position
            elif any(term in header for term in ("location", "country")):
                header_map["location"] = position
            elif any(term in header for term in ("application", "apply", "link", "posting")):
                header_map["application"] = position
            elif any(term in header for term in ("date", "posted")):
                header_map["posted"] = position
        if not {"company", "title"}.issubset(header_map):
            continue
        previous_company = ""
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue

            def get(name: str) -> Any | None:
                position = header_map.get(name, -1)
                return cells[position] if 0 <= position < len(cells) else None

            company_cell = get("company")
            title_cell = get("title")
            if title_cell is None:
                continue
            company = clean_text(company_cell.get_text(" ", strip=True) if company_cell else "")
            if company in {"", "↳", "â†³", "Ã¢â€ Â³"}:
                company = previous_company
            else:
                previous_company = company
            title = clean_text(title_cell.get_text(" ", strip=True))
            location_cell = get("location")
            location = clean_text(location_cell.get_text(" / ", strip=True) if location_cell else "")
            application_cell = get("application")
            link_scope = application_cell or row
            urls = [clean_text(str(link.get("href") or "")) for link in link_scope.find_all("a", href=True)]
            application = _preferred_url([url for url in urls if url.startswith(("http://", "https://"))])
            if company and title and application:
                raw_row = clean_text(row.get_text(" ", strip=True))
                markers, sponsorship, closed = community_markers(raw_row)
                jobs.append({
                    "company": company,
                    "title": title,
                    "location": location,
                    "apply_url": application,
                    "posted_at": clean_text(get("posted").get_text(" ", strip=True)) if get("posted") else "",
                    "community_markers": markers,
                    "community_sponsorship_signal": sponsorship,
                    "community_closed_hint": closed,
                    "community_origin": origin,
                })
    return jobs


def parse_markdown_jobs(content: str, origin: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    lines = content.splitlines()
    current_section = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = clean_text(re.sub(r"^##\s+", "", stripped))
        if "|" not in stripped or index + 1 >= len(lines):
            continue
        separator = lines[index + 1]
        if "|" not in separator or "---" not in separator:
            continue
        headers = [normalized_token(_plain_cell(cell)) for cell in line.strip().strip("|").split("|")]
        header_map: dict[str, int] = {}
        for position, header in enumerate(headers):
            if any(term in header for term in ("company", "employer")):
                header_map["company"] = position
            elif any(term in header for term in ("role", "title", "position")):
                header_map["title"] = position
            elif any(term in header for term in ("location", "country")):
                header_map["location"] = position
            elif any(term in header for term in ("application", "apply", "link", "posting")):
                header_map["application"] = position
            elif any(term in header for term in ("date", "posted")):
                header_map["posted"] = position
        if "title" not in header_map or ("company" not in header_map and not current_section):
            continue
        row_index = index + 2
        previous_company = ""
        while row_index < len(lines) and "|" in lines[row_index]:
            raw_row = lines[row_index]
            cells = raw_row.strip().strip("|").split("|")
            def get(name: str) -> str:
                position = header_map.get(name, -1)
                return cells[position] if 0 <= position < len(cells) else ""
            title = _plain_cell(get("title"))
            company = _plain_cell(get("company")) or current_section
            if company in {"", "↳", "â†³"}:
                company = previous_company
            elif company:
                previous_company = company
            location = _plain_cell(get("location"))
            application = _application_url(get("application") or raw_row)
            if company and title and application:
                markers, sponsorship, closed = community_markers(raw_row)
                jobs.append({
                    "company": company,
                    "title": title,
                    "location": location,
                    "apply_url": application,
                    "posted_at": _plain_cell(get("posted")),
                    "community_markers": markers,
                    "community_sponsorship_signal": sponsorship,
                    "community_closed_hint": closed,
                    "community_origin": origin,
                })
            row_index += 1
    jobs.extend(_parse_html_table_jobs(content, origin))
    unique: dict[str, dict[str, Any]] = {}
    for job in jobs:
        key = normalized_token(f"{job['company']}|{job['title']}|{job['location']}|{job['apply_url']}")
        unique[key] = job
    return list(unique.values())


def _records_from_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("internships", "jobs", "data", "results", "listings"):
            if key in value:
                return _records_from_json(value[key])
        records: list[dict[str, Any]] = []
        for item in value.values():
            records.extend(_records_from_json(item))
        return records
    return []


def parse_json_jobs(content: str, origin: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for record in _records_from_json(json.loads(content)):
        company = clean_text(str(record.get("company") or record.get("company_name") or ""))
        title = clean_text(str(record.get("role") or record.get("title") or record.get("position") or ""))
        location_value = record.get("location") or record.get("locations") or record.get("country") or ""
        location = clean_text(" / ".join(map(str, location_value)) if isinstance(location_value, list) else str(location_value))
        application = clean_text(str(
            record.get("listingUrl")
            or record.get("officialUrl")
            or record.get("application_url")
            or record.get("apply_url")
            or record.get("url")
            or record.get("link")
            or ""
        ))
        if not (company and title and application):
            continue
        markers, sponsorship, closed = community_markers(json.dumps(record, default=str))
        jobs.append({
            "company": company,
            "title": title,
            "location": location,
            "apply_url": application,
            "season": clean_text(str(record.get("season") or "")),
            "posted_at": record.get("posted") or record.get("posted_date") or record.get("date_posted") or record.get("date"),
            "community_markers": markers,
            "community_sponsorship_signal": sponsorship,
            "community_closed_hint": bool(record.get("closed")) or closed,
            "community_origin": origin,
        })
    return jobs


def discovery_priority(job: dict[str, Any]) -> int:
    text = normalized_token(f"{job.get('location', '')} {job.get('title', '')}")
    if any(term in text for term in MEXICO_PRIORITY_TERMS):
        return 100
    if "remote" in text:
        return 80
    return 50


def repository_health(
    last_update: datetime | None,
    base_priority: int,
    now: datetime,
    stale_days: int = 90,
) -> tuple[str, int]:
    if last_update is None:
        return "ACTIVE", base_priority
    if last_update.tzinfo is None and now.tzinfo is not None:
        last_update = last_update.replace(tzinfo=now.tzinfo)
    if (now - last_update).days > stale_days:
        return "STALE", max(10, int(base_priority * 0.5))
    return "ACTIVE", base_priority


def official_source_label(url: str, company: str) -> tuple[str, float]:
    host = (urlparse(url).hostname or "").lower()
    labels = (
        ("greenhouse", "Greenhouse", 95.0),
        ("lever.co", "Lever", 95.0),
        ("myworkdayjobs", "Workday", 95.0),
        ("smartrecruiters", "SmartRecruiters", 95.0),
        ("oraclecloud", "Oracle Recruiting", 95.0),
        ("ashbyhq", "Ashby", 95.0),
    )
    for token, label, confidence in labels:
        if token in host:
            return label, confidence
    return f"{company} Careers", 100.0


class CommunityRepositoryAdapter(JobSourceAdapter):
    last_repository_update: datetime | None = None
    fetched_count: int = 0

    @property
    def source_name(self) -> str:
        return SOURCE_NAMES.get(self.source_identifier, self.company)

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        urls = SOURCE_FILES.get(self.source_identifier)
        if not urls:
            raise ValueError(f"Unsupported community source: {self.source_identifier}")
        jobs: list[dict[str, Any]] = []
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            repository_path = urlparse(self.source_url).path.strip("/")
            if repository_path.count("/") == 1:
                metadata_url = f"https://api.github.com/repos/{repository_path}"
                validate_public_url(metadata_url)
                metadata = await client.get(metadata_url, headers={"Accept": "application/vnd.github+json"})
                if metadata.status_code in {403, 429}:
                    raise CommunityRateLimitError(
                        f"GitHub rate limit reached for {self.source_name}; retry after the reset window."
                    )
                if metadata.status_code == 200:
                    pushed_at = metadata.json().get("pushed_at")
                    if pushed_at:
                        self.last_repository_update = datetime.fromisoformat(
                            str(pushed_at).replace("Z", "+00:00")
                        )
            seen_logical_files: set[str] = set()
            for url in urls:
                logical_file = url.rsplit("/", 1)[-1]
                if logical_file in seen_logical_files and jobs:
                    continue
                validate_public_url(url)
                response = await client.get(url)
                if response.status_code in {403, 429}:
                    raise CommunityRateLimitError(
                        f"GitHub rate limit reached for {self.source_name}; retry after the reset window."
                    )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                seen_logical_files.add(logical_file)
                self.fetched_count += 1
                last_modified = response.headers.get("last-modified")
                if last_modified:
                    try:
                        candidate = parsedate_to_datetime(last_modified)
                        if self.last_repository_update is None or candidate > self.last_repository_update:
                            self.last_repository_update = candidate
                    except (TypeError, ValueError):
                        pass
                parsed = (
                    parse_json_jobs(response.text, url)
                    if url.endswith(".json")
                    else parse_markdown_jobs(response.text, url)
                )
                jobs.extend(parsed)
        unique: dict[str, dict[str, Any]] = {}
        for job in jobs:
            if not is_target_internship_title(job.get("title", "")):
                continue
            key = normalized_token(f"{job['company']}|{job['title']}|{job['location']}|{job['apply_url']}")
            unique[key] = job
        return sorted(unique.values(), key=discovery_priority, reverse=True)

    async def collect(self) -> list[NormalizedJob]:
        normalized = [self.normalize_job(raw) for raw in await self.fetch_jobs()]
        candidates = [
            job for job in normalized
            if is_plausible_official_url(job.apply_url) and not job.raw_data.get("community_closed_hint")
        ][: settings.embedded_jobs_max_details]
        semaphore = asyncio.Semaphore(3)

        async def verify(job: NormalizedJob) -> None:
            async with semaphore:
                result = await verify_official_application(job.apply_url, job.title, job.external_id)
            if result.verification_status not in {"verified", "partially_verified"}:
                return
            job.official_apply_url = result.official_apply_url
            job.canonical_official_url = result.official_apply_url or ""
            job.official_status = result.official_status
            job.verification_status = result.verification_status
            job.verification_method = result.verification_method
            job.status_reason = result.status_reason
            job.last_verified_at = result.last_verified_at
            job.verified_from_source, job.source_confidence_score = official_source_label(
                result.official_apply_url or "", job.company
            )
            if result.page_text:
                job.description = result.page_text
                job.requirements = result.page_text
            if result.official_status in {"closed", "expired", "unavailable"}:
                job.is_active = False

        await asyncio.gather(*(verify(job) for job in candidates))
        return normalized

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        url = raw.get("apply_url", "")
        requisition = extract_ats_requisition_id(url)
        closed_hint = bool(raw.get("community_closed_hint"))
        description = (
            f"Discovered by {self.source_name}. Community metadata only; "
            "eligibility, sponsorship, remote scope, deadline, and active status require official verification."
        )
        return self.build_job(
            raw,
            external_id=requisition or None,
            company=raw.get("company"),
            title=raw.get("title", ""),
            location=raw.get("location", ""),
            description=description,
            requirements="",
            apply_url=url,
            posted_at=raw.get("posted_at"),
            original_source_url=raw.get("community_origin") or self.source_url,
            official_apply_url=None,
            official_status="unknown",
            verification_status="unverified",
            verification_method="community_discovery",
            status_reason=(
                "Community repository marks this listing closed; official status is not verified."
                if closed_hint else
                "Community discovery only. Official employer verification is required."
            ),
            discovery_status="community_closed" if closed_hint else "discovered",
            is_active=not closed_hint,
            discovered_from_source=self.source_name,
            discovery_sources=[self.source_name],
            source_confidence_score=CONFIDENCE.get(self.source_identifier, 50),
            community_sponsorship_signal=raw.get("community_sponsorship_signal", "UNKNOWN"),
            community_markers=raw.get("community_markers", []),
            ats_requisition_id=requisition,
        )
