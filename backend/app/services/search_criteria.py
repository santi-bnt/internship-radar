from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


OFFICIAL_REGISTRY_TYPES = {"OFFICIAL_COMPANY", "OFFICIAL_ATS"}
COMMUNITY_REGISTRY_TYPES = {"COMMUNITY_REPO", "AGGREGATOR"}

ROLE_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "SOFTWARE_ENGINEERING": ("software", "developer", "sde", "programming"),
    "EMBEDDED_FIRMWARE": ("embedded", "firmware", "rtos", "microcontroller"),
    "ROBOTICS": ("robotics", "robot", "controls", "autonomy"),
    "AI_MACHINE_LEARNING": ("machine learning", "artificial intelligence", " ai ", "ml "),
    "COMPUTER_VISION": ("computer vision", "opencv", "perception", "imaging"),
    "BACKEND": ("backend", "back end", "server", "api"),
    "FULL_STACK": ("full stack", "fullstack", "web developer"),
    "FPGA_DIGITAL_DESIGN": ("fpga", "rtl", "verilog", "digital design", "asic"),
    "HARDWARE_VALIDATION": ("hardware validation", "hardware test", "silicon validation"),
    "ELECTRICAL_VALIDATION": ("electrical", "electronics", "validation", "test engineer"),
    "DATA_ALGORITHMS": ("data", "algorithm", "analytics"),
    "RESEARCH_ENGINEERING": (
        "research intern", "research internship", "student researcher",
        "research engineering", "research engineer", "industrial research",
    ),
    "OTHER": (),
}

ROLE_SEARCH_TERMS: dict[str, str] = {
    "SOFTWARE_ENGINEERING": "software engineering intern",
    "EMBEDDED_FIRMWARE": "embedded firmware intern",
    "ROBOTICS": "robotics intern",
    "AI_MACHINE_LEARNING": "machine learning intern",
    "COMPUTER_VISION": "computer vision intern",
    "BACKEND": "backend software intern",
    "FULL_STACK": "full stack intern",
    "FPGA_DIGITAL_DESIGN": "fpga digital design intern",
    "HARDWARE_VALIDATION": "hardware validation intern",
    "ELECTRICAL_VALIDATION": "electrical validation intern",
    "DATA_ALGORITHMS": "data algorithms intern",
    "RESEARCH_ENGINEERING": "research engineering intern",
}

GUADALAJARA_METRO_ALIASES = {
    "guadalajara", "zapopan", "tlaquepaque", "san pedro tlaquepaque",
    "tlajomulco", "tlajomulco de zuniga", "el salto", "jalisco",
    "guadalajara metropolitan area", "gdl", "guadalajara metro",
}


def is_guadalajara_metro(value: object) -> bool:
    normalized = normalized_token(value)
    return any(
        normalized == alias or f" {alias} " in f" {normalized} "
        for alias in GUADALAJARA_METRO_ALIASES
    )


def location_matches(job: object, requested: Iterable[str]) -> bool:
    job_location = " ".join(str(_job_value(job, field, "") or "") for field in ("location", "city", "region", "country"))
    for location in requested:
        if is_guadalajara_metro(location) and is_guadalajara_metro(job_location):
            return True
        if f" {normalized_token(location)} " in f" {normalized_token(job_location)} ":
            return True
    return False


def normalized_token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9+#]+", " ", text.casefold()).strip()


def _job_value(job: object, name: str, default: Any = "") -> Any:
    if isinstance(job, dict):
        return job.get(name, default)
    return getattr(job, name, default)


def _job_text(job: object) -> str:
    parts = (
        _job_value(job, "company"),
        _job_value(job, "title"),
        _job_value(job, "location"),
        _job_value(job, "country"),
        _job_value(job, "city"),
        _job_value(job, "region"),
        _job_value(job, "area"),
        _job_value(job, "description"),
        _job_value(job, "requirements"),
    )
    return f" {normalized_token(' '.join(str(part or '') for part in parts))} "


def _contains_company(candidate: str, requested: Iterable[str]) -> bool:
    normalized_candidate = normalized_token(candidate)
    return any(
        normalized_token(company) in normalized_candidate
        or normalized_candidate in normalized_token(company)
        for company in requested
        if normalized_token(company)
    )


def selected_company_names(criteria: dict[str, Any], targets: Iterable[object]) -> list[str]:
    names = list(criteria.get("companies") or [])
    if criteria.get("target_companies_only"):
        names.extend(str(getattr(target, "company_name", "")) for target in targets)
    return list(dict.fromkeys(name for name in names if name))


def select_sources_for_criteria(
    sources: Iterable[object],
    criteria: dict[str, Any] | None,
    targets: Iterable[object],
) -> list[object]:
    source_list = list(sources)
    if not criteria:
        return source_list
    source_mode = criteria.get("source_mode", "OFFICIAL_AND_COMMUNITY")
    companies = selected_company_names(criteria, targets)

    def allowed(source: object) -> bool:
        registry_type = str(getattr(source, "registry_type", "OTHER"))
        official = registry_type in OFFICIAL_REGISTRY_TYPES
        community = registry_type in COMMUNITY_REGISTRY_TYPES
        if source_mode == "OFFICIAL_ONLY" and not official:
            return False
        if source_mode == "OFFICIAL_AND_COMMUNITY" and not (official or community):
            return False
        if not companies:
            return True
        if community:
            return True
        return _contains_company(str(getattr(source, "company", "")), companies)

    selected = [source for source in source_list if allowed(source)]
    selected.sort(
        key=lambda source: (
            1 if companies and _contains_company(str(getattr(source, "company", "")), companies) else 0,
            1 if str(getattr(source, "registry_type", "")) in OFFICIAL_REGISTRY_TYPES else 0,
            int(getattr(source, "priority", 0) or 0),
        ),
        reverse=True,
    )
    return selected


def discovery_search_terms(criteria: dict[str, Any] | None) -> list[str]:
    if not criteria:
        return []
    role_terms = [
        ROLE_SEARCH_TERMS[category]
        for category in criteria.get("role_categories") or []
        if category in ROLE_SEARCH_TERMS
    ]
    role_terms.extend(
        f"{keyword} intern" for keyword in criteria.get("include_keywords") or []
    )
    if not role_terms:
        role_terms.append("intern")
    locations = [
        *(criteria.get("cities") or []),
        *(criteria.get("states") or []),
        *(criteria.get("countries") or []),
    ]
    terms = list(role_terms)
    if locations:
        terms.extend(f"{term} {location}" for term in role_terms[:3] for location in locations[:2])
    if "REMOTE" in set(criteria.get("work_models") or []):
        remote_labels = {
            "MEXICO": "remote Mexico",
            "LATAM": "remote LATAM",
            "GLOBAL": "global remote",
            "US_ONLY": "remote United States",
            "UNKNOWN": "remote",
        }
        terms.extend(
            f"{term} {remote_labels[scope]}"
            for term in role_terms[:2]
            for scope in (criteria.get("remote_scopes") or [])
            if scope in remote_labels
        )
    student_variants = ("intern", "student", "co-op", "trainee", "early career")
    expanded = [*terms]
    for term in role_terms[:4]:
        base = re.sub(r"\b(intern|internship|student|co-op|trainee|early career)\b", "", term).strip()
        expanded.extend(f"{base} {student}" for student in student_variants if base)
    return list(dict.fromkeys(term.strip() for term in expanded if term.strip()))[:16]


def _posted_datetime(job: object) -> datetime | None:
    for field in ("official_posted_at", "source_posted_at", "posted_at", "first_seen_at"):
        value = _job_value(job, field, None)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def matches_discovery_criteria(
    job: object,
    criteria: dict[str, Any] | None,
    target_company_names: Iterable[str] = (),
    *,
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    if not criteria:
        return True, {}
    text = _job_text(job)
    requested_companies = list(criteria.get("companies") or [])
    if requested_companies and not _contains_company(
        str(_job_value(job, "company")), requested_companies
    ):
        return False, {"company": False}
    if criteria.get("target_companies_only") and not _contains_company(
        str(_job_value(job, "company")), target_company_names
    ):
        return False, {"target_company": False}

    work_models = set(criteria.get("work_models") or ["ANY"])
    remote_type = normalized_token(_job_value(job, "remote_type"))
    is_remote = remote_type.startswith("remote")
    is_hybrid = "hybrid" in remote_type
    work_model = "REMOTE" if is_remote else "HYBRID" if is_hybrid else "ON_SITE"
    if "ANY" not in work_models and work_model not in work_models:
        return False, {"work_model": work_model}
    if is_remote and "REMOTE" in work_models:
        selected_scopes = set(criteria.get("remote_scopes") or [])
        job_scope = str(_job_value(job, "remote_scope", "UNKNOWN") or "UNKNOWN").upper()
        scope_matches = job_scope in selected_scopes
        if job_scope == "COUNTRY_LIST" and "MEXICO" in selected_scopes:
            allowed_countries = {
                normalized_token(country)
                for country in (_job_value(job, "remote_countries_allowed", []) or [])
            }
            scope_matches = "mexico" in allowed_countries
        if selected_scopes and not scope_matches:
            return False, {"remote_scope": job_scope}

    locations = [
        *(criteria.get("countries") or []),
        *(criteria.get("states") or []),
        *(criteria.get("cities") or []),
    ]
    if locations and not location_matches(job, locations):
        return False, {"location": False}

    categories = criteria.get("role_categories") or []
    if categories and "OTHER" not in categories:
        category_match = any(
            any(f" {normalized_token(term)} " in text for term in ROLE_CATEGORY_TERMS.get(category, ()))
            for category in categories
        )
        if not category_match:
            return False, {"role_category": False}

    includes = criteria.get("include_keywords") or []
    if includes and not any(normalized_token(keyword) in text for keyword in includes):
        return False, {"include_keywords": False}
    excludes = criteria.get("exclude_keywords") or []
    if any(normalized_token(keyword) in text for keyword in excludes):
        return False, {"exclude_keywords": True}

    posted_within_days = criteria.get("posted_within_days")
    posted_at = _posted_datetime(job)
    if posted_within_days and posted_at:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=int(posted_within_days))
        if posted_at < cutoff:
            return False, {"posting_age": False}

    return True, {
        "company": str(_job_value(job, "company", "")),
        "work_model": work_model,
        "remote_scope": str(_job_value(job, "remote_scope", "UNKNOWN")),
        "matched_roles": categories,
        "matched_keywords": [
            keyword for keyword in includes if normalized_token(keyword) in text
        ],
    }


def matches_eligibility_criteria(job: object, criteria: dict[str, Any] | None) -> bool:
    if not criteria or not criteria.get("only_realistically_eligible", True):
        return True
    analysis = _job_value(job, "analysis", None)
    eligibility = str(_job_value(analysis, "eligibility_status", "UNKNOWN") or "UNKNOWN").upper()
    if eligibility in {"NOT_ELIGIBLE", "LIKELY_INELIGIBLE"}:
        return False
    if eligibility == "UNKNOWN" and not criteria.get("include_unknown_eligibility", True):
        return False
    return True


def search_result_sort_key(job: object) -> tuple[float, ...]:
    analysis = _job_value(job, "analysis", None)
    eligibility = str(_job_value(analysis, "eligibility_status", "UNKNOWN") or "UNKNOWN").upper()
    eligibility_rank = {
        "ELIGIBLE": 4,
        "LIKELY_ELIGIBLE": 3,
        "UNKNOWN": 2,
        "LIKELY_INELIGIBLE": 1,
        "NOT_ELIGIBLE": 0,
    }.get(eligibility, 2)
    mexico_compatible = 1 if (
        normalized_token(_job_value(job, "country")) == "mexico"
        or str(_job_value(job, "can_work_from_mexico", "UNKNOWN")) == "YES"
        or bool(_job_value(job, "remote_from_mexico_allowed", False))
    ) else 0
    official = 1 if (
        str(_job_value(job, "official_status")) == "open"
        and str(_job_value(job, "verification_status")) == "verified"
    ) else 0
    remote_type = normalized_token(_job_value(job, "remote_type"))
    eligible_remote = 1 if (
        remote_type.startswith("remote")
        and eligibility in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
        and mexico_compatible
    ) else 0
    return (
        float(eligibility_rank),
        float(_job_value(analysis, "technical_score", 0) or 0),
        float(_job_value(analysis, "freshness_score", 0) or 0),
        float(bool(_job_value(job, "is_target_company", False))),
        float(mexico_compatible),
        float(eligible_remote),
        float(official),
    )
