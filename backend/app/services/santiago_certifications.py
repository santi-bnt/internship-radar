"""Verified, candidate-owned certification records for Santiago only."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified


UNIVERSITY_OF_MICHIGAN = "University of Michigan"
SANTIAGO_VERIFIED_CERTIFICATIONS = ()


def _identity(record: dict[str, Any]) -> tuple[str, str]:
    return (
        str(record.get("issuer") or record.get("organization") or "").strip().casefold(),
        str(record.get("credential_id") or "").strip().casefold(),
    )


def ensure_santiago_verified_certifications(profile: Any) -> list[str]:
    """Upsert exact credential records by issuer + credential ID.

    The caller authenticates Santiago; this helper never queries, creates, or
    alters another candidate profile.
    """
    records = list(getattr(profile, "certifications_json", None) or [])
    by_identity = {
        _identity(record): index for index, record in enumerate(records)
        if isinstance(record, dict) and all(_identity(record))
    }
    changed: list[str] = []
    for certification in SANTIAGO_VERIFIED_CERTIFICATIONS:
        key = _identity(certification)
        index = by_identity.get(key)
        if index is None:
            records.append(dict(certification))
            by_identity[key] = len(records) - 1
            changed.append(certification["credential_id"])
        elif records[index] != certification:
            records[index] = dict(certification)
            changed.append(certification["credential_id"])
    if changed:
        profile.certifications_json = records
        flag_modified(profile, "certifications_json")
    return changed
