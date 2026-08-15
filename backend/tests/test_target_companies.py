import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.jobs.refresh import _merge_duplicate
from app.jobs.target_search import search_target_companies
from app.models import CompanySource, Job, TargetCompany
from app.services.scoring import analyze_job
from app.services.target_companies import (
    ALIASES,
    normalize_company_name,
    priority_bonus,
    search_is_due,
    seed_records,
)
from app.sources.base import is_target_internship_title


def make_target(name: str = "Oracle", **changes) -> TargetCompany:
    values = {
        "company_name": name,
        "aliases": ALIASES.get(name, [name]),
        "careers_domains": [],
        "category": "Cloud and data",
        "priority": "high",
        "enabled": True,
        "preferred_locations": [],
        "preferred_role_categories": [],
    }
    values.update(changes)
    return TargetCompany(**values)


@pytest.mark.parametrize(
    "alias",
    ["Oracle", "Oracle Corporation", "Oracle Cloud", "Oracle Cloud Infrastructure", "OCI", "Oracle Labs", "NetSuite"],
)
def test_oracle_aliases_normalize_to_one_company(alias):
    target = make_target()
    assert normalize_company_name(alias, [target]) == ("Oracle", target)


def test_oci_alias_does_not_modify_user_certifications():
    target = make_target()
    certifications = ["Python Data Structures"]
    normalize_company_name("OCI", [target])
    assert certifications == ["Python Data Structures"]
    assert "OCI" not in certifications


def test_official_duplicate_keeps_official_url_and_tracks_aggregator():
    job = Job(
        source_name="Oracle Careers",
        source_url="https://careers.oracle.com",
        company="Oracle",
        title="Software Engineer Intern",
        location="Mexico",
        apply_url="https://careers.oracle.com/job/1",
        official_apply_url="https://careers.oracle.com/job/1",
        official_status="open",
        verification_status="verified",
        raw_data_hash="official",
    )
    _merge_duplicate(
        job,
        {
            "source_name": "Aggregator",
            "source_url": "https://aggregator.example",
            "apply_url": "https://aggregator.example/job/1",
            "official_apply_url": None,
            "official_status": "unknown",
            "verification_status": "unverified",
        },
    )
    assert job.apply_url == "https://careers.oracle.com/job/1"
    assert job.alternate_sources[0]["apply_url"] == "https://aggregator.example/job/1"


def test_target_bonus_is_moderate_and_does_not_override_blocker(profile, base_job):
    job = dict(base_job)
    job.update(
        {
            "company": "Oracle",
            "is_target_company": True,
            "company_priority_bonus": priority_bonus("high", True, True),
            "requirements": "Must be a U.S. citizen. C++ and Linux required.",
        }
    )
    result = analyze_job(job, profile)
    assert result.recommendation == "Not Eligible"
    assert result.overall_score < 80


def test_senior_and_staff_roles_are_not_target_internships():
    assert not is_target_internship_title("Senior Software Engineer Intern")
    assert not is_target_internship_title("Staff Embedded Systems Intern")
    assert is_target_internship_title("Software Developer Intern")


def test_remote_canada_is_not_remote_mexico(profile, base_job):
    job = dict(base_job)
    job.update(
        {
            "country": "Canada",
            "location": "Remote - Canada",
            "remote_type": "Remote",
            "remote_from_mexico_allowed": False,
        }
    )
    result = analyze_job(job, profile)
    assert any("Canadian work permit" in risk for risk in result.risk_flags)
    assert not any("explicitly allows remote work from Mexico" in reason for reason in result.positive_reasons)


def test_priority_schedule_cadence():
    now = datetime.now(timezone.utc)
    high = make_target(priority="high", last_checked_at=now - timedelta(hours=25))
    medium = make_target("IBM", priority="medium", last_checked_at=now - timedelta(hours=25))
    low = make_target("Other", priority="low", last_checked_at=now - timedelta(days=6))
    assert search_is_due(high, now)
    assert not search_is_due(medium, now)
    assert not search_is_due(low, now)


def test_target_search_uses_enabled_company_once_for_aliases(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        oracle = make_target()
        disabled = make_target("IBM", enabled=False)
        db.add_all([oracle, disabled])
        db.flush()
        source = CompanySource(
            company="OCI",
            source_type="official_careers",
            source_identifier="oracle",
            source_url="https://careers.oracle.com",
            enabled=True,
        )
        db.add(source)
        db.commit()
        captured = {}

        async def fake_refresh(current_db, source_ids=None):
            captured["source_ids"] = source_ids
            return {
                "jobs_fetched": 0,
                "jobs_created": 0,
                "jobs_updated": 0,
                "errors": [],
            }

        monkeypatch.setattr("app.jobs.target_search.refresh_all_sources", fake_refresh)
        run = asyncio.run(
            search_target_companies(db, force=True, company_id=oracle.id)
        )
        assert run.companies_checked == 1
        assert captured["source_ids"] == {source.id}


def test_search_all_target_companies_uses_every_enabled_source(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(make_target())
        db.commit()
        captured = {}

        async def fake_refresh(current_db, source_ids=None):
            captured["source_ids"] = source_ids
            return {
                "jobs_fetched": 0,
                "jobs_created": 0,
                "jobs_updated": 0,
                "errors": [],
            }

        monkeypatch.setattr("app.jobs.target_search.refresh_all_sources", fake_refresh)
        run = asyncio.run(search_target_companies(db, force=True))
        assert run.companies_checked == 1
        assert captured["source_ids"] is None


def test_seed_keeps_general_discovery_optional():
    names = {record["company_name"] for record in seed_records()}
    assert {"Oracle", "NVIDIA", "Rivian", "Zipline"}.issubset(names)
    assert "Example New Startup" not in names
    assert normalize_company_name("Example New Startup", [make_target()]) == (
        "Example New Startup",
        None,
    )
