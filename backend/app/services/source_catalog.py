"""SourceCatalog policy over existing CompanySource company/board records."""
SOURCE_CATALOG = {
    "greenhouse": {"type": "official_ats", "hours": 6, "quick": True, "minimum_interval_seconds": .25},
    "lever": {"type": "official_ats", "hours": 6, "quick": True, "minimum_interval_seconds": .25},
    "ashby": {"type": "official_ats", "hours": 6, "quick": True, "minimum_interval_seconds": .25},
    "smartrecruiters": {"type": "official_ats", "hours": 6, "quick": True, "minimum_interval_seconds": .25},
    "workday": {"type": "official_ats", "hours": 12, "experimental": True, "minimum_interval_seconds": .75},
    "freehire": {"type": "external_discovery", "hours": 6, "quick": True, "opt_in": True, "minimum_interval_seconds": 1},
    "web_search": {"type": "web_discovery", "hours": 24, "opt_in": True, "minimum_interval_seconds": 1},
    "research": {"type": "research_discovery", "hours": 24, "opt_in": True, "minimum_interval_seconds": 1},
    "jobspy": {"type": "external_discovery", "hours": 24, "optional": True, "implemented": False},
    "usajobs": {"type": "public_api", "hours": 24, "implemented": False},
    "manual": {"type": "manual", "scheduled": False},
}


def source_hours(kind):
    return SOURCE_CATALOG.get(kind, {}).get("hours")
