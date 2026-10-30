import pytest
from types import SimpleNamespace

from app.sources.company_sources import OFFICIAL_COMPANY_SOURCES
from app.sources.greenhouse import GreenhouseAdapter
from app.sources.registry import create_adapter


def test_greenhouse_filters_for_student_roles():
    accepted = [
        "Software Engineering Intern",
        "Firmware Internship - Summer 2027",
        "Electrical Engineering Co-op",
        "Student Robotics Program",
        "Software Engineer, Early Career",
    ]
    rejected = [
        "Senior Software Engineer",
        "Staff FPGA Engineer",
        "Engineering Manager",
        "University Recruiter",
    ]

    assert all(GreenhouseAdapter.is_internship_title(title) for title in accepted)
    assert not any(
        GreenhouseAdapter.is_internship_title(title) for title in rejected
    )


def test_greenhouse_normalization_uses_the_exact_application_form():
    adapter = GreenhouseAdapter(
        "Zipline",
        "flyzipline",
        "https://boards.greenhouse.io/flyzipline",
    )
    job = adapter.normalize_job(
        {
            "id": 7904518003,
            "title": "Aerodynamics Intern (Summer 2027)",
            "location": {"name": "South San Francisco, California, USA"},
            "content": "Internship description",
            "absolute_url": "https://www.zipline.com/open-roles?gh_jid=7904518003",
            "updated_at": "2026-08-21T16:37:58-04:00",
        }
    )
    assert job.apply_url == (
        "https://job-boards.greenhouse.io/embed/job_app?for=flyzipline&token=7904518003"
    )
    assert job.official_apply_url == job.apply_url
    assert job.original_source_url == "https://www.zipline.com/open-roles?gh_jid=7904518003"


@pytest.mark.parametrize(
    ("company", "board", "source_url", "title", "job_id", "listing_url"),
    [
        (
            "Duolingo",
            "duolingounirecruitment",
            "https://job-boards.greenhouse.io/duolingounirecruitment",
            "Software Engineer, Intern",
            8806878002,
            "https://job-boards.greenhouse.io/duolingounirecruitment/jobs/8806878002",
        ),
        (
            "Roblox",
            "roblox",
            "https://careers.roblox.com/jobs",
            "[Summer 2027] Software Engineer Intern",
            8072713,
            "https://careers.roblox.com/jobs/8072713?gh_jid=8072713",
        ),
    ],
)
def test_duolingo_and_roblox_follow_the_standard_greenhouse_pipeline(
    company,
    board,
    source_url,
    title,
    job_id,
    listing_url,
):
    source = next(item for item in OFFICIAL_COMPANY_SOURCES if item["company"] == company)
    assert source == {
        "company": company,
        "source_type": "greenhouse",
        "source_identifier": board,
        "source_url": source_url,
    }
    configured_adapter = create_adapter(SimpleNamespace(**source))
    assert isinstance(configured_adapter, GreenhouseAdapter)

    adapter = GreenhouseAdapter(company, board, source_url)
    job = adapter.normalize_job(
        {
            "id": job_id,
            "title": title,
            "location": {"name": "Pittsburgh, Pennsylvania, United States"},
            "content": "Technical internship using backend services and systems.",
            "absolute_url": listing_url,
            "updated_at": "2026-09-23T12:00:00-04:00",
        }
    )

    assert job.company == company
    assert job.source_name == "Greenhouse"
    assert job.source_url == source_url
    assert job.original_source_url == listing_url
    assert job.official_apply_url == (
        f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={job_id}"
    )
    assert job.apply_url == job.official_apply_url
    assert job.verification_status == "verified"
