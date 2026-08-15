from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR
from app.sources.base import JobSourceAdapter, NormalizedJob


class LocalJsonAdapter(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Local JSON"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        path = Path(self.source_identifier)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        if not path.is_file() or BACKEND_DIR not in path.resolve().parents:
            raise ValueError("Local JSON source must remain inside the backend directory")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Local JSON source must contain a list")
        return data

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        return self.build_job(
            raw,
            external_id=raw.get("external_id"),
            company=raw.get("company"),
            title=raw.get("title", ""),
            location=raw.get("location", ""),
            description=raw.get("description", ""),
            requirements=raw.get("requirements", ""),
            preferred_qualifications=raw.get("preferred_qualifications", ""),
            apply_url=raw.get("apply_url", ""),
            country=raw.get("country", ""),
            remote_type=raw.get("remote_type", ""),
            employment_type=raw.get("employment_type", "Internship"),
            duration=raw.get("duration"),
            posted_at=raw.get("posted_at"),
            official_posted_at=raw.get("official_posted_at") or raw.get("posted_at"),
            expires_at=raw.get("expires_at"),
            original_source_url=raw.get("original_source_url") or raw.get("apply_url", ""),
            official_apply_url=raw.get("official_apply_url") or raw.get("apply_url"),
            official_status=raw.get("official_status", "open"),
            verification_status=raw.get("verification_status", "verified"),
            verification_method=raw.get("verification_method", "local_test_fixture"),
            status_reason=raw.get("status_reason", "Verified test fixture"),
            discovery_status="demo",
            last_verified_at=raw.get("last_verified_at") or raw.get("posted_at"),
            remote_from_mexico_allowed=raw.get("remote_from_mexico_allowed"),
            is_active=raw.get("is_active", True),
        )
