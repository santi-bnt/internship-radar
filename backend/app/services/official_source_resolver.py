"""Bounded official resolution using the existing safe URL importer."""
from difflib import SequenceMatcher
from app.services.discovery_records import detect_ats
from app.services.normalization import normalized_token
from app.services.safe_job_fetch import validate_job_url
from app.services.verification import extract_external_target


class OfficialSourceResolver:
    def __init__(self, trusted_domains=()):
        self.trusted_domains = set(trusted_domains)

    async def resolve(self, normalized):
        from app.services.job_url_import import extract_job_url
        metadata = {**(normalized.raw_data or {}).get("_discovery_metadata", {}), "sourceExternalId": normalized.external_id}
        candidates = list(dict.fromkeys(filter(None, (
            metadata.get("originalUrl"), metadata.get("applicationUrl"),
            normalized.apply_url, extract_external_target(normalized.original_source_url),
        ))))[:3]
        for url in candidates:
            try:
                validate_job_url(url)
            except ValueError:
                continue
            # Reachability alone does not prove that an arbitrary aggregator
            # domain is official. Known ATS hosts and research domains qualify.
            from urllib.parse import urlsplit
            host = (urlsplit(url).hostname or "").lower()
            official_candidate = detect_ats(url) != "unknown" or host.endswith((".edu", ".ac.uk", ".epfl.ch", ".mcgill.ca")) or host in {"eee.epfl.ch", "allenai.org"} or host in self.trusted_domains
            if not official_candidate:
                continue
            try:
                official = None
                if host in self.trusted_domains:
                    # Prefer a real employer posting page, not a careers index
                    # whose first outgoing ATS link happens to match a result.
                    from bs4 import BeautifulSoup
                    from app.services.safe_job_fetch import fetch_job_page
                    from app.services.job_url_import import _generic_job, _job_posting_jsonld, JobExtractionError
                    from app.services.target_companies import canonicalize_url
                    page = await fetch_job_page(url)
                    if page.status_code in {404, 410}:
                        raise JobExtractionError("The official application appears closed or removed.")
                    structured = _job_posting_jsonld(BeautifulSoup(page.text, "html.parser"))
                    if page.status_code == 200 and structured.get("url") and canonicalize_url(str(structured["url"])) == canonicalize_url(page.url):
                        official, _ = _generic_job(page)
                        official.canonical_official_url = canonicalize_url(page.url)
                        if official.official_status == "closed":
                            official.verification_status = "verified"
                            official.official_apply_url = official.apply_url
                if official is None:
                    official = await extract_job_url(url)
            except (ValueError, RuntimeError) as exc:
                # Preserve a known original ATS URL as canonical, never label
                # it verified until identity and availability can be checked.
                normalized.canonical_official_url = url
                if "closed or removed" in str(exc).lower():
                    normalized.official_status = "closed"
                    normalized.verification_status = "dead"
                    normalized.verification_method = "official_http_404_410"
                    normalized.official_apply_url = url
                    normalized.is_active = False
                continue
            title_match = SequenceMatcher(None, normalized_token(normalized.title), normalized_token(official.title)).ratio() >= .72
            derived_employer = official.raw_data.get("_employer_identity") in {"board_slug", "tenant_slug"}
            company_match = normalized_token(normalized.company) == normalized_token(official.company) or (not derived_employer and normalized.company == "Unknown" and official.company not in {"", "Unknown"})
            if title_match and not company_match and derived_employer:
                from app.services.job_url_import import _ats_identity
                if _ats_identity(url) and _ats_identity(url) == _ats_identity(official.apply_url):
                    official.company = normalized.company
                    official.verification_status = "partially_verified"
                    official.status_reason = "Official ATS posting and title match; employer display name is source-reported and requires review."
                    company_match = True
            if not title_match or not company_match:
                normalized.status_reason = "Official candidate URL requires title/company review."
                continue
            official.discovered_from_source = normalized.discovered_from_source
            official.discovery_sources = list(dict.fromkeys([*normalized.discovery_sources, *official.discovery_sources]))
            official.raw_data = {**official.raw_data, "_discovery_metadata": metadata, "_discovered_url": normalized.original_source_url}
            official.original_source_url = normalized.original_source_url
            return official
        return normalized
