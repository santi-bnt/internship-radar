from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Iterable

from app.services.normalization import normalize_title, normalized_token
from app.services.target_companies import canonicalize_url


def value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def same_job(left: Any, right: Any) -> bool:
    left_external = normalized_token(value(left, "external_id"))
    right_external = normalized_token(value(right, "external_id"))
    left_source = normalized_token(value(left, "source_name"))
    right_source = normalized_token(value(right, "source_name"))
    same_company = normalized_token(value(left, "company")) == normalized_token(value(right, "company"))
    if left_external and left_external == right_external and (left_source == right_source or same_company):
        return True

    left_requisition = normalized_token(value(left, "ats_requisition_id", "") or "")
    right_requisition = normalized_token(value(right, "ats_requisition_id", "") or "")
    if left_requisition and left_requisition == right_requisition and same_company:
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
    if title_ratio >= 0.94 and (location_match or not value(left, "location") or not value(right, "location")):
        return True
    return location_match and title_ratio >= 0.88 and description_ratio >= 0.68


def find_duplicate(existing_jobs: Iterable[Any], candidate: Any) -> Any | None:
    return next((job for job in existing_jobs if same_job(job, candidate)), None)
