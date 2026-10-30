from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from typing import Any

from app.services.normalization import (
    clean_job_content,
    clean_text,
    detect_country,
    parse_datetime,
    raw_hash,
    split_location,
)
from app.services.classification import classify_area, classify_company_importance, classify_remote
from app.services.eligibility import extract_job_eligibility_signals
from app.services.target_companies import canonicalize_url
from app.services.normalization import normalize_title, normalized_token

STUDENT_TERMS = (
    "intern", "internship", "co-op", "co op", "student", "university",
    "student worker", "working student", "undergraduate", "trainee",
    "new college grad", "entry level", "early career",
)
SENIOR_TERMS = ("senior", "staff", "principal", "manager", "director", "lead")
TARGET_ROLE_TERMS = (
    "software",
    "application engineering",
    "security consultant",
    "site reliability",
    "sde",
    "embedded",
    "firmware",
    "robot",
    "fpga",
    "rtl",
    "digital design",
    "asic",
    "hardware",
    "electrical",
    "systems",
    "iot",
    "automation",
    "backend",
    "full stack",
    "frontend",
    "debug",
    "silicon",
    "soc",
    "computer architecture",
    "controls",
    "computer vision",
    "research",
    "edge ai",
    "ai",
    "machine learning",
    "data",
    "product",
    "linux",
    "device",
    "platform",
    "infrastructure",
    "cloud",
    "devops",
    "site reliability",
    "network",
    "security",
    "solutions engineering",
    "developer engineering",
    "semiconductor",
    "manufacturing",
    "automotive software",
    "electronics",
    "validation",
    "verification",
)
PROFILE_EXCLUSION_TERMS = (
    "phd",
    "ph.d",
    "doctoral",
    "mba",
    "military veteran",
)


def is_target_internship_title(title: str) -> bool:
    from app.services.talent_communities import is_talent_community
    if is_talent_community(title):
        return True
    normalized = clean_text(title).lower()
    return (
        not any(term in normalized for term in PROFILE_EXCLUSION_TERMS)
        and not any(term in normalized for term in SENIOR_TERMS)
        and any(term in normalized for term in STUDENT_TERMS)
        and any(term in normalized for term in TARGET_ROLE_TERMS)
    )


@dataclass
class NormalizedJob:
    external_id: str | None
    source_name: str
    source_url: str
    company: str
    title: str
    location: str
    country: str
    remote_type: str
    employment_type: str
    duration: str | None
    description: str
    requirements: str
    preferred_qualifications: str
    apply_url: str
    posting_url: str
    application_url: str
    application_url_source: str
    application_url_status: str
    application_url_last_verified_at: datetime | None
    application_url_diagnostic: str
    posted_at: datetime | None
    is_active: bool = True
    city: str = ""
    region: str = ""
    remote_regions: list[str] = field(default_factory=list)
    remote_countries_allowed: list[str] = field(default_factory=list)
    remote_from_mexico_allowed: bool = False
    remote_scope: str = "UNKNOWN"
    physical_work_country_required: str = "Unknown"
    can_work_from_mexico: str = "UNKNOWN"
    job_requires_work_in_us: bool = False
    sponsorship_status: str = "UNKNOWN"
    sponsorship_evidence_text: str = ""
    sponsorship_source_url: str = ""
    sponsorship_last_verified_at: datetime | None = None
    relocation_required: bool = False
    area: str = "Unknown"
    company_importance: str = "Unknown"
    official_apply_url: str | None = None
    original_source_url: str = ""
    discovered_from_source: str = ""
    verified_from_source: str = ""
    discovery_sources: list[str] = field(default_factory=list)
    source_confidence_score: float = 0
    community_sponsorship_signal: str = "UNKNOWN"
    community_markers: list[str] = field(default_factory=list)
    company_normalized: str = ""
    title_normalized: str = ""
    ats_requisition_id: str = ""
    canonical_official_url: str = ""
    discovery_status: str = "discovered"
    official_status: str = "unknown"
    verification_status: str = "unverified"
    verification_method: str = "not_attempted"
    status_reason: str = ""
    last_verified_at: datetime | None = None
    verification_failures: int = 0
    official_posted_at: datetime | None = None
    source_posted_at: datetime | None = None
    expires_at: datetime | None = None
    is_priority_alert: bool = False
    priority_alerted_at: datetime | None = None
    urgency: str = "Recent"
    recycled_posting: bool = False
    raw_data_hash: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobSourceAdapter(ABC):
    def __init__(
        self,
        company: str,
        source_identifier: str,
        source_url: str,
        search_criteria: dict[str, Any] | None = None,
    ):
        self.company = company
        self.source_identifier = source_identifier
        self.source_url = source_url
        self.search_criteria = search_criteria or {}

    def search_terms(self, defaults: tuple[str, ...] = (
        "software intern", "embedded firmware intern", "hardware intern",
        "fpga intern", "research intern", "machine learning intern",
        "co-op", "early career",
    )) -> list[str]:
        from app.services.search_criteria import discovery_search_terms

        return discovery_search_terms(self.search_criteria) or list(defaults)

    @property
    @abstractmethod
    def source_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def fetch_jobs(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize_job(self, raw: dict[str, Any]) -> NormalizedJob:
        raise NotImplementedError

    async def collect(self) -> list[NormalizedJob]:
        return [self.normalize_job(raw) for raw in await self.fetch_jobs()]

    def build_job(
        self,
        raw: dict[str, Any],
        *,
        external_id: str | int | None,
        title: str,
        location: str,
        description: str,
        apply_url: str,
        company: str | None = None,
        requirements: str = "",
        preferred_qualifications: str = "",
        country: str = "",
        remote_type: str = "",
        employment_type: str = "Internship",
        duration: str | None = None,
        posted_at: Any = None,
        official_posted_at: Any = None,
        expires_at: Any = None,
        original_source_url: str = "",
        official_apply_url: str | None = None,
        official_status: str = "unknown",
        verification_status: str = "unverified",
        verification_method: str = "not_attempted",
        status_reason: str = "",
        discovery_status: str = "discovered",
        last_verified_at: Any = None,
        remote_from_mexico_allowed: bool | None = None,
        relocation_required: bool = False,
        is_active: bool = True,
        discovered_from_source: str = "",
        verified_from_source: str = "",
        discovery_sources: list[str] | None = None,
        source_confidence_score: float = 0,
        community_sponsorship_signal: str = "UNKNOWN",
        community_markers: list[str] | None = None,
        ats_requisition_id: str = "",
    ) -> NormalizedJob:
        clean_description = clean_text(description)
        display_description = clean_job_content(description)
        display_requirements = clean_job_content(requirements)
        display_preferred = clean_job_content(preferred_qualifications)
        actual_company = clean_text(company or self.company)
        actual_country = detect_country(location, country)
        city, region = split_location(location)
        remote = classify_remote(location, clean_description, remote_type)
        if remote_from_mexico_allowed is not None:
            remote = remote.__class__(
                "Remote from Mexico" if remote_from_mexico_allowed else remote.remote_type,
                remote.remote_regions,
                remote.remote_countries_allowed,
                remote_from_mexico_allowed,
                remote.remote_scope if remote_from_mexico_allowed else remote.remote_scope,
                "YES" if remote_from_mexico_allowed else remote.can_work_from_mexico,
            )
        classification_input = {
            "title": title,
            "description": clean_description,
            "requirements": requirements,
            "skills": raw.get("skills", []),
        }
        source_posted_at = parse_datetime(posted_at)
        official_posted = parse_datetime(official_posted_at)
        official_url = official_apply_url or (apply_url if official_status == "open" else None)
        signal_input = {
            "location": location,
            "country": actual_country,
            "remote_type": remote.remote_type,
            "description": clean_description,
            "requirements": requirements,
            "preferred_qualifications": preferred_qualifications,
            "official_apply_url": official_url,
            "apply_url": apply_url,
            "source_url": self.source_url,
            "verification_status": verification_status,
            "last_verified_at": parse_datetime(last_verified_at),
        }
        signals = extract_job_eligibility_signals(signal_input)
        posting_url = original_source_url or apply_url
        application_url = official_url or ""
        application_status = "VERIFIED" if verification_status == "verified" and application_url else (
            "DISCOVERED" if application_url else "MISSING"
        )
        return NormalizedJob(
            external_id=str(external_id) if external_id is not None else None,
            source_name=self.source_name,
            source_url=self.source_url,
            company=actual_company,
            title=clean_text(title),
            location=clean_text(location),
            country=actual_country,
            city=city,
            region=region,
            remote_type=remote.remote_type,
            remote_regions=remote.remote_regions,
            remote_countries_allowed=remote.remote_countries_allowed,
            remote_from_mexico_allowed=remote.remote_from_mexico_allowed,
            remote_scope=signals.remote_scope,
            physical_work_country_required=signals.physical_work_country_required,
            can_work_from_mexico=signals.can_work_from_mexico,
            job_requires_work_in_us=signals.job_requires_work_in_us,
            sponsorship_status=signals.sponsorship_status,
            sponsorship_evidence_text=signals.sponsorship_evidence_text,
            sponsorship_source_url=signals.sponsorship_source_url,
            sponsorship_last_verified_at=signals.sponsorship_last_verified_at,
            relocation_required=relocation_required,
            employment_type=clean_text(employment_type) or "Internship",
            duration=clean_text(duration) or None,
            area=classify_area(classification_input),
            company_importance=classify_company_importance(actual_company),
            description=display_description,
            requirements=display_requirements,
            preferred_qualifications=display_preferred,
            apply_url=official_url or apply_url or original_source_url,
            posting_url=posting_url,
            application_url=application_url,
            application_url_source=("OFFICIAL_ATS" if official_url else "UNKNOWN"),
            application_url_status=application_status,
            application_url_last_verified_at=parse_datetime(last_verified_at),
            application_url_diagnostic=("" if application_url else "APPLICATION_URL_NOT_FOUND"),
            official_apply_url=official_url,
            original_source_url=original_source_url or apply_url,
            discovered_from_source=discovered_from_source or self.source_name,
            verified_from_source=(
                verified_from_source
                or (self.source_name if verification_status in {"verified", "partially_verified"} else "")
            ),
            discovery_sources=discovery_sources or [self.source_name],
            source_confidence_score=source_confidence_score,
            community_sponsorship_signal=community_sponsorship_signal,
            community_markers=community_markers or [],
            company_normalized=normalized_token(actual_company),
            title_normalized=normalize_title(title),
            ats_requisition_id=ats_requisition_id or (str(external_id) if external_id else ""),
            canonical_official_url=canonicalize_url(official_url or ""),
            discovery_status=discovery_status,
            official_status=official_status,
            verification_status=verification_status,
            verification_method=verification_method,
            status_reason=status_reason,
            last_verified_at=parse_datetime(last_verified_at),
            posted_at=official_posted or source_posted_at,
            official_posted_at=official_posted,
            source_posted_at=source_posted_at,
            expires_at=parse_datetime(expires_at),
            is_active=is_active,
            raw_data_hash=raw_hash(raw),
            raw_data=json.loads(json.dumps(raw, default=str)),
        )
