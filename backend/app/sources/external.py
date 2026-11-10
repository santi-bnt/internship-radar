"""ExternalDiscoverySource contract, including explicit manual ingestion."""
from app.schemas.discovery import RawOpportunity
from app.sources.base import JobSourceAdapter


class ExternalDiscoverySource(JobSourceAdapter):
    source_name = "External Discovery"
    complete_snapshot = False

    def normalize_job(self, raw):
        value = RawOpportunity.model_validate(raw)
        job = self.build_job(raw, external_id=value.external_id, title=value.title,
            company=value.company, location=value.location, description=value.description,
            apply_url=value.canonical_url or value.source_url, posted_at=value.posted_at,
            original_source_url=value.source_url, discovered_from_source=value.source_name,
            verification_status="unverified", verification_method="external_discovery",
            status_reason="External discovery requires official-source verification.")
        job.source_name = value.source_name
        job.source_url = value.source_url
        job.raw_data = {**raw, "_discovery_metadata": value.metadata}
        return job


class ManualSource(ExternalDiscoverySource):
    source_name = "Manual"

    async def fetch_jobs(self):
        return []  # Explicit payloads are injected into the shared pipeline.
