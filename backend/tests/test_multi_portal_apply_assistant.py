import pytest
from sqlalchemy import func, select

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import CompanyPortalRegistry
from app.services.application_assistant import classify_question, detect_portal
from app.services.company_portal_registry import (
    COMPANY_PORTAL_REGISTRY,
    PORTAL_SUPPORT,
    company_policy,
    direct_application_url,
)


def test_portal_detection_matrix() -> None:
    cases = {
        "https://intel.wd1.myworkdayjobs.com/job/REQ-1234": "WORKDAY",
        "https://job-boards.greenhouse.io/zipline/jobs/123": "GREENHOUSE",
        "https://jobs.careers.microsoft.com/global/en/job/123": "MICROSOFT_CAREERS",
        "https://www.amazon.jobs/en/jobs/123/software-intern": "AMAZON_JOBS",
        "https://careers.oracle.com/jobs/123": "ORACLE_CAREERS",
        "https://jobs.lever.co/example/123": "LEVER",
        "https://jobs.ashbyhq.com/example/123": "ASHBY",
        "https://jobs.smartrecruiters.com/Example/123": "SMARTRECRUITERS",
        "https://careers.example.com/apply/123": "GENERIC",
    }
    for url, expected in cases.items():
        assert detect_portal(url)["portal_type"] == expected


def test_zipline_company_registry_routes_own_career_page_to_greenhouse() -> None:
    result = detect_portal("https://www.zipline.com/open-roles/embedded-software", "Zipline")
    assert result["portal_type"] == "GREENHOUSE"
    assert result["company_policy_key"] == "ZIPLINE"
    assert result["support_status"] == "SUPPORTED"


def test_zipline_listing_shell_resolves_to_exact_greenhouse_application() -> None:
    result = direct_application_url(
        "https://www.zipline.com/open-roles?gh_jid=7904518003",
        "Zipline",
    )
    assert result == (
        "https://job-boards.greenhouse.io/embed/job_app?for=flyzipline&token=7904518003"
    )
    portal = detect_portal(result, "Zipline")
    assert portal["portal_type"] == "GREENHOUSE"
    assert portal["portal_job_id"] == "7904518003"


@pytest.mark.parametrize(
    ("company", "listing_url", "board", "job_id"),
    [
        (
            "Duolingo",
            "https://careers.duolingo.com/jobs?gh_jid=8806878002",
            "duolingounirecruitment",
            "8806878002",
        ),
        (
            "Roblox",
            "https://careers.roblox.com/jobs/8072713?gh_jid=8072713",
            "roblox",
            "8072713",
        ),
    ],
)
def test_duolingo_and_roblox_preserve_official_greenhouse_application_links(
    company: str,
    listing_url: str,
    board: str,
    job_id: str,
) -> None:
    result = direct_application_url(listing_url, company)
    assert result == (
        f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={job_id}"
    )
    portal = detect_portal(listing_url, company)
    assert portal["portal_type"] == "GREENHOUSE"
    assert portal["company_policy_key"] == company.upper()


def test_direct_application_url_does_not_rewrite_unrelated_companies() -> None:
    url = "https://careers.example.com/jobs/123"
    assert direct_application_url(url, "Example") == url


def test_company_registry_uses_one_policy_layer_per_company() -> None:
    policies = {entry["company_id"]: entry for entry in COMPANY_PORTAL_REGISTRY}
    assert policies["intel"]["application_adapter"] == "WorkdayAdapter"
    assert policies["ge_aerospace"]["application_adapter"] == "WorkdayAdapter"
    assert policies["microsoft"]["application_adapter"] == "MicrosoftCareersAdapter"
    assert policies["duolingo"]["company_specific_rules"]["greenhouse_board_token"] == "duolingounirecruitment"
    assert policies["roblox"]["company_specific_rules"]["greenhouse_board_token"] == "roblox"
    assert company_policy("AWS")["company_policy_key"] == "AMAZON"
    assert PORTAL_SUPPORT["MICROSOFT_CAREERS"] == "BETA"


def test_company_portal_registry_is_seeded_for_all_phase_one_companies() -> None:
    init_db()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CompanyPortalRegistry)) == len(
            COMPANY_PORTAL_REGISTRY
        )
        zipline = db.scalar(
            select(CompanyPortalRegistry).where(CompanyPortalRegistry.company_id == "zipline")
        )
        assert zipline is not None
        assert zipline.application_adapter == "GreenhouseAdapter"
        assert zipline.resume_behavior == "JOB_SPECIFIC"


def test_company_specific_sensitive_aliases_remain_confirmation_required() -> None:
    assert classify_question("Were you previously employed by GE?")["question_key"] == "FORMER_GE_EMPLOYEE"
    assert classify_question("Do you have a potential conflict of interest?")["question_key"] == "CONFLICT_OF_INTEREST"
    assert classify_question("Were you previously employed by GE?")["policy"] == "CONFIRM_REQUIRED"


def test_unsupported_future_portals_fail_closed() -> None:
    lever = detect_portal("https://jobs.lever.co/example/123")
    assert lever["portal_type"] == "LEVER"
    assert lever["support_status"] == "UNSUPPORTED"
