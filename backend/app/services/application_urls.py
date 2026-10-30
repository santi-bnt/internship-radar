from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from app.services.normalization import clean_text
from app.services.verification import is_plausible_official_url


@dataclass(frozen=True)
class ApplicationUrlResolution:
    posting_url: str
    application_url: str
    source: str
    status: str
    diagnostic: str
    verified_at: datetime | None


def _candidate(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return clean_text(value)
    return ""


def resolve_application_url(job: Any) -> ApplicationUrlResolution:
    """Resolve only supplied official URLs; never synthesize a job or ATS endpoint."""
    raw = getattr(job, "raw_data", None) or (job.get("raw_data", {}) if isinstance(job, dict) else {})
    get = job.get if isinstance(job, dict) else lambda key, default="": getattr(job, key, default)
    posting = clean_text(str(
        get("posting_url") or get("canonical_official_url") or get("original_source_url")
        or get("official_apply_url") or get("apply_url") or ""
    ))
    supplied = clean_text(str(
        get("application_url") or get("official_apply_url") or get("apply_url") or ""
    ))
    metadata = _candidate(raw, "applicationUrl", "application_url", "applyUrl", "apply_url", "externalUrl")
    candidate = supplied or metadata
    if candidate and posting:
        candidate = urljoin(posting, candidate)
    if candidate and is_plausible_official_url(candidate):
        same_host = not posting or (urlparse(candidate).hostname == urlparse(posting).hostname)
        verified = str(get("verification_status", "")) == "verified"
        return ApplicationUrlResolution(
            posting, candidate, "OFFICIAL_ATS" if same_host else "OFFICIAL_REDIRECT",
            "VERIFIED" if verified else "DISCOVERED", "",
            datetime.now(timezone.utc) if verified else None,
        )
    if posting and is_plausible_official_url(posting):
        return ApplicationUrlResolution(
            posting, "", "UNKNOWN", "MISSING", "APPLICATION_URL_NOT_FOUND", None,
        )
    return ApplicationUrlResolution(
        posting, "", "UNKNOWN", "UNKNOWN", "OFFICIAL_POSTING_NOT_RESOLVED", None,
    )
