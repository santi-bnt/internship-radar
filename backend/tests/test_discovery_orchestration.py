from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx

from app.services.dedupe import same_job
from app.services.discovery_orchestration import (
    DISCOVERY_GROUPS,
    GROUP_HOURS,
    mark_source_failure,
    mark_source_success,
    select_group_sources,
    source_group,
    stable_jitter_seconds,
)


NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _source(**overrides):
    values = {
        "id": 1,
        "company": "Example",
        "source_type": "greenhouse",
        "source_identifier": "example",
        "source_url": "https://boards.greenhouse.io/example",
        "enabled": True,
        "reference_only": False,
        "priority": 50,
        "refresh_frequency": "daily",
        "last_success_at": None,
        "next_run_at": None,
        "backoff_until": None,
        "rate_limited_until": None,
        "consecutive_failures": 0,
        "source_status": "HEALTHY",
        "discovery_checkpoint_json": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_groups_have_distinct_staggered_windows():
    assert len(DISCOVERY_GROUPS) == len(set(GROUP_HOURS.values()))
    assert GROUP_HOURS["CANADA"] != GROUP_HOURS["GREENHOUSE"]


def test_source_grouping_and_source_budget_prevent_all_at_once():
    sources = [
        _source(
            id=index,
            source_identifier=f"source-{index}",
            source_url=f"https://{index}.greenhouse.example/jobs",
        )
        for index in range(10)
    ]
    selected = select_group_sources(sources, "GREENHOUSE", now=NOW, budget=3)
    assert len(selected) == 3
    assert all(source_group(source) == "GREENHOUSE" for source in selected)


def test_per_domain_limit_selects_one_source_per_board():
    sources = [_source(id=1), _source(id=2, source_identifier="same-domain")]
    selected = select_group_sources(sources, "GREENHOUSE", now=NOW, budget=8)
    assert [source.id for source in selected] == [1]


def test_canada_group_has_reserved_coverage_even_without_canada_named_company():
    sources = [
        _source(id=1, company="Amazon", geography_scope="US_CANADA"),
        _source(id=2, company="Microsoft Canada", source_type="official_careers", source_url="https://careers.microsoft.com/jobs", geography_scope="CANADA"),
    ]
    selected = select_group_sources(sources, "CANADA", now=NOW, budget=8)
    assert {source.id for source in selected} == {1, 2}


def test_stable_jitter_is_deterministic_and_bounded():
    source = _source(id=99, source_identifier="same-source")
    assert stable_jitter_seconds(source, max_seconds=60) == stable_jitter_seconds(source, max_seconds=60)
    assert 0 <= stable_jitter_seconds(source, max_seconds=60) <= 60


def test_retry_after_rate_limit_defers_only_the_affected_source():
    source = _source(consecutive_failures=1)
    request = httpx.Request("GET", "https://boards.greenhouse.io/example")
    response = httpx.Response(429, headers={"Retry-After": "120"}, request=request)
    mark_source_failure(source, httpx.HTTPStatusError("limited", request=request, response=response), now=NOW)
    assert source.retry_after_seconds == 120
    assert source.rate_limited_until == NOW + timedelta(seconds=120)
    other = _source(id=2)
    assert select_group_sources([source, other], "GREENHOUSE", now=NOW, budget=8) == [other]


def test_exponential_backoff_and_success_reset():
    source = _source(consecutive_failures=3)
    mark_source_failure(source, RuntimeError("temporary timeout"), now=NOW)
    assert source.backoff_until > NOW
    assert source.discovery_checkpoint_json["state"] == "retry"
    mark_source_success(source, now=NOW)
    assert source.consecutive_failures == 0
    assert source.backoff_until is None
    assert source.rate_limited_until is None
    assert source.next_run_at > NOW


def test_localized_or_tracking_urls_still_deduplicate_in_shared_pipeline():
    left = {
        "company": "Amazon",
        "title": "Software Development Engineer Intern",
        "location": "Toronto, Canada",
        "apply_url": "https://amazon.jobs/en/jobs/3123243/software-development-engineer?ref=search",
    }
    right = {
        "company": "Amazon",
        "title": "Software Development Engineer Intern",
        "location": "Toronto, Canada",
        "apply_url": "https://amazon.jobs/fr/jobs/3123243/software-development-engineer",
    }
    assert same_job(left, right)
