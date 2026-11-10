from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, Iterable

from app.services.normalization import normalize_title, normalized_token
from app.services.target_companies import canonicalize_url
from app.services.discovery_records import opportunity_ats


def value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def same_job(left: Any, right: Any) -> bool:
    left_external = normalized_token(value(left, "external_id"))
    right_external = normalized_token(value(right, "external_id"))
    left_source = normalized_token(value(left, "source_name"))
    right_source = normalized_token(value(right, "source_name"))
    same_company = normalized_token(value(left, "company")) == normalized_token(value(right, "company"))
    left_years = set(re.findall(r"\b20\d{2}\b", value(left, "title", "") or ""))
    right_years = set(re.findall(r"\b20\d{2}\b", value(right, "title", "") or ""))
    if same_company and left_years and right_years and left_years.isdisjoint(right_years):
        return False  # Annual programs can reuse a landing URL, not a cycle.
    left_ats = opportunity_ats(left)
    right_ats = opportunity_ats(right)
    compatible_scope = left_ats == right_ats or "unknown" in {left_ats, right_ats}
    if left_external and left_external == right_external and same_company and ((left_source == right_source and compatible_scope) or left_ats == right_ats != "unknown"):
        return True

    left_requisition = normalized_token(value(left, "ats_requisition_id", "") or "")
    right_requisition = normalized_token(value(right, "ats_requisition_id", "") or "")
    if left_requisition and left_requisition == right_requisition and same_company and ((left_source == right_source and compatible_scope) or left_ats == right_ats != "unknown"):
        return True

    # Google's recruiting cycles reuse titles and locations, but have distinct
    # requisitions. Never collapse a new fall posting into a closed early cycle.
    if same_company and normalized_token(value(left, "company")) == "google" and left_external and right_external and left_external != right_external:
        return False

    left_apply = canonicalize_url(value(left, "apply_url", "") or "")
    right_apply = canonicalize_url(value(right, "apply_url", "") or "")
    if left_apply and right_apply and left_apply == right_apply:
        return True
    left_official = canonicalize_url(value(left, "canonical_official_url", "") or "")
    right_official = canonicalize_url(value(right, "canonical_official_url", "") or "")
    if left_official and right_official and left_official == right_official:
        return True

    left_hash = value(left, "raw_data_hash")
    right_hash = value(right, "raw_data_hash")
    if left_hash and right_hash and left_hash == right_hash:
        return True

    company_match = same_company
    location_match = normalized_token(value(left, "location")) == normalized_token(value(right, "location"))
    if not company_match:
        return False

    title_ratio = SequenceMatcher(
        None,
        normalize_title(value(left, "title", "")),
        normalize_title(value(right, "title", "")),
    ).ratio()
    left_description = normalized_token(value(left, "description", ""))[:1200]
    right_description = normalized_token(value(right, "description", ""))[:1200]
    description_ratio = SequenceMatcher(None, left_description, right_description).ratio()
    if left_ats != "unknown" and right_ats != "unknown" and left_external and right_external and (left_ats != right_ats or left_external != right_external):
        return False  # Reused titles are not proof of the same requisition.
    if normalize_title(value(left, "title", "")) == normalize_title(value(right, "title", "")) and location_match:
        return True
    return False  # Fuzzy evidence is surfaced for review, never auto-merged.


def find_duplicate(existing_jobs: Iterable[Any], candidate: Any) -> Any | None:
    return next((job for job in existing_jobs if same_job(job, candidate)), None)


def possible_duplicate(existing_jobs, candidate):
    matches = []
    for job in existing_jobs:
        if normalized_token(value(job, "company")) != normalized_token(value(candidate, "company")):
            continue
        if normalized_token(value(job, "location")) != normalized_token(value(candidate, "location")):
            continue
        confidence = SequenceMatcher(None, normalize_title(value(job, "title", "")), normalize_title(value(candidate, "title", ""))).ratio()
        if confidence >= .75:
            matches.append((confidence, job))
    return max(matches, key=lambda pair: pair[0]) if matches else (None, None)
