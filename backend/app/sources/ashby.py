"""Public per-board Ashby API; no browser automation or global board crawl."""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit
import httpx
from app.services.source_rate_limit import request_hooks
from app.core.config import settings
from app.sources.base import JobSourceAdapter, is_target_internship_title


class AshbyAdapter(JobSourceAdapter):
    source_name = "Ashby"
    complete_snapshot = False

    @property
    def api_url(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.source_identifier):
            raise ValueError("Invalid Ashby board slug")
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.source_identifier}"

    async def fetch_jobs(self):
        async with httpx.AsyncClient(event_hooks=request_hooks(), timeout=settings.request_timeout_seconds, follow_redirects=False) as client:
            response = await client.get(self.api_url)
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError("Ashby response has no jobs list")
        jobs = [j for j in payload["jobs"] if isinstance(j, dict) and j.get("isListed", True)]
        self.all_external_ids = {str(j.get("id") or urlsplit(j.get("jobUrl", "")).path.rstrip("/").split("/")[-1]) for j in jobs}
        self.complete_snapshot = True
        self.fetched_count = len(jobs)
        return [j for j in jobs if is_target_internship_title(j.get("title", ""))]

    def normalize_job(self, raw):
        job_url = raw.get("jobUrl", "")
        return self.build_job(raw,
            external_id=raw.get("id") or urlsplit(job_url).path.rstrip("/").split("/")[-1],
            title=raw.get("title", ""), location=raw.get("location", "Unknown"),
            description=raw.get("descriptionHtml") or raw.get("descriptionPlain", ""),
            apply_url=raw.get("applyUrl") or job_url, original_source_url=job_url,
            official_apply_url=raw.get("applyUrl") or job_url,
            employment_type=raw.get("employmentType", "Unknown"),
            posted_at=raw.get("publishedAt"), official_posted_at=raw.get("publishedAt"),
            official_status="open", verification_status="verified",
            verification_method="official_ashby_api", last_verified_at=datetime.now(timezone.utc),
            status_reason="Published on the configured official Ashby board.")
