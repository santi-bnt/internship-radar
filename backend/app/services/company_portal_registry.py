from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse


PORTAL_TYPES = frozenset(
    {
        "WORKDAY",
        "GREENHOUSE",
        "MICROSOFT_CAREERS",
        "AMAZON_JOBS",
        "ORACLE_CAREERS",
        "LEVER",
        "ASHBY",
        "SMARTRECRUITERS",
        "GOOGLE_CAREERS",
        "GENERIC",
        "UNKNOWN",
    }
)

PORTAL_SUPPORT: dict[str, str] = {
    "WORKDAY": "SUPPORTED",
    "GREENHOUSE": "SUPPORTED",
    "MICROSOFT_CAREERS": "BETA",
    "AMAZON_JOBS": "BETA",
    "ORACLE_CAREERS": "BETA",
    "GENERIC": "BETA",
    "LEVER": "UNSUPPORTED",
    "ASHBY": "UNSUPPORTED",
    "SMARTRECRUITERS": "BETA",
    "GOOGLE_CAREERS": "UNSUPPORTED",
    "UNKNOWN": "UNSUPPORTED",
}

COMPANY_PORTAL_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "company_id": "intel",
        "company_name": "Intel",
        "known_domains": ["intel.wd1.myworkdayjobs.com", "jobs.intel.com"],
        "portal_type": "WORKDAY",
        "application_adapter": "WorkdayAdapter",
        "company_policy_key": "INTEL",
        "company_specific_rules": {"compliance_confirmation_required": True},
        "known_question_aliases": {
            "FORMER_INTEL_EMPLOYEE": ["previously employed by intel", "former intel employee"],
            "INTEL_IP_INTEREST": ["interest in intel intellectual property"],
        },
        "support_status": "SUPPORTED",
    },
    {
        "company_id": "ge_aerospace",
        "company_name": "GE Aerospace",
        "known_domains": ["geaerospace.wd5.myworkdayjobs.com", "careers.geaerospace.com"],
        "portal_type": "WORKDAY",
        "application_adapter": "WorkdayAdapter",
        "company_policy_key": "GE_AEROSPACE",
        "company_specific_rules": {"government_questions_confirmation_required": True},
        "known_question_aliases": {
            "FORMER_GE_EMPLOYEE": ["previously employed by ge", "former ge employee"],
            "GOVERNMENT_EMPLOYEE": ["currently or formerly employed by a government"],
            "FAMILY_GOVERNMENT_EMPLOYEE": ["family member employed by a government"],
        },
        "support_status": "SUPPORTED",
    },
    {
        "company_id": "zipline",
        "company_name": "Zipline",
        "known_domains": ["zipline.com", "www.zipline.com", "boards.greenhouse.io", "job-boards.greenhouse.io"],
        "portal_type": "GREENHOUSE",
        "application_adapter": "GreenhouseAdapter",
        "company_policy_key": "ZIPLINE",
        "company_specific_rules": {
            "canonical_company_only": True,
            "greenhouse_board_token": "flyzipline",
        },
        "known_question_aliases": {
            "JOB_DISCOVERY_SOURCE": [
                "tell us how you heard about zipline and this job",
                "how did you hear about zipline",
            ],
            "FULL_TIME_SUMMER_AVAILABILITY": [
                "available for a full time onsite internship this summer",
                "available may june through august september",
            ],
            "SPRING_SUMMER_COMBINED_AVAILABILITY": [
                "interested and available for a combined spring and summer internship",
                "available january to august or september",
            ],
            "US_WORK_AUTHORIZATION": [
                "legally authorized to work for any employer in the united states",
                "not currently authorized to work in the united states",
            ],
            "US_SPONSORSHIP_REQUIRED": [
                "require or in the future will require sponsorship to obtain work authorization",
            ],
        },
        "support_status": "SUPPORTED",
    },
    {
        "company_id": "duolingo",
        "company_name": "Duolingo",
        "known_domains": [
            "careers.duolingo.com",
            "boards.greenhouse.io",
            "job-boards.greenhouse.io",
        ],
        "portal_type": "GREENHOUSE",
        "application_adapter": "GreenhouseAdapter",
        "company_policy_key": "DUOLINGO",
        "company_specific_rules": {
            "canonical_company_only": True,
            "greenhouse_board_token": "duolingounirecruitment",
        },
        "known_question_aliases": {},
        "support_status": "SUPPORTED",
    },
    {
        "company_id": "roblox",
        "company_name": "Roblox",
        "known_domains": [
            "careers.roblox.com",
            "boards.greenhouse.io",
            "job-boards.greenhouse.io",
        ],
        "portal_type": "GREENHOUSE",
        "application_adapter": "GreenhouseAdapter",
        "company_policy_key": "ROBLOX",
        "company_specific_rules": {
            "canonical_company_only": True,
            "greenhouse_board_token": "roblox",
        },
        "known_question_aliases": {},
        "support_status": "SUPPORTED",
    },
    {
        "company_id": "microsoft",
        "company_name": "Microsoft",
        "known_domains": ["jobs.careers.microsoft.com", "careers.microsoft.com"],
        "portal_type": "MICROSOFT_CAREERS",
        "application_adapter": "MicrosoftCareersAdapter",
        "company_policy_key": "MICROSOFT",
        "company_specific_rules": {"preserve_saved_profile": True},
        "known_question_aliases": {},
        "support_status": "BETA",
    },
    {
        "company_id": "amazon_aws",
        "company_name": "Amazon / AWS",
        "known_domains": ["amazon.jobs", "www.amazon.jobs"],
        "portal_type": "AMAZON_JOBS",
        "application_adapter": "AmazonJobsAdapter",
        "company_policy_key": "AMAZON",
        "company_specific_rules": {"pause_on_assessment": True, "preserve_saved_profile": True},
        "known_question_aliases": {},
        "support_status": "BETA",
    },
    {
        "company_id": "oracle",
        "company_name": "Oracle",
        "known_domains": ["careers.oracle.com", "oraclecloud.com"],
        "portal_type": "ORACLE_CAREERS",
        "application_adapter": "OracleCareersAdapter",
        "company_policy_key": "ORACLE",
        "company_specific_rules": {"special_program_gate": True, "preserve_saved_profile": True},
        "known_question_aliases": {},
        "support_status": "BETA",
    },
)


def normalize_company_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    aliases = {
        "ge": "ge_aerospace",
        "general_electric": "ge_aerospace",
        "amazon": "amazon_aws",
        "aws": "amazon_aws",
        "amazon_web_services": "amazon_aws",
        "microsoft_corporation": "microsoft",
        "intel_corporation": "intel",
    }
    return aliases.get(normalized, normalized)


def company_policy(company: str) -> dict[str, Any]:
    company_id = normalize_company_id(company)
    for entry in COMPANY_PORTAL_REGISTRY:
        if entry["company_id"] == company_id:
            return dict(entry)
    return {
        "company_id": company_id or "unknown",
        "company_name": company or "Unknown company",
        "known_domains": [],
        "portal_type": "GENERIC",
        "application_adapter": "GenericApplicationAdapter",
        "company_policy_key": "GENERIC",
        "company_specific_rules": {},
        "known_question_aliases": {},
        "support_status": "BETA",
    }


def greenhouse_application_url(board_token: str, job_id: str | int) -> str:
    board = str(board_token).strip().casefold()
    token = str(job_id).strip()
    if not re.fullmatch(r"[a-z0-9_-]+", board) or not token.isdigit():
        return ""
    return f"https://job-boards.greenhouse.io/embed/job_app?{urlencode({'for': board, 'token': token})}"


def direct_application_url(application_url: str, company: str = "", portal_job_id: str = "") -> str:
    """Return a job-specific application form URL when an official career URL is only a listing shell."""
    value = application_url.strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        return value
    query = parse_qs(parsed.query)
    if parsed.hostname == "job-boards.greenhouse.io" and parsed.path == "/embed/job_app":
        return value
    policy = company_policy(company)
    board_token = str(policy["company_specific_rules"].get("greenhouse_board_token", ""))
    greenhouse_job_id = (query.get("gh_jid") or query.get("token") or [portal_job_id])[0]
    direct_url = greenhouse_application_url(board_token, greenhouse_job_id)
    return direct_url or value


def detect_portal_from_url(application_url: str, company: str = "") -> dict[str, Any]:
    try:
        parsed = urlparse(application_url)
    except ValueError:
        parsed = urlparse("")
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    evidence: list[str] = []
    portal_type = "UNKNOWN"

    if "myworkdayjobs.com" in host or "/workday/" in path:
        portal_type, evidence = "WORKDAY", ["workday hostname or path"]
    elif "greenhouse.io" in host or host == "grnh.se":
        portal_type, evidence = "GREENHOUSE", ["greenhouse hostname"]
    elif host in {"jobs.careers.microsoft.com", "careers.microsoft.com"}:
        portal_type, evidence = "MICROSOFT_CAREERS", ["Microsoft Careers hostname"]
    elif host == "amazon.jobs" or host.endswith(".amazon.jobs"):
        portal_type, evidence = "AMAZON_JOBS", ["Amazon Jobs hostname"]
    elif host == "careers.oracle.com" or host.endswith(".oraclecloud.com"):
        portal_type, evidence = "ORACLE_CAREERS", ["Oracle recruiting hostname"]
    elif host.endswith(".lever.co") or host == "jobs.lever.co":
        portal_type, evidence = "LEVER", ["Lever hostname"]
    elif host.endswith(".ashbyhq.com") or host == "jobs.ashbyhq.com":
        portal_type, evidence = "ASHBY", ["Ashby hostname"]
    elif "smartrecruiters.com" in host:
        portal_type, evidence = "SMARTRECRUITERS", ["SmartRecruiters hostname"]
    elif "google.com" in host and "/about/careers" in path:
        portal_type, evidence = "GOOGLE_CAREERS", ["Google Careers URL"]
    elif host:
        policy = company_policy(company)
        known = any(host == domain or host.endswith(f".{domain}") for domain in policy["known_domains"])
        if known and policy["portal_type"] in PORTAL_TYPES:
            portal_type = str(policy["portal_type"])
            evidence = [f"company registry match for {policy['company_id']}"]
        else:
            portal_type, evidence = "GENERIC", ["unrecognized HTTPS career portal"]

    requisition_match = re.search(r"\b(?:JR|R|REQ)[-_]?\d{4,}\b", f"{path} {parsed.query}", re.IGNORECASE)
    query = parse_qs(parsed.query)
    numeric_job_id = (query.get("token") or query.get("gh_jid") or [""])[0]
    policy = company_policy(company)
    return {
        "portal_type": portal_type,
        "host": host,
        "portal_job_id": requisition_match.group(0).upper() if requisition_match else (numeric_job_id if numeric_job_id.isdigit() else ""),
        "detection_evidence": evidence,
        "support_status": PORTAL_SUPPORT.get(portal_type, "UNSUPPORTED"),
        "application_adapter": {
            "WORKDAY": "WorkdayAdapter",
            "GREENHOUSE": "GreenhouseAdapter",
            "MICROSOFT_CAREERS": "MicrosoftCareersAdapter",
            "AMAZON_JOBS": "AmazonJobsAdapter",
            "ORACLE_CAREERS": "OracleCareersAdapter",
            "GENERIC": "GenericApplicationAdapter",
        }.get(portal_type, ""),
        "company_policy_key": policy["company_policy_key"],
        "company_id": policy["company_id"],
    }
