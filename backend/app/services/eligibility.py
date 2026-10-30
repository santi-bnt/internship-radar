from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.dedupe import value
from app.services.normalization import clean_text, normalize_country, normalized_token


ELIGIBILITY_STATES = {
    "ELIGIBLE",
    "LIKELY_ELIGIBLE",
    "UNKNOWN",
    "LIKELY_INELIGIBLE",
    "NOT_ELIGIBLE",
}
REMOTE_SCOPES = {
    "GLOBAL",
    "LATAM",
    "MEXICO",
    "COUNTRY_LIST",
    "US_ONLY",
    "COUNTRY_RESTRICTED",
    "UNKNOWN",
    "NOT_REMOTE",
}
SPONSORSHIP_STATUSES = {"AVAILABLE", "NOT_AVAILABLE", "NOT_REQUIRED", "UNKNOWN"}

REMOTE_DISCOVERY_ALLOCATION = {
    "mexico": 0.40,
    "eligible_remote": 0.30,
    "international_target_companies": 0.30,
}
REMOTE_DISCOVERY_QUERIES = (
    "remote software engineer intern",
    "remote software internship Mexico",
    "remote embedded software intern",
    "remote C++ intern Mexico",
    "remote Python intern Mexico",
    "remote LATAM software engineering intern",
    "remote robotics intern",
    "remote AI intern LATAM",
    "global remote internship software",
    "Mexico remote software internship",
)


NOT_AVAILABLE_PATTERNS = (
    r"\bno (?:visa |immigration |employment )?sponsorship\b",
    r"\bnot eligible for (?:visa |immigration |employment )?sponsorship\b",
    r"\b(?:we|company|employer) (?:are|is) unable to sponsor\b",
    r"\b(?:cannot|can not|will not|won t) sponsor\b",
    r"\bwill not (?:offer|provide) (?:work authorization |visa |immigration |employment )?sponsorship\b",
    r"\bno sponsorship (?:now|currently)(?: or in the future)?\b",
    r"\bwithout (?:current or future )?sponsorship\b",
    r"\bmust (?:have|possess) (?:unrestricted|permanent) (?:u s )?work authorization\b",
    r"\bapplicants? must have unrestricted work authorization\b",
    r"\bmust (?:be|already be) (?:legally )?authorized to work in (?:the )?(?:u s|united states)\b",
    r"\bmust be currently eligible to work in (?:the )?(?:u s|united states)\b",
    r"\b(?:u s|united states) work authorization (?:is )?required\b",
)
AVAILABLE_PATTERNS = (
    r"\b(?:visa |immigration |employment )?sponsorship (?:is )?(?:available|provided|offered)\b",
    r"\bwill sponsor (?:qualified|eligible) candidates?\b",
    r"\bwe (?:offer|provide) (?:visa |immigration |employment )?sponsorship\b",
    r"\bsponsorship available\b",
)
NOT_REQUIRED_PATTERNS = (
    r"\b(?:visa |immigration |employment )?sponsorship (?:is )?not required\b",
    r"\bno (?:u s |united states )?work authorization required\b",
)
US_AUTHORIZATION_PATTERNS = (
    r"\bmust (?:be|already be) (?:legally )?authorized to work in (?:the )?(?:u s|united states)\b",
    r"\bmust be currently eligible to work in (?:the )?(?:u s|united states)\b",
    r"\b(?:u s|united states) work authorization (?:is )?required\b",
    r"\bunrestricted (?:u s )?work authorization\b",
)


@dataclass(frozen=True)
class JobEligibilitySignals:
    remote_scope: str
    physical_work_country_required: str
    can_work_from_mexico: str
    job_requires_work_in_us: bool
    sponsorship_status: str
    sponsorship_evidence_text: str
    sponsorship_source_url: str
    sponsorship_last_verified_at: datetime | None
    remote_countries_allowed: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EligibilityDecision:
    state: str
    score: float
    reasons: list[str]
    risks: list[str]


def _posting_text(job: Any) -> str:
    return " ".join(
        clean_text(value(job, field, "") or "")
        for field in (
            "location",
            "country",
            "remote_type",
            "description",
            "requirements",
            "preferred_qualifications",
        )
    ).strip()


def _first_evidence(text: str, patterns: tuple[str, ...]) -> str:
    segments = [segment.strip() for segment in re.split(r"(?<=[.!?;])\s+|\n+", text) if segment.strip()]
    for pattern in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        for segment in segments:
            if compiled.search(normalized_token(segment)):
                return segment[:800]
    return ""


def extract_sponsorship(text: str) -> tuple[str, str]:
    normalized = normalized_token(text)
    for status, patterns in (
        ("NOT_AVAILABLE", NOT_AVAILABLE_PATTERNS),
        ("AVAILABLE", AVAILABLE_PATTERNS),
        ("NOT_REQUIRED", NOT_REQUIRED_PATTERNS),
    ):
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return status, _first_evidence(text, patterns)
    return "UNKNOWN", ""


def determine_remote_scope(job: Any) -> tuple[str, list[str], str]:
    configured_scope = clean_text(value(job, "remote_scope", "") or "").upper()
    if configured_scope in REMOTE_SCOPES - {"UNKNOWN"}:
        configured_countries = list(value(job, "remote_countries_allowed", []) or [])
        configured_mexico = clean_text(value(job, "can_work_from_mexico", "") or "").upper()
        if configured_mexico not in {"YES", "NO"}:
            configured_mexico = (
                "YES" if configured_scope in {"GLOBAL", "LATAM", "MEXICO"} else "NO"
            )
        return configured_scope, configured_countries, configured_mexico
    text = normalized_token(" ".join(
        clean_text(value(job, field, "") or "")
        for field in (
            "location", "remote_type", "description", "requirements",
            "preferred_qualifications",
        )
    ))
    remote_type = normalized_token(value(job, "remote_type", "") or "")
    is_remote = any(
        phrase in text
        for phrase in ("remote", "work from anywhere", "work from home", "distributed")
    ) or "remote" in remote_type
    if not is_remote or "hybrid" in text:
        country = normalize_country(value(job, "country", ""))
        return "NOT_REMOTE", [], "YES" if country == "Mexico" else "NO"

    if any(
        phrase in text
        for phrase in (
            "remote united states",
            "united states remote",
            "remote anywhere in the u s",
            "remote in the u s",
            "remote within the united states",
            "us remote only",
            "u s remote only",
            "candidates must reside in the united states",
            "must be located in the united states",
        )
    ):
        return "US_ONLY", ["United States"], "NO"
    if any(phrase in text for phrase in ("remote canada", "canada remote", "remote in canada")):
        return "COUNTRY_RESTRICTED", ["Canada"], "NO"
    if any(
        phrase in text
        for phrase in (
            "remote mexico",
            "mexico remote",
            "remote from mexico",
            "remotely from mexico",
            "eligible to work remotely from mexico",
        )
    ):
        return "MEXICO", ["Mexico"], "YES"
    if any(
        phrase in text
        for phrase in (
            "remote latam",
            "latam remote",
            "remote latin america",
            "latin america remote",
            "remote across latin america",
            "candidates in latin america",
        )
    ):
        excluded = any(phrase in text for phrase in ("except mexico", "excluding mexico", "mexico excluded"))
        return "LATAM", ["Latin America"], "NO" if excluded else "YES"
    if any(
        phrase in text
        for phrase in (
            "remote worldwide",
            "worldwide remote",
            "global remote",
            "remote globally",
            "work from anywhere",
            "anywhere in the world",
        )
    ):
        excluded = any(phrase in text for phrase in ("except mexico", "excluding mexico", "mexico excluded"))
        return "GLOBAL", ["Worldwide"], "NO" if excluded else "YES"

    allowed = [
        country
        for country in ("Mexico", "United States", "Canada")
        if normalized_token(country) in text
    ]
    restriction_language = any(
        phrase in text
        for phrase in ("eligible countries", "approved countries", "must reside", "must be located", "country list")
    )
    if len(allowed) >= 2 and restriction_language:
        return "COUNTRY_LIST", allowed, "YES" if "Mexico" in allowed else "NO"
    if restriction_language and allowed:
        return "COUNTRY_RESTRICTED", allowed, "YES" if "Mexico" in allowed else "NO"
    return "UNKNOWN", [], "UNKNOWN"


def extract_job_eligibility_signals(job: Any) -> JobEligibilitySignals:
    posting = _posting_text(job)
    normalized = normalized_token(posting)
    scope, allowed_countries, mexico_status = determine_remote_scope(job)
    listed_country = normalize_country(value(job, "country", ""))

    if scope in {"MEXICO", "LATAM", "GLOBAL"} or (
        scope == "COUNTRY_LIST" and "Mexico" in allowed_countries
    ):
        physical_country = "Mexico"
    elif scope == "US_ONLY":
        physical_country = "United States"
    elif scope in {"COUNTRY_LIST", "COUNTRY_RESTRICTED"}:
        physical_country = allowed_countries[0] if len(allowed_countries) == 1 else "Country list"
    elif scope == "UNKNOWN":
        physical_country = "Unknown"
    else:
        physical_country = listed_country

    sponsorship_status, evidence = extract_sponsorship(posting)
    explicit_us_auth = any(re.search(pattern, normalized) for pattern in US_AUTHORIZATION_PATTERNS)
    requires_us = physical_country == "United States" or scope == "US_ONLY" or explicit_us_auth
    source_url = clean_text(
        value(job, "official_apply_url", "")
        or value(job, "apply_url", "")
        or value(job, "source_url", "")
        or ""
    )
    verified_at = value(job, "last_verified_at")
    if isinstance(verified_at, str):
        try:
            verified_at = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
        except ValueError:
            verified_at = None
    if evidence and value(job, "verification_status") == "verified" and not verified_at:
        verified_at = datetime.now(timezone.utc)
    if not evidence:
        source_url = ""
        verified_at = None

    return JobEligibilitySignals(
        remote_scope=scope,
        physical_work_country_required=physical_country,
        can_work_from_mexico=mexico_status,
        job_requires_work_in_us=requires_us,
        sponsorship_status=sponsorship_status,
        sponsorship_evidence_text=evidence,
        sponsorship_source_url=source_url,
        sponsorship_last_verified_at=verified_at,
        remote_countries_allowed=allowed_countries,
    )


def profile_work_authorized_countries(profile: Any) -> set[str]:
    configured = value(profile, "work_authorized_countries", None)
    if configured:
        return {normalize_country(country) for country in configured}
    legacy = value(profile, "work_authorizations", {}) or {}
    return {
        normalize_country(country)
        for country, status in legacy.items()
        if any(term in normalized_token(str(status)) for term in ("citizen", "authorized", "permanent resident"))
        and "no current" not in normalized_token(str(status))
    }


def evaluate_work_eligibility(
    signals: JobEligibilitySignals,
    profile: Any,
) -> EligibilityDecision:
    authorized = profile_work_authorized_countries(profile)
    us_authorized = bool(value(profile, "us_work_authorized", "United States" in authorized))
    needs_us_sponsorship = bool(value(profile, "requires_us_employment_sponsorship", not us_authorized))
    physical_country = signals.physical_work_country_required

    if signals.remote_scope == "UNKNOWN":
        return EligibilityDecision(
            "UNKNOWN",
            55,
            [],
            ["Remote location restrictions are unknown. Do not assume Mexico is permitted."],
        )
    if signals.can_work_from_mexico == "NO" and signals.remote_scope != "NOT_REMOTE":
        if signals.job_requires_work_in_us and us_authorized:
            return EligibilityDecision(
                "ELIGIBLE", 100,
                ["The role requires U.S. work authorization and the profile confirms it."], [],
            )
        if signals.sponsorship_status == "AVAILABLE":
            return EligibilityDecision(
                "LIKELY_ELIGIBLE", 85,
                ["The restricted work location may be feasible because the employer explicitly offers sponsorship."],
                ["Confirm the sponsorship process before applying."],
            )
        if signals.sponsorship_status == "NOT_AVAILABLE":
            reason = (
                "U.S. work authorization required and employer indicates sponsorship is unavailable."
                if signals.job_requires_work_in_us
                else "The posting excludes Mexico and does not offer sponsorship for the required country."
            )
            reasons = [reason]
            if signals.job_requires_work_in_us:
                reasons.extend([
                    "The position requires work in the United States.",
                    "The user does not currently have U.S. work authorization.",
                    "Technical match cannot override this eligibility requirement.",
                ])
            return EligibilityDecision("NOT_ELIGIBLE", 0, reasons, [])
        if signals.sponsorship_status == "AVAILABLE":
            return EligibilityDecision(
                "LIKELY_ELIGIBLE", 85,
                ["The role excludes Mexico, but sponsorship is explicitly available for the required location."],
                ["Confirm the relocation and country-specific work permit process."],
            )
        return EligibilityDecision(
            "LIKELY_INELIGIBLE", 25, [],
            ["The posting explicitly excludes working from Mexico and no alternative work authorization is confirmed."],
        )

    if signals.job_requires_work_in_us:
        if us_authorized:
            return EligibilityDecision(
                "ELIGIBLE", 100,
                ["The profile confirms current U.S. work authorization."], [],
            )
        if needs_us_sponsorship and signals.sponsorship_status == "NOT_AVAILABLE":
            return EligibilityDecision(
                "NOT_ELIGIBLE",
                0,
                [
                    "U.S. work authorization required and employer indicates sponsorship is unavailable.",
                    "The position requires work in the United States.",
                    "The user does not currently have U.S. work authorization.",
                    "Technical match cannot override this eligibility requirement.",
                ],
                [],
            )
        if needs_us_sponsorship and signals.sponsorship_status == "AVAILABLE":
            return EligibilityDecision(
                "LIKELY_ELIGIBLE",
                85,
                ["The employer explicitly indicates sponsorship is available."],
                ["Confirm that internship sponsorship covers this candidate and start date."],
            )
        return EligibilityDecision(
            "UNKNOWN",
            55,
            [],
            ["U.S. work authorization is required, but sponsorship information is unavailable."],
        )

    if physical_country == "Mexico" or signals.can_work_from_mexico == "YES":
        if "Mexico" in authorized:
            reason = (
                "Remote role explicitly allows candidates located in Mexico."
                if signals.remote_scope != "NOT_REMOTE"
                else "The required work location is Mexico and the profile confirms work authorization."
            )
            return EligibilityDecision(
                "ELIGIBLE", 100,
                [reason, "No U.S. employment authorization is required for the listed work location."], [],
            )
        return EligibilityDecision(
            "LIKELY_INELIGIBLE", 25, [],
            ["The role requires work from Mexico, but Mexico work authorization is not confirmed."],
        )

    if physical_country in authorized:
        return EligibilityDecision(
            "ELIGIBLE", 100,
            [f"The profile confirms work authorization for {physical_country}."], [],
        )
    if physical_country in {"Unknown", "Country list", "Remote", ""}:
        return EligibilityDecision(
            "UNKNOWN", 55, [],
            ["The physical hiring country and required work authorization are not stated clearly."],
        )
    if signals.sponsorship_status == "AVAILABLE":
        return EligibilityDecision(
            "LIKELY_ELIGIBLE", 85,
            [f"Sponsorship is offered for a role requiring work in {physical_country}."],
            ["Confirm country-specific work permit eligibility."],
        )
    if signals.sponsorship_status == "NOT_AVAILABLE":
        return EligibilityDecision(
            "NOT_ELIGIBLE", 0,
            [f"The role requires work authorization in {physical_country}, which is not held, and sponsorship is unavailable."],
            [],
        )
    return EligibilityDecision(
        "UNKNOWN", 55, [],
        [f"Work authorization or sponsorship for {physical_country} is not stated."],
    )


def remote_eligibility_bonus(signals: JobEligibilitySignals, state: str, relocation_required: bool) -> float:
    if state not in {"ELIGIBLE", "LIKELY_ELIGIBLE"}:
        return 0.0
    if signals.remote_scope not in {"MEXICO", "LATAM", "GLOBAL"}:
        return 0.0
    if signals.can_work_from_mexico != "YES":
        return 0.0
    return 15.0 + 10.0 + (0.0 if relocation_required else 8.0)


def apply_job_eligibility_signals(job: Any) -> JobEligibilitySignals:
    signals = extract_job_eligibility_signals(job)
    for key, item in signals.to_dict().items():
        if key == "remote_countries_allowed" and value(job, key, None):
            continue
        if hasattr(job, key):
            setattr(job, key, item)
    return signals


def discovery_search_plan() -> dict[str, Any]:
    """Return the deterministic allocation used by every general discovery cycle."""
    return {
        "allocation": dict(REMOTE_DISCOVERY_ALLOCATION),
        "remote_queries": list(REMOTE_DISCOVERY_QUERIES),
    }
