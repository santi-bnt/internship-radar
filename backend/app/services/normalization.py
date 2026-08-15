from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse

import bleach


COUNTRY_HINTS = {
    "Mexico": ("mexico", "méxico", "monterrey", "guadalajara", "queretaro", "querétaro", "cdmx"),
    "United States": (
        "united states",
        "usa",
        "u.s.",
        "california",
        "texas",
        "washington",
        "arizona",
        "oregon",
        "massachusetts",
        "new york",
    ),
    "Canada": ("canada", "ontario", "toronto", "vancouver", "quebec", "ottawa", "waterloo"),
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    decoded = value
    for _ in range(3):
        next_value = unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    text = unescape(bleach.clean(decoded, tags=[], strip=True))
    return re.sub(r"\s+", " ", text).strip()


def clean_job_content(value: str | None) -> str:
    if not value:
        return ""
    decoded = value
    for _ in range(3):
        next_value = unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return bleach.clean(
        decoded,
        tags={
            "a", "article", "b", "br", "div", "em", "h1", "h2", "h3",
            "h4", "h5", "h6", "i", "li", "ol", "p", "section", "strong", "ul",
        },
        attributes={"a": ["href", "title"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    ).strip()


def normalized_token(value: str | None) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(value: str) -> str:
    text = normalized_token(value)
    noise = ("summer 2026", "fall 2026", "spring 2027", "2026", "2027", "job")
    for token in noise:
        text = text.replace(token, " ")
    return re.sub(r"\s+", " ", text).strip()


def detect_country(location: str, explicit_country: str | None = None) -> str:
    if explicit_country:
        return normalize_country(explicit_country)
    haystack = normalized_token(location)
    for country, hints in COUNTRY_HINTS.items():
        if any(normalized_token(hint) in haystack for hint in hints):
            return country
    return "Remote" if "remote" in haystack else "Unknown"


def normalize_country(value: str | None) -> str:
    normalized = normalized_token(value)
    if normalized in {"us", "u s", "usa", "united states", "united states of america"}:
        return "United States"
    if normalized in {"canada", "canada ca"}:
        return "Canada"
    if normalized in {"mexico", "mexico mx"}:
        return "Mexico"
    if normalized == "remote":
        return "Remote"
    return clean_text(value) or "Unknown"


def split_location(location: str) -> tuple[str, str]:
    parts = [part.strip() for part in clean_text(location).split(",") if part.strip()]
    country = detect_country(location)
    if parts and normalize_country(parts[-1]) == country:
        parts = parts[:-1]
    city = parts[0] if parts else ""
    region = ", ".join(parts[1:]) if len(parts) > 1 else ""
    return city, region


def detect_remote_type(location: str, description: str = "") -> str:
    text = normalized_token(f"{location} {description[:500]}")
    if "hybrid" in text:
        return "Hybrid"
    if "remote" in text:
        return "Remote"
    return "On-site"


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only public http(s) URLs are accepted")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not accepted")
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise ValueError("Private/local network URLs are not accepted")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Private/local network URLs are not accepted")
    except ValueError as exc:
        if "Private/local" in str(exc):
            raise
    return url


def raw_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
