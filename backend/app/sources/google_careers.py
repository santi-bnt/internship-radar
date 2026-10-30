"""Read Google Careers' public server-rendered data without executing JavaScript."""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from bs4 import BeautifulSoup

from app.services.normalization import clean_text
from app.sources.base import is_target_internship_title


GOOGLE_SEARCH_URL = "https://www.google.com/about/careers/applications/jobs/results/"
logger = logging.getLogger(__name__)
REQUESTED_GOOGLE_IDS = {"122803627516404422", "100648618540573382"}
COUNTRY_CODES = {"US": "United States", "CA": "Canada", "MX": "Mexico", "IL": "Israel",
                 "CH": "Switzerland", "GB": "United Kingdom", "PL": "Poland", "RO": "Romania",
                 "IN": "India", "TW": "Taiwan", "DE": "Germany", "FR": "France"}


def _html_field(row: list[Any], index: int) -> str:
    value = row[index] if len(row) > index else None
    return value[1] if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str) else ""


def _qualifications(html: str, name: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    heading = next((tag for tag in soup.find_all(["h3", "h4"]) if name in tag.get_text().casefold()), None)
    if heading is None:
        return ""
    items = heading.find_next("ul")
    return str(items) if items is not None else ""


def _location_summary(locations: list[str], limit: int = 240) -> str:
    full = "; ".join(locations)
    if len(full) <= limit:
        return full
    selected = []
    for location in locations:
        remaining = len(locations) - len(selected) - 1
        suffix = f"; +{remaining} other locations" if remaining else ""
        if len("; ".join([*selected, location]) + suffix) > limit:
            break
        selected.append(location)
    if not selected:
        return "See official job page for locations"
    return "; ".join(selected) + f"; +{len(locations) - len(selected)} other locations"


def parse_google_listing(
    html: str, *, required_external_ids: set[str] | None = None,
    diagnostics: list[str] | None = None, invalid_rows: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Decode JSON data arrays in AF_initDataCallback; never eval provider scripts."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.get_text()
        if "AF_initDataCallback({" not in text:
            continue
        marker = re.search(r"\bdata\s*:", text)
        if marker is None:
            continue
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[marker.end():].lstrip())
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, list) or len(payload) < 4 or not isinstance(payload[0], list):
            continue
        if not isinstance(payload[2], int) or not isinstance(payload[3], int) or payload[3] <= 0:
            continue
        rows = payload[0]
        jobs = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 11:
                continue
            job_id, title, application_url = row[:3]
            if not isinstance(job_id, str) or not job_id.isdigit() or not isinstance(title, str):
                continue
            if row[7] != "Google" or (
                not is_target_internship_title(title)
                and job_id not in (required_external_ids or set())
            ):
                continue
            if application_url in (None, ""):
                message = f"Google Careers job {job_id}: no direct application URL in listing; official details page retained."
                logger.warning(message)
                if diagnostics is not None:
                    diagnostics.append(message)
            elif not _is_google_application_url(application_url):
                message = f"Google Careers job {job_id}: unsupported application URL format "
                if isinstance(application_url, str):
                    try:
                        parsed_url = urlsplit(application_url)
                        query_keys = ",".join(sorted({key for key, _ in parse_qsl(parsed_url.query)}))
                        message += f"(host={parsed_url.hostname or 'unknown'}, path={parsed_url.path or '/'}, "
                        message += f"query_keys={query_keys or 'none'}); row skipped."
                    except ValueError:
                        message += "(malformed URL); row skipped."
                else:
                    message += "(missing URL); row skipped."
                logger.warning(message)
                if diagnostics is not None:
                    diagnostics.append(message)
                if invalid_rows is not None:
                    invalid_rows.append(message)
                continue
            slug = re.sub(r"[^a-z0-9\s-]", "", title.casefold())
            slug = re.sub(r"[\s-]+", "-", slug).strip("-")
            url = f"{GOOGLE_SEARCH_URL}{job_id}-{slug}"
            locations = row[9] if isinstance(row[9], list) else []
            full_locations = [item[0] for item in locations if isinstance(item, list) and item and isinstance(item[0], str)]
            location = _location_summary(full_locations)
            countries = {item[5] for item in locations if isinstance(item, list) and len(item) > 5 and isinstance(item[5], str)}
            country = COUNTRY_CODES.get(next(iter(countries)), "") if len(countries) == 1 else ""
            cities = {clean_text(item[2]) for item in locations if isinstance(item, list) and len(item) > 2 and isinstance(item[2], str)}
            regions = {clean_text(item[4]) for item in locations if isinstance(item, list) and len(item) > 4 and isinstance(item[4], str)}
            city = next(iter(cities)) if len(cities) == 1 else ""
            region = next(iter(regions)) if len(regions) == 1 else ""
            qualifications = _html_field(row, 4)
            requirements = _html_field(row, 19) or _qualifications(qualifications, "minimum")
            preferred = _qualifications(qualifications, "preferred")
            # Only this job's notice, description and responsibilities. Search
            # recommendations and Google's general EEO footer are not requirements.
            description = "\n".join(filter(None, [
                _html_field(row, 15), "<h3>About the job</h3>" + _html_field(row, 10),
                "<h3>Responsibilities</h3>" + _html_field(row, 3),
            ]))
            jobs.append({"external_id": job_id, "title": clean_text(title), "url": url,
                         "application_url": application_url, "location_hint": location, "locations": full_locations, "country": country,
                         "city": city if len(city) <= 140 else "", "region": region if len(region) <= 140 else "",
                         "description": description, "requirements": requirements,
                         "preferred_qualifications": preferred})
        return jobs, payload[2], payload[3]
    raise ValueError("Google Careers public listing data is missing or its schema changed.")


def _is_google_application_url(value: Any) -> bool:
    """Accept known Google application and job-detail URL forms only."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.hostname not in {"www.google.com", "careers.google.com"}:
        return False
    path = parsed.path.rstrip("/")
    if path == "/about/careers/applications/signin":
        return bool(parsed.query and re.search(r"(?:^|&)jobId=[^&]+", parsed.query))
    return bool(re.fullmatch(r"/about/careers/applications/jobs/results/\d+(?:-[A-Za-z0-9-]+)?", path))
