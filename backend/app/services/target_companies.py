from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from app.services.normalization import normalized_token


ROLE_CATEGORIES = [
    "Software Engineering",
    "Backend / Data",
    "Cloud / Infrastructure",
    "Embedded / Firmware",
    "Systems Software",
    "FPGA / Digital Design",
    "AI / API Integration",
    "Robotics / Controls",
    "Developer Tools",
    "Maps / Routing",
]
DEFAULT_LOCATIONS = [
    "Mexico", "Guadalajara", "Monterrey", "Mexico City", "Remote Mexico",
    "United States", "Canada", "Remote", "Hybrid",
]
HIGH_PRIORITY = {
    "Oracle", "Amazon", "Microsoft", "Google", "NVIDIA", "Intel", "AMD",
    "Qualcomm", "NXP Semiconductors", "Synopsys", "Cadence", "Arm", "Rivian", "Zipline",
}
TARGET_COMPANY_SEED = {
    "Cloud and data": [
        "Oracle", "Amazon", "Microsoft", "Google", "IBM", "Salesforce", "ServiceNow",
        "Snowflake", "Databricks", "MongoDB", "Cloudflare",
    ],
    "Semiconductors": [
        "NVIDIA", "Intel", "AMD", "Qualcomm", "NXP Semiconductors", "Texas Instruments",
        "Synopsys", "Cadence", "Arm", "Micron", "Western Digital", "Marvell", "Broadcom",
    ],
    "Robotics and automotive": [
        "Rivian", "Volkswagen Group Technologies", "Zipline", "Tesla", "Bosch",
        "Honeywell", "Garmin", "Caterpillar", "John Deere", "Siemens", "ABB",
        "Rockwell Automation",
    ],
}
ALIASES = {
    "Oracle": [
        "Oracle", "Oracle Corporation", "Oracle Cloud", "Oracle Cloud Infrastructure",
        "OCI", "Oracle Labs", "NetSuite",
    ],
    "Amazon": ["Amazon", "Amazon Web Services", "AWS"],
    "NXP Semiconductors": ["NXP Semiconductors", "NXP"],
    "Arm": ["Arm", "Arm Holdings"],
    "Volkswagen Group Technologies": ["Volkswagen Group Technologies", "Volkswagen", "VW"],
}
VERIFIED_CAREER_URLS = {
    "Oracle": ["https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/jobsearch"],
    "Amazon": ["https://www.amazon.jobs/en/search?base_query=intern"],
    "Google": ["https://www.google.com/about/careers/applications/jobs/results/?q=intern"],
    "NVIDIA": ["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"],
    "NXP Semiconductors": ["https://nxp.wd3.myworkdayjobs.com/careers"],
    "AMD": ["https://careers.amd.com/careers-home/jobs?keywords=intern"],
    "Qualcomm": ["https://careers.qualcomm.com/careers?query=intern"],
    "Arm": ["https://careers.arm.com/en/search-jobs?keywords=intern"],
    "Synopsys": ["https://careers.synopsys.com/search-jobs?k=intern"],
    "Cadence": ["https://cadence.wd1.myworkdayjobs.com/External_Careers"],
    "Intel": ["https://intel.wd1.myworkdayjobs.com/External"],
    "Micron": ["https://micron.wd1.myworkdayjobs.com/External"],
    "Western Digital": ["https://jobs.smartrecruiters.com/WesternDigital"],
    "Marvell": ["https://marvell.wd1.myworkdayjobs.com/MarvellCareers"],
    "Broadcom": ["https://broadcom.wd1.myworkdayjobs.com/External_Career"],
    "Databricks": ["https://boards.greenhouse.io/databricks"],
    "MongoDB": ["https://boards.greenhouse.io/mongodb"],
    "Cloudflare": ["https://boards.greenhouse.io/cloudflare"],
    "Bosch": ["https://jobs.smartrecruiters.com/BoschGroup"],
    "Rockwell Automation": [
        "https://rockwellautomation.wd1.myworkdayjobs.com/External_Rockwell_Automation"
    ],
    "Zipline": ["https://boards.greenhouse.io/flyzipline"],
}


def seed_records() -> list[dict[str, Any]]:
    records = []
    for category, names in TARGET_COMPANY_SEED.items():
        for name in names:
            records.append(
                {
                    "company_name": name,
                    "aliases": ALIASES.get(name, [name]),
                    "careers_domains": VERIFIED_CAREER_URLS.get(name, []),
                    "category": category,
                    "priority": "high" if name in HIGH_PRIORITY else "medium",
                    "enabled": True,
                    "custom": False,
                    "preferred_locations": list(DEFAULT_LOCATIONS),
                    "preferred_role_categories": list(ROLE_CATEGORIES),
                }
            )
    return records


def normalize_company_name(name: str, companies: Iterable[Any]) -> tuple[str, Any | None]:
    candidate = normalized_token(name)
    best = None
    for company in companies:
        aliases = list(getattr(company, "aliases", []) or []) + [company.company_name]
        if any(normalized_token(alias) == candidate for alias in aliases):
            best = company
            break
    return (best.company_name, best) if best else (name.strip(), None)


def canonicalize_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def search_is_due(company: Any, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    last_checked = company.last_checked_at
    if last_checked is None:
        return True
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    interval = {"high": 1, "medium": 2, "low": 7}.get(company.priority, 7)
    return current - last_checked >= timedelta(days=interval)


def priority_bonus(priority: str, official: bool, verified: bool) -> float:
    company_points = {"high": 12.0, "medium": 7.0, "low": 3.0}.get(priority, 0.0)
    return company_points + (8.0 if official else 0.0) + (8.0 if verified else 0.0)
