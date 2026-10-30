import asyncio
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import Base, SessionLocal
from app.jobs.import_google import (
    import_google_for_authorized_users,
    import_google_opportunities,
    resolve_authorized_import_owners,
    resolve_import_owner,
)
from app.jobs.import_priority_jobs import (
    AMAZON_PRIORITY_IDS, GOOGLE_PRIORITY_IDS, PRIORITY_IDS, import_priority_opportunities,
)
from app.jobs.refresh import _update_job, persist_analysis
from app.main import app
from app.models import AuthorizedAccount, GeneratedResume, Job, ResumeProfile, UserProfile
from app.security.identity import JOSHUA_EMAIL, JOSHUA_USER_ID
from app.services.dedupe import same_job
from app.sources.google_careers import GOOGLE_SEARCH_URL, parse_google_listing
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.amazon_jobs import AmazonJobsAdapter
from app.services.resume_generation import generate_local_content
from app.services.scoring import analyze_job
from app.services.research_application_status import apply_research_application_status, is_research_internship, is_us_research_internship
from conftest import security_headers


def row(job_id="100648618540573382", title="Software Engineering Intern, BS, Summer 2027", country="US"):
    data = [None] * 21
    data[:3] = [job_id, title, f"https://www.google.com/about/careers/applications/signin?jobId=real-{job_id}&loc={country}"]
    data[3] = [None, "<ul><li>Develop and test technical systems.</li></ul>"]
    data[4] = [None, "<h3>Minimum qualifications:</h3><ul><li>Pursuing a Bachelor's degree in Computer Science or a related technical field.</li><li>C++ Python algorithms.</li></ul><h3>Preferred qualifications:</h3><ul><li>Currently attending a degree program in the US.</li></ul>"]
    data[7] = "Google"
    data[9] = [["Mountain View, CA, USA", [], "Mountain View", None, "CA", country]]
    data[10] = [None, "<p>Design and implement technical projects.</p>"]
    data[15] = [None, "<p>Participation requires that you are located in the United States for the duration of the internship.</p>"]
    return data


def listing(rows, total=None, page_size=20):
    payload = [rows, None, total if total is not None else len(rows), page_size]
    return "<script>AF_initDataCallback({key:'ds:1',data:" + json.dumps(payload) + ",sideChannel:{}});</script>"


def normalized(rows):
    adapter = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL)
    return [adapter.normalize_job(item) for item in parse_google_listing(listing(rows))[0]]


def test_public_data_recovers_jobs_without_html_anchors_and_excludes_phd():
    jobs, total, size = parse_google_listing(listing([
        row(), row("555", "Software Engineering Intern, PhD, Summer 2027"),
        row("122803627516404422", "Hardware Engineering Intern, BS/MS, Summer 2027"),
    ]))
    assert total == 3 and size == 20 and len(jobs) == 2
    assert "PhD" not in jobs[0]["description"] + jobs[0]["requirements"]
    assert "Currently attending" not in jobs[0]["requirements"]
    assert "Currently attending" in jobs[0]["preferred_qualifications"]
    assert jobs[1]["url"].endswith("122803627516404422-hardware-engineering-intern-bsms-summer-2027")
    job = normalized([row()])[0]
    assert job.country == "United States"
    assert job.application_url.startswith("https://www.google.com/about/careers/applications/signin?jobId=real-")
    assert job.official_apply_url == job.posting_url == job.canonical_official_url
    assert job.application_url_status == "VERIFIED" and job.job_requires_work_in_us
    assert job.requirements != job.description


def test_google_student_researcher_bs_ms_is_discovered_without_explicit_ids():
    rows = [
        row("131518356678156998", "Student Researcher, BS/MS, Winter-Summer 2027", "US"),
        row("104405499448828614", "Student Researcher, BS/MS, Winter-Summer 2027", "CA"),
        row("114416552819729094", "Student Researcher, BS/MS, Winter-Summer 2027", "CA"),
        row("134313315235963590", "Student Researcher, PhD, Winter-Summer 2027", "US"),
    ]
    discovered, _, _ = parse_google_listing(listing(rows))
    assert {job["external_id"] for job in discovered} == {
        "131518356678156998", "104405499448828614", "114416552819729094",
    }
    normalized_jobs = [
        OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL).normalize_job(job)
        for job in discovered
    ]
    assert all(job.application_url_status == "VERIFIED" for job in normalized_jobs)
    assert [job.country for job in normalized_jobs] == ["United States", "Canada", "Canada"]


def test_google_student_researcher_apply_now_respects_candidate_work_authorization():
    research_row = row(
        "131518356678156998", "Student Researcher, BS/MS, Winter-Summer 2027", "US",
    )
    research_row[4] = [None, "<h3>Minimum qualifications:</h3><ul>"
                       "<li>Currently enrolled in a Bachelor's or Master's degree in Computer Science or a related technical field.</li>"
                       "<li>Experience in an area of computer science such as Software Engineering.</li></ul>"]
    research_row[15] = [None, "<p>Participation requires that you are located in the United States for the engagement.</p>"]
    job = normalized([research_row])[0]
    assert is_research_internship(job)
    assert is_us_research_internship(job)
    base_profile = dict(
        owner_user_id="candidate", full_name="Candidate", degree="B.S. in Robotics and Digital Systems Engineering",
        degree_field="Robotics and Digital Systems Engineering", degree_level_current="BACHELORS",
        degree_status="IN_PROGRESS", graduation_year=2028, skills=["Python", "C++"],
        citizenship_country="Mexico", willing_to_relocate=True,
    )
    mexican_profile = UserProfile(
        **base_profile, work_authorized_countries=["Mexico"],
        us_work_authorized=False, requires_us_employment_sponsorship=True,
    )
    uncertain = analyze_job(job, mexican_profile)
    assert uncertain.eligibility_status == "UNKNOWN"
    assert uncertain.blocker_reasons == []
    assert apply_research_application_status(job, uncertain) is None
    assert uncertain.recommendation == "Needs Verification"

    authorized_profile = UserProfile(
        **base_profile, work_authorized_countries=["Mexico", "United States"],
        us_work_authorized=True, requires_us_employment_sponsorship=False,
    )
    eligible = analyze_job(job, authorized_profile)
    assert eligible.eligibility_status in {"ELIGIBLE", "LIKELY_ELIGIBLE"}
    assert apply_research_application_status(job, eligible) == "Apply Now"


def test_explicit_country_code_is_used_outside_north_america():
    assert normalized([row(country="IL")])[0].country == "Israel"


@pytest.mark.parametrize("title", ["Application Engineering Intern, Summer 2027 (English)", "Security Consultant Intern, BS/MS, Summer 2027"])
def test_other_google_technical_internships_are_not_omitted(title):
    assert len(parse_google_listing(listing([row(title=title)]))[0]) == 1


def test_security_engineering_internship_is_discovered_and_explicit_id_remains_supported():
    security_id = "136826798817059526"
    payload = listing([row(security_id, "Security Engineering Intern, BS/MS, Summer 2027")])
    discovered = parse_google_listing(payload)[0]
    jobs, _, _ = parse_google_listing(payload, required_external_ids={security_id})
    assert [job["external_id"] for job in discovered] == [security_id]
    assert [job["external_id"] for job in jobs] == [security_id]


def test_explicit_google_ids_collect_only_the_requested_postings(monkeypatch):
    requested_id = "136826798817059526"

    class Response:
        url = GOOGLE_SEARCH_URL
        text = listing([
            row(requested_id, "Security Engineering Intern, BS/MS, Summer 2027"),
            row(),
        ])

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("app.sources.official_careers.httpx.AsyncClient", Client)
    adapter = OfficialCareersAdapter(
        "Google", "google", GOOGLE_SEARCH_URL,
        search_criteria={"required_external_ids": [requested_id]},
    )
    assert [job.external_id for job in asyncio.run(adapter.collect())] == [requested_id]


def test_many_google_locations_fit_database_without_losing_source_locations():
    data = row()
    data[9] = [[f"City {index}, State, USA", [], f"City {index}", None, "State", "US"] for index in range(40)]
    job = normalized([data])[0]
    assert len(job.location) <= 240
    assert "other locations" in job.location
    assert job.country == "United States"
    assert job.raw_data["locations"] == [location[0] for location in data[9]]
    assert job.city == "" and job.region == "State"
    for column in Job.__table__.columns:
        value = job.to_dict().get(column.name)
        limit = getattr(column.type, "length", None)
        if limit and isinstance(value, str):
            assert len(value) <= limit, column.name


def test_invalid_schema_is_not_reported_as_a_healthy_empty_feed():
    with pytest.raises(ValueError, match="schema changed"):
        parse_google_listing("<script>AF_initDataCallback({data:runUnknownCode()});</script>")


def test_changed_application_url_skips_only_the_bad_google_row():
    malformed = row("777", "Hardware Engineering Intern, BS/MS, Summer 2027")
    malformed[2] = "https://jobs.example.net/777/apply"
    diagnostics = []
    jobs, _, _ = parse_google_listing(listing([malformed, row("778")]), diagnostics=diagnostics)
    assert [job["external_id"] for job in jobs] == ["778"]
    assert diagnostics == [
        "Google Careers job 777: unsupported application URL format "
        "(host=jobs.example.net, path=/777/apply, query_keys=none); row skipped."
    ]


def test_google_detail_page_url_format_is_supported_as_application_target():
    data = row("779")
    data[2] = "https://www.google.com/about/careers/applications/jobs/results/779-hardware-engineering-intern"
    jobs, _, _ = parse_google_listing(listing([data]))
    assert jobs[0]["application_url"] == data[2]


def test_missing_direct_apply_link_retains_official_details_page_without_inventing_a_link():
    data = row("780")
    data[2] = None
    jobs, _, _ = parse_google_listing(listing([data]))
    assert jobs[0]["application_url"] is None
    normalized_job = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL).normalize_job(jobs[0])
    assert normalized_job.apply_url == jobs[0]["url"]
    assert normalized_job.canonical_official_url == jobs[0]["url"]


def test_google_import_fails_clearly_if_no_candidate_row_has_supported_application_url(monkeypatch):
    malformed = row("777", "Hardware Engineering Intern, BS/MS, Summer 2027")
    malformed[2] = "https://jobs.example.net/777/apply"

    class Response:
        url = GOOGLE_SEARCH_URL
        text = listing([malformed])

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("app.sources.official_careers.httpx.AsyncClient", Client)
    adapter = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL)
    with pytest.raises(RuntimeError, match="none had a supported official application URL"):
        asyncio.run(adapter.collect())


def test_one_malformed_google_row_does_not_abort_valid_results_from_the_group(monkeypatch):
    malformed = row("777", "Hardware Engineering Intern, BS/MS, Summer 2027")
    malformed[2] = "https://jobs.example.net/777/apply"

    class Response:
        url = GOOGLE_SEARCH_URL
        text = listing([malformed, row("778")])

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("app.sources.official_careers.httpx.AsyncClient", Client)
    adapter = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL)
    jobs = asyncio.run(adapter.collect())
    assert [job.external_id for job in jobs] == ["778"]


def test_google_fetch_paginates_sequentially_and_does_not_fetch_search_recommendations(monkeypatch):
    requests = []
    class Response:
        url = GOOGLE_SEARCH_URL
        def __init__(self, page):
            self.text = listing([row(str(page))], total=2, page_size=1)
        def raise_for_status(self):
            pass
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, params):
            requests.append((url, params["page"]))
            return Response(params["page"])
    monkeypatch.setattr("app.sources.official_careers.httpx.AsyncClient", Client)
    adapter = OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL)
    assert len(asyncio.run(adapter.collect())) == 2
    assert requests == [(GOOGLE_SEARCH_URL, 1), (GOOGLE_SEARCH_URL, 2)]


def test_distinct_google_cycles_never_merge_because_of_matching_titles():
    left = normalized([row()])[0].to_dict()
    right = normalized([row("85564713261245126")])[0].to_dict()
    assert not same_job(left, right)
    assert same_job(left, deepcopy(left))


def test_import_is_idempotent_and_scoped_to_one_user():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for owner in ("santiago", "joshua"):
            db.add(UserProfile(owner_user_id=owner, full_name=owner, degree="Engineering", university="University",
                               graduation_year=2028, gpa=93.05, nationality="Mexican", skills=["C++", "Python"]))
        db.commit()
        jobs = normalized([row(), row("122803627516404422", "Hardware Engineering Intern, BS/MS, Summer 2027"), row("999")])
        records = import_google_opportunities(db, jobs, "santiago")
        assert len(records) == 3
        assert all(job.owner_user_id == "santiago" for job in records)
        assert records[0].is_priority_alert and records[0].is_priority_pinned
        assert records[1].is_priority_alert and records[1].is_priority_pinned
        assert not records[2].is_priority_pinned
        original_ids = [job.id for job in records]
        assert [job.id for job in import_google_opportunities(db, jobs, "santiago")] == original_ids
        assert not db.scalars(select(Job).where(Job.owner_user_id == "joshua")).all()
        _update_job(records[0], {"raw_data": {"updated": True}})
        persist_analysis(db, records[0], db.scalar(select(UserProfile).where(UserProfile.owner_user_id == "santiago")))
        assert records[0].is_priority_pinned and records[0].is_priority_alert
        with pytest.raises(RuntimeError, match="profile does not exist"):
            import_google_opportunities(db, jobs, "unknown")


def test_google_research_is_imported_and_analyzed_independently_for_authorized_users():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for owner, authorized in (("santiago", True), (JOSHUA_USER_ID, False), ("inactive", True)):
            db.add(UserProfile(
                owner_user_id=owner, full_name=owner, degree="B.S. in Robotics and Digital Systems Engineering",
                university="University", degree_field="Robotics and Digital Systems Engineering",
                degree_level_current="BACHELORS", degree_status="IN_PROGRESS",
                graduation_year=2028, gpa=3.7, nationality="Mexican", citizenship_country="Mexico",
                skills=["Python", "C++"], work_authorized_countries=["Mexico", "United States"] if authorized else ["Mexico"],
                us_work_authorized=authorized, requires_us_employment_sponsorship=not authorized,
            ))
            db.add(AuthorizedAccount(
                user_id=owner, email=f"{owner}@example.com", provider="google", is_active=owner != "inactive",
            ))
        db.commit()
        assert resolve_authorized_import_owners(db) == sorted(["santiago", JOSHUA_USER_ID])

        research = row("131518356678156998", "Student Researcher, BS/MS, Winter-Summer 2027")
        research[4] = [None, "<h3>Minimum qualifications:</h3><ul>"
                       "<li>Currently enrolled in a Bachelor's or Master's degree in Computer Science or a related technical field.</li>"
                       "<li>Experience in software engineering.</li></ul>"]
        jobs = normalized([research, row()])
        imported = import_google_for_authorized_users(db, jobs, "santiago")
        assert set(imported) == {"santiago", JOSHUA_USER_ID}
        assert all(len(records) == 2 for records in imported.values())
        assert not db.scalars(select(Job).where(Job.owner_user_id == "inactive")).all()

        santiago_research = next(job for job in imported["santiago"] if "Research" in job.title)
        joshua_research = next(job for job in imported[JOSHUA_USER_ID] if "Research" in job.title)
        assert santiago_research.id != joshua_research.id
        assert santiago_research.owner_user_id == "santiago"
        assert joshua_research.owner_user_id == JOSHUA_USER_ID
        assert santiago_research.analysis.recommendation == "Apply Now"
        assert joshua_research.analysis.recommendation != "Apply Now"
        assert joshua_research.analysis.eligibility_status == "UNKNOWN"
        assert next(job for job in imported["santiago"] if job.external_id == "100648618540573382").is_priority_pinned
        assert not next(job for job in imported[JOSHUA_USER_ID] if job.external_id == "100648618540573382").is_priority_pinned

        ids = {owner: [job.id for job in records] for owner, records in imported.items()}
        repeated = import_google_for_authorized_users(db, jobs, "santiago")
        assert {owner: [job.id for job in records] for owner, records in repeated.items()} == ids


def test_requested_official_postings_are_all_pinned_for_only_the_requested_user():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(UserProfile(owner_user_id="santiago", full_name="Santiago", degree="Engineering", university="University",
                           graduation_year=2028, gpa=93.05, nationality="Mexican", skills=["C++", "Python"]))
        db.commit()
        google_rows = [row(job_id, "Security Engineering Intern, BS/MS, Summer 2027") for job_id in GOOGLE_PRIORITY_IDS]
        google = [
            OfficialCareersAdapter("Google", "google", GOOGLE_SEARCH_URL).normalize_job(item)
            for item in parse_google_listing(listing(google_rows), required_external_ids=GOOGLE_PRIORITY_IDS)[0]
        ]
        amazon = AmazonJobsAdapter("Amazon", "amazon", "https://www.amazon.jobs/en/search.json")
        amazon_jobs = [amazon.normalize_job({
            "id": job_id, "job_id": job_id,
            "title": "Software Development Engineer Intern, Summer 2027",
            "location": "USA, WA, Seattle", "job_path": f"/en/jobs/{job_id}/software-development-engineer-intern",
            "description": "Build and test software systems.",
            "basic_qualifications": "Currently enrolled in a Bachelor's degree.",
        }) for job_id in AMAZON_PRIORITY_IDS]
        records = import_priority_opportunities(db, [*google, *amazon_jobs], "santiago")
        assert {job.external_id for job in records} == PRIORITY_IDS
        assert all(job.is_priority_pinned and job.is_priority_alert for job in records)
        assert all(job.owner_user_id == "santiago" for job in records)


def test_owner_resolution_requires_a_unique_verified_stored_identity():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(UserProfile(owner_user_id="candidate", full_name="Candidate", degree="Engineering", university="University",
                           graduation_year=2028, gpa=93.05, nationality="Mexican"))
        db.add(ResumeProfile(user_id="candidate", full_name="Candidate", email="cv@example.com"))
        db.add(AuthorizedAccount(user_id="candidate", email="login@example.com", is_active=True))
        db.commit()
        assert resolve_import_owner(db, "", " CV@EXAMPLE.COM ") == "candidate"
        assert resolve_import_owner(db, "candidate", "") == "candidate"
        with pytest.raises(RuntimeError, match="Configure"):
            resolve_import_owner(db, "", "")
        with pytest.raises(RuntimeError, match="exactly one"):
            resolve_import_owner(db, "", "not-stored@example.com")
        with pytest.raises(RuntimeError, match="could not be verified"):
            resolve_import_owner(db, JOSHUA_USER_ID, "")
        db.add(ResumeProfile(user_id="ambiguous", full_name="Other", email="cv@example.com"))
        db.commit()
        with pytest.raises(RuntimeError, match="exactly one"):
            resolve_import_owner(db, "", "cv@example.com")


def test_pinned_jobs_remain_visible_without_changing_eligibility_or_leaking_to_joshua(monkeypatch):
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            job = import_google_opportunities(db, normalized([row()]), settings.primary_user_id)[0]
            job.analysis.eligibility_status = "NOT_ELIGIBLE"
            job.analysis.effective_score = 0
            job.analysis.blocker_reasons = ["Work authorization must be confirmed"]
            db.commit()
            job_id = job.id
            resume_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == settings.primary_user_id))
            sample = generate_local_content(job, resume_profile)
        monkeypatch.setattr("app.main.generate_resume", lambda *_: (sample, "\\documentclass{article}", b"%PDF-1.4"))
        result = client.get("/api/jobs?priority=true").json()
        assert result["items"][0]["id"] == job_id
        assert result["items"][0]["analysis"]["eligibility_status"] == "NOT_ELIGIBLE"
        assert result["items"][0]["analysis"]["effective_score"] == 0
        assert result["items"][0]["is_priority_pinned"] is True
        other = security_headers(JOSHUA_EMAIL, subject=JOSHUA_USER_ID)
        assert job_id not in {item["id"] for item in client.get("/api/jobs?priority=true", headers=other).json()["items"]}
        assert client.get(f"/api/jobs/{job_id}", headers=other).status_code == 404
        generated = client.post(f"/api/jobs/{job_id}/resume/generate", json={"resume_target": "software_engineering"})
        assert generated.status_code == 200, generated.text
        assert generated.json()["status"] == "compiled"
        assert generated.json()["resume_target"] == "software_engineering"
        unchanged = client.get(f"/api/jobs/{job_id}").json()["analysis"]
        assert unchanged["eligibility_status"] == "NOT_ELIGIBLE"
        assert unchanged["blocker_reasons"] == ["Work authorization must be confirmed"]
        assert client.post(f"/api/jobs/{job_id}/resume/generate", headers=other).status_code == 404
        with SessionLocal() as db:
            for resume in db.scalars(select(GeneratedResume).where(GeneratedResume.job_id == job_id)):
                db.delete(resume)
            db.flush()
            db.delete(db.get(Job, job_id))
            db.commit()
