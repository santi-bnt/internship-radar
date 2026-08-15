from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.dedupe import value
from app.services.eligibility import determine_remote_scope
from app.services.normalization import normalize_country, normalized_token


TARGET_COUNTRIES = {"Mexico", "United States", "Canada"}

MAJOR_COMPANIES = {
    "amazon",
    "microsoft",
    "google",
    "apple",
    "nvidia",
    "amd",
    "intel",
    "qualcomm",
    "nxp",
    "nxp semiconductors",
    "texas instruments",
    "cisco",
    "ibm",
    "oracle",
    "meta",
    "tesla",
    "rivian",
    "spacex",
    "garmin",
    "bosch",
    "honeywell",
    "siemens",
    "rockwell automation",
    "ge vernova",
    "nokia",
    "ericsson",
    "ciena",
    "cirrus logic",
    "microchip",
    "microchip technology",
    "analog devices",
    "arm",
    "samsung semiconductor",
    "sk hynix",
    "marvell",
    "marvell technology",
    "broadcom",
    "infineon",
    "stmicroelectronics",
    "synopsys",
    "cadence",
    "general motors",
    "ford",
    "ford motor company",
    "john deere",
    "schneider electric",
    "continental",
    "ametek",
}

AREA_KEYWORDS = {
    "FPGA / RTL / ASIC": ("fpga", "rtl", "verilog", "systemverilog", "asic", "vlsi", "digital design"),
    "Firmware / Embedded": (
        "firmware",
        "embedded",
        "microcontroller",
        "mcu",
        "rtos",
        "freertos",
        "device driver",
        "embedded linux",
        "esp32",
        "raspberry pi",
    ),
    "Robotics": ("robotics", "robot", "ros", "autonomy", "mechatronics"),
    "Hardware Test / Validation": ("hardware test", "validation", "verification", "test engineer"),
    "Electrical Engineering": ("electrical", "electronics", "pcb", "circuit", "semiconductor"),
    "Controls / Automation": ("controls", "control systems", "automation", "plc", "pid"),
    "Computer Vision": ("computer vision", "opencv", "image processing", "perception"),
    "Software / SDE": ("software", "sde", "backend", "developer", "programming"),
}


@dataclass(frozen=True)
class RemoteDetails:
    remote_type: str
    remote_regions: list[str]
    remote_countries_allowed: list[str]
    remote_from_mexico_allowed: bool
    remote_scope: str = "UNKNOWN"
    can_work_from_mexico: str = "UNKNOWN"


def classify_remote(location: str, description: str = "", explicit_type: str = "") -> RemoteDetails:
    text = normalized_token(f"{location} {explicit_type} {description}")
    if "hybrid" in text:
        return RemoteDetails("Hybrid", [], [], False, "NOT_REMOTE", "NO")
    if not any(term in text for term in ("remote", "work from anywhere", "work from home", "distributed")):
        mexico = normalize_country(location) == "Mexico" or "mexico" in text
        return RemoteDetails("On-site", [], [], False, "NOT_REMOTE", "YES" if mexico else "NO")

    scope, countries, mexico_status = determine_remote_scope(
        {
            "location": location,
            "country": "",
            "remote_type": explicit_type or "Remote",
            "description": description,
        }
    )

    us_only = any(
        phrase in text
        for phrase in (
            "us remote only",
            "u s remote only",
            "remote in the united states only",
            "must be located in the united states",
            "remote within united states",
            "united states remote",
        )
    )
    canada_only = any(
        phrase in text
        for phrase in ("canada remote", "remote in canada only", "remote within canada", "must be located in canada")
    )
    state_only = re.search(
        r"(must reside|must be located|remote within) (in )?(california|texas|washington|ontario|quebec|[a-z]+ state|[a-z]+ province)",
        text,
    )
    mexico_allowed = any(
        phrase in text
        for phrase in (
            "remote worldwide",
            "work from anywhere",
            "worldwide remote",
            "remote in north america",
            "eligible to work remotely from mexico",
            "remote from mexico",
            "contractor from latin america",
            "latin america remote",
            "global remote",
        )
    )
    if us_only:
        return RemoteDetails("Remote - United States only", ["United States"], ["United States"], False, "US_ONLY", "NO")
    if canada_only:
        return RemoteDetails("Remote - Canada only", ["Canada"], ["Canada"], False, "COUNTRY_RESTRICTED", "NO")
    if state_only:
        region = state_only.group(3).title()
        country = "Canada" if region.lower() in {"ontario", "quebec"} or "province" in region.lower() else "United States"
        return RemoteDetails(f"Remote - {region} only", [region], [country], False, "COUNTRY_RESTRICTED", "NO")
    if mexico_allowed:
        if not countries:
            countries = ["Mexico", "United States", "Canada"] if "north america" in text else ["Worldwide"]
        return RemoteDetails("Remote from Mexico", [], countries, True, scope, "YES")
    if scope in {"MEXICO", "LATAM", "GLOBAL", "COUNTRY_LIST"} and mexico_status == "YES":
        return RemoteDetails("Remote from Mexico", [], countries, True, scope, mexico_status)
    if scope in {"US_ONLY", "COUNTRY_RESTRICTED"}:
        return RemoteDetails("Remote - Country restricted", [], countries, False, scope, mexico_status)
    return RemoteDetails("Remote - Location Restrictions Unknown", [], [], False, "UNKNOWN", "UNKNOWN")


def classify_area(job: Any) -> str:
    text = normalized_token(
        " ".join(
            [
                value(job, "title", "") or "",
                value(job, "description", "") or "",
                value(job, "requirements", "") or "",
                " ".join(value(job, "skills", []) or []),
            ]
        )
    )
    for area, keywords in AREA_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return area
    return "Unknown"


def classify_company_importance(company: str) -> str:
    normalized = normalized_token(company)
    if normalized in MAJOR_COMPANIES:
        return "Major company"
    if normalized:
        return "Unknown"
    return "Unknown"


def location_allowed(job: Any, profile: Any) -> tuple[bool, str]:
    selected = {
        normalize_country(country)
        for country in (value(profile, "countries_to_search", None) or ["Mexico", "United States", "Canada"])
    }
    country = normalize_country(value(job, "country", "Unknown"))
    remote_type = value(job, "remote_type", "Unknown") or "Unknown"
    is_remote = remote_type.startswith("Remote")
    is_hybrid = remote_type == "Hybrid"
    is_onsite = remote_type == "On-site"
    remote_from_mexico = bool(value(job, "remote_from_mexico_allowed", False))

    if bool(value(profile, "only_remote", False)) and not is_remote:
        return False, "The profile is configured for remote-only opportunities."
    if is_remote and not bool(value(profile, "include_remote", True)):
        return False, "Remote opportunities are disabled in the profile."
    if is_hybrid and not bool(value(profile, "include_hybrid", True)):
        return False, "Hybrid opportunities are disabled in the profile."
    if is_onsite and not bool(value(profile, "include_onsite", True)):
        return False, "On-site opportunities are disabled in the profile."
    if bool(value(profile, "remote_from_mexico_only", False)) and is_remote and not remote_from_mexico:
        return False, "The remote role is not confirmed as workable from Mexico."

    if country in selected:
        return True, "The role is in a selected country."
    if is_remote and remote_from_mexico:
        return True, "The role is outside selected countries but explicitly allows work from Mexico."
    if country not in TARGET_COUNTRIES:
        return False, "On-site, hybrid, or restricted remote roles outside Mexico, the U.S., and Canada are ignored."
    return False, "The role country is not selected."


def detect_recycled_posting(job: Any, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    text = normalized_token(f"{value(job, 'title', '')} {value(job, 'description', '')}")
    expired_seasons = [f"{season} {year}" for year in range(2020, now.year) for season in ("summer", "fall", "spring", "winter")]
    if any(season in text for season in expired_seasons):
        return True, "The listing references a past internship season."
    expires_at = value(job, "expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            return True, "The application deadline has passed."
    first_seen = value(job, "first_seen_at")
    source_posted = value(job, "source_posted_at") or value(job, "posted_at")
    if isinstance(first_seen, datetime) and isinstance(source_posted, datetime):
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if source_posted.tzinfo is None:
            source_posted = source_posted.replace(tzinfo=timezone.utc)
        if first_seen - source_posted > timedelta(days=120):
            return True, "The source date is much older than the discovery date."
    return False, ""


def urgency_label(job: Any, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    expires_at = value(job, "expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        remaining = expires_at - now
        if remaining.total_seconds() <= 0:
            return "Closed"
        if expires_at.date() == now.date():
            return "Closing Today"
        if remaining <= timedelta(hours=72):
            return "Urgent"
        if remaining <= timedelta(days=7):
            return "Apply Soon"
    first_seen = value(job, "first_seen_at")
    if isinstance(first_seen, str):
        try:
            first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        except ValueError:
            first_seen = None
    if isinstance(first_seen, datetime):
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        age = now - first_seen
        if age <= timedelta(hours=24):
            return "New"
        if age <= timedelta(days=7):
            return "Recent"
    posted = value(job, "posted_at")
    last_verified = value(job, "last_verified_at")
    if isinstance(posted, datetime):
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if now - posted > timedelta(days=30):
            if not last_verified or now - last_verified.replace(tzinfo=last_verified.tzinfo or timezone.utc) > timedelta(days=7):
                return "Old Listing"
    return "Recent"


def qualifies_priority_alert(
    job: Any,
    profile: Any,
    analysis: Any,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    first_seen = value(job, "first_seen_at")
    if isinstance(first_seen, str):
        try:
            first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        except ValueError:
            first_seen = None
    if isinstance(first_seen, datetime) and first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    is_recent = bool(first_seen and first_seen >= now - timedelta(days=7)) or float(
        value(analysis, "freshness_score", 0)
    ) >= 75
    normal_threshold = float(value(analysis, "overall_score", 0)) >= float(
        value(profile, "priority_minimum_score", 80)
    )
    major_threshold = (
        bool(value(profile, "alert_for_major_companies", True))
        and value(job, "company_importance", "Unknown") == "Major company"
        and float(value(analysis, "overall_score", 0))
        >= float(value(profile, "major_company_minimum_score", 70))
    )
    internship_area = value(job, "area", "Unknown") in AREA_KEYWORDS
    return bool(
        value(profile, "priority_alerts", True)
        and value(job, "discovery_status", "discovered") != "demo"
        and value(job, "status", "active") in {"active", "saved"}
        and value(job, "is_active", True)
        and value(job, "official_status") == "open"
        and value(job, "verification_status") == "verified"
        and not (value(analysis, "blocker_reasons", []) or [])
        and value(analysis, "eligibility_status", "ELIGIBLE") in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
        and float(value(analysis, "level_score", 0)) >= 80
        and float(value(analysis, "freshness_score", 0)) >= 50
        and internship_area
        and is_recent
        and (normal_threshold or major_threshold)
    )
