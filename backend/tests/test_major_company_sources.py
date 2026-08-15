import asyncio

from app.sources.amazon_jobs import AmazonJobsAdapter
from app.sources.base import is_target_internship_title
from app.sources.company_sources import OFFICIAL_COMPANY_SOURCES
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.registry import ADAPTERS
from app.sources.smartrecruiters import SmartRecruitersAdapter
from app.sources.workday import WorkdayAdapter


def test_major_companies_are_configured_with_official_urls():
    assert [source["company"] for source in OFFICIAL_COMPANY_SOURCES[:5]] == [
        "Amazon",
        "Google",
        "Meta",
        "NVIDIA",
        "NXP",
    ]
    assert {source["company"] for source in OFFICIAL_COMPANY_SOURCES} >= {
        "AMD",
        "Qualcomm",
        "Arm",
        "Synopsys",
        "Cadence",
        "Intel",
        "Micron",
        "Western Digital",
        "Marvell",
        "Broadcom",
        "Rockwell Automation",
        "Databricks",
        "MongoDB",
        "Cloudflare",
        "Zoox",
        "Bosch",
    }
    assert all(source["source_url"].startswith("https://") for source in OFFICIAL_COMPANY_SOURCES)
    assert all("example.com" not in source["source_url"] for source in OFFICIAL_COMPANY_SOURCES)


def test_major_company_adapter_types_are_registered():
    assert ADAPTERS["amazon_jobs"] is AmazonJobsAdapter
    assert ADAPTERS["official_careers"] is OfficialCareersAdapter
    assert ADAPTERS["smartrecruiters"] is SmartRecruitersAdapter
    assert ADAPTERS["workday"] is WorkdayAdapter


def test_only_target_student_roles_are_accepted():
    accepted = [
        "Software Development Engineer Intern",
        "Embedded Firmware Co-op",
        "Hardware Validation Student",
        "Robotics Software Internship",
        "Formal Verification Intern",
    ]
    rejected = [
        "Senior Software Engineer",
        "HR Intern",
        "Sales Internship",
        "University Recruiter",
        "Computer Vision Internship, PhD Student",
        "Software Development Engineer Fall Intern - Military Veteran",
    ]
    assert all(is_target_internship_title(title) for title in accepted)
    assert not any(is_target_internship_title(title) for title in rejected)


def test_workday_builds_official_cxs_endpoint():
    adapter = WorkdayAdapter(
        "NVIDIA",
        "nvidia|NVIDIAExternalCareerSite",
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
    )
    assert adapter.api_url == (
        "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/"
        "nvidia/NVIDIAExternalCareerSite"
    )


def test_smartrecruiters_normalizes_official_posting():
    adapter = SmartRecruitersAdapter(
        "Bosch",
        "BoschGroup",
        "https://jobs.smartrecruiters.com/BoschGroup",
    )
    assert adapter.api_url == (
        "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings"
    )
    job = adapter.normalize_job(
        {
            "id": "7440001",
            "uuid": "posting-uuid",
            "name": "Embedded Software Engineering Intern",
            "company": {"name": "Bosch Group"},
            "location": {
                "fullLocation": "Plymouth, Michigan, United States",
                "country": "us",
                "remote": False,
            },
            "releasedDate": "2026-07-30T10:00:00Z",
            "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/7440001-role",
            "applyUrl": "https://jobs.smartrecruiters.com/BoschGroup/7440001-role?oga=true",
            "typeOfEmployment": {"label": "Intern"},
            "jobAd": {
                "sections": {
                    "jobDescription": {
                        "title": "Job Description",
                        "text": "<p>Develop embedded software.</p>",
                    },
                    "qualifications": {
                        "title": "Qualifications",
                        "text": "<ul><li>Currently enrolled.</li></ul>",
                    },
                }
            },
            "active": True,
        }
    )
    assert job.external_id == "posting-uuid"
    assert job.company == "Bosch"
    assert job.official_apply_url.endswith("?oga=true")
    assert "Develop embedded software" in job.description
    assert "Currently enrolled" in job.requirements
    assert job.verification_method == "official_smartrecruiters_api"


def test_workday_reads_every_result_page(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        offsets = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            self.offsets.append(json["offset"])
            if json["offset"] == 0:
                return Response(
                    {
                        "total": 21,
                        "jobPostings": [
                            {"title": f"Unrelated role {index}"}
                            for index in range(20)
                        ],
                    }
                )
            return Response(
                {
                    "total": 21,
                    "jobPostings": [
                        {
                            "title": "Embedded Software Intern",
                            "externalPath": "/job/embedded-intern",
                        }
                    ],
                }
            )

        async def get(self, url):
            return Response(
                {
                    "jobPostingInfo": {
                        "jobReqId": "req-21",
                        "title": "Embedded Software Intern",
                        "location": "Austin, Texas, United States",
                        "jobDescription": "Currently enrolled. C++ required.",
                        "externalUrl": "https://company.example/job/embedded-intern",
                    }
                }
            )

    monkeypatch.setattr("app.sources.workday.httpx.AsyncClient", Client)
    adapter = WorkdayAdapter(
        "Intel",
        "intel|External",
        "https://intel.wd1.myworkdayjobs.com/External",
    )
    jobs = asyncio.run(adapter.collect())
    assert Client.offsets == [0, 20]
    assert [job.external_id for job in jobs] == ["req-21"]


def test_amazon_normalization_uses_official_application_link():
    adapter = AmazonJobsAdapter(
        "Amazon", "internships", "https://www.amazon.jobs/en/search?base_query=intern"
    )
    job = adapter.normalize_job(
        {
            "id": "123",
            "title": "Software Development Engineer Intern",
            "location": "Seattle, WA, USA",
            "description": "Build distributed systems.",
            "basic_qualifications": "Currently enrolled in a Bachelor's degree.",
            "preferred_qualifications": "Python",
            "job_path": "/en/jobs/123/software-development-engineer-intern",
            "posted_date": "2026-07-20",
        }
    )
    assert job.official_apply_url == (
        "https://www.amazon.jobs/en/jobs/123/software-development-engineer-intern"
    )
    assert job.official_status == "open"
    assert job.verification_status == "verified"
