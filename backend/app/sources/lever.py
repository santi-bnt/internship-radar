from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalization import validate_public_url
from app.sources.base import JobSourceAdapter, NormalizedJob


class LeverAdapter(JobSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Lever"

    @property
    def api_url(self) -> str:
        return f"https://api.lever.co/v0/postings/{self.source_identifier}?mode=json"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        validate_public_url(self.api_url)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.api_url)
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Lever returned an unexpected payload")
        return payload

    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        categories = raw.get("categories") or {}
        lists = raw.get("lists") or []
        requirements = " ".join(
            item.get("content", "") for item in lists if "require" in item.get("text", "").lower()
        )
        description = " ".join(
            [
                raw.get("descriptionPlain", ""),
                raw.get("additionalPlain", ""),
                " ".join(item.get("content", "") for item in lists),
            ]
        )
        return self.build_job(
            raw,
            external_id=raw.get("id"),
            title=raw.get("text", ""),
            location=categories.get("location", ""),
            description=description,
            requirements=requirements,
            apply_url=raw.get("applyUrl") or raw.get("hostedUrl", ""),
            employment_type=categories.get("commitment", "Internship"),
            posted_at=raw.get("createdAt"),
            official_posted_at=raw.get("createdAt"),
            original_source_url=raw.get("hostedUrl") or raw.get("applyUrl", ""),
            official_apply_url=raw.get("applyUrl") or raw.get("hostedUrl", ""),
            official_status="open",
            verification_status="verified",
            verification_method="official_lever_api",
            status_reason="Present on the official Lever board with an active application URL.",
            last_verified_at=datetime.now(timezone.utc),
        )
