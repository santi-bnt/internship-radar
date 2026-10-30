from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Application,
    CandidateJobOverride,
    GeneratedResume,
    Job,
    JobAnalysis,
    ResumeProfile,
)
from app.security.identity import ALONSO_USER_ID, JOSHUA_USER_ID
from app.services.resume_generation import generate_local_content
from app.sources.workday import WorkdayAdapter
from conftest import security_headers


HPE_URL = (
    "https://hpe.wd5.myworkdayjobs.com/en-US/Jobsathpe/job/"
    "Tlaquepaque-Jalisco-Mexico/Digital-transformation-internship_1213000"
)
HPE_DESCRIPTION = """
<div>
  <p><b>Job Description:</b></p>
  <p>This role has been designed as Hybrid with an average of 2 days per week
  from an HPE office.</p>
  <p><b>Job Family Definition:</b></p>
  <p>Students or recent graduates enrolled in accredited programs.</p>
  <p><b>Responsibilities:</b></p>
  <ul><li>Support senior team members on technical projects.</li>
  <li>Identify and troubleshoot technical issues.</li>
  <li>Support hardware, software, and technical systems.</li></ul>
  <p><b>Education &amp; Experience:</b></p>
  <p>Currently pursuing a Bachelor's degree in Engineering, Computer Science,
  Information Technology, or a related technical field.</p>
  <p><b>Knowledge &amp; Skills:</b></p>
  <p>Basic programming or scripting knowledge, including Python, Java, or C++.
  Advanced English, problem solving, analytical skills, communication, and a
  strong interest in technology.</p>
  <p><b>Preferred Qualifications:</b></p>
  <p>Interest in learning new technologies and methodologies.</p>
</div>
"""


def _official_hpe_raw() -> dict:
    return {
        "jobReqId": "1213000",
        "jobPostingId": "Digital-transformation-internship_1213000",
        "title": "Digital transformation internship",
        "location": "Tlaquepaque, Jalisco, Mexico",
        "timeType": "Full time",
        "jobDescription": HPE_DESCRIPTION,
        "externalUrl": HPE_URL,
        "canApply": True,
        "posted": True,
        "_listing": {
            "externalPath": "/job/Tlaquepaque-Jalisco-Mexico/Digital-transformation-internship_1213000",
        },
    }


def _adapter() -> WorkdayAdapter:
    return WorkdayAdapter(
        "Hewlett Packard Enterprise",
        "hpe|Jobsathpe",
        "https://hpe.wd5.myworkdayjobs.com/Jobsathpe",
    )


def test_workday_normalization_extracts_description_requirements_skills_and_hybrid():
    normalized = _adapter().normalize_job(_official_hpe_raw())

    assert normalized.external_id == "1213000"
    assert normalized.location == "Tlaquepaque, Jalisco, Mexico"
    assert normalized.remote_type == "Hybrid"
    assert len(normalized.description) > 500
    assert "Support senior team members" in normalized.description
    assert "Engineering, Computer Science" in normalized.requirements
    assert "Python" in normalized.requirements
    assert "Java" in normalized.requirements
    assert "C++" in normalized.requirements
    assert "learning new technologies" in normalized.preferred_qualifications
    assert normalized.canonical_official_url.rstrip("/") == HPE_URL.rstrip("/")


def _remove_test_job(db, job_id: int) -> None:
    db.query(Application).filter(Application.job_id == job_id).delete()
    db.query(CandidateJobOverride).filter(CandidateJobOverride.job_id == job_id).delete()
    db.query(GeneratedResume).filter(GeneratedResume.job_id == job_id).delete()
    db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).delete()
    db.query(Job).filter(Job.id == job_id).delete()
    db.commit()


def test_manual_recheck_enriches_existing_hpe_job_and_resume_can_generate(monkeypatch, request):
    owner = settings.effective_primary_user_id
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            existing_ids = list(db.scalars(select(Job.id).where(
                Job.owner_user_id == owner,
                Job.external_id == "1213000",
            )))
            assert not existing_ids, "HPE fixture requisition already exists in the isolated test database."

            weak = _adapter().normalize_job({
                **_official_hpe_raw(),
                "jobDescription": "",
                "location": "Tlajomulco, Jalisco, Mexico",
                "canApply": None,
            })
            data = weak.to_dict()
            data.update({
                "owner_user_id": owner,
                "source_name": "LinkedIn discovery",
                "description": "",
                "requirements": "",
                "preferred_qualifications": "",
                "location": "Tlajomulco, Jalisco, Mexico",
                "remote_type": "On-site",
                "official_status": "unknown",
                "verification_status": "unverified",
                "status": "active",
            })
            job = Job(**data)
            db.add(job)
            db.flush()
            job_id = job.id

            override = CandidateJobOverride(
                owner_user_id=owner, job_id=job_id, force_apply_now=True,
            )
            db.add(override)
            prior_resume = GeneratedResume(
                user_id=owner,
                job_id=job_id,
                version=1,
                status="compiled",
                target_role=job.title,
                resume_target="recommended",
                content_hash="hpe-existing-resume",
            )
            db.add(prior_resume)
            db.flush()
            application = Application(
                owner_user_id=owner,
                job_id=job_id,
                company="Hewlett Packard Enterprise",
                status="Applied",
                status_history=[{"from": "Saved", "to": "Applied"}],
                submitted_resume_id=prior_resume.id,
                notes="Existing application note must survive recheck.",
            )
            db.add(application)
            db.flush()
            application_id, resume_id = application.id, prior_resume.id
            db.commit()
            request.addfinalizer(lambda: _cleanup_job(job_id))

            before_other_users = db.query(Job).filter(
                Job.owner_user_id.in_([JOSHUA_USER_ID, ALONSO_USER_ID]),
                Job.external_id == "1213000",
            ).count()

            async def exact_posting(self, ids, *, require_all=True):
                assert "1213000" in ids
                return [_official_hpe_raw()]

            monkeypatch.setattr(WorkdayAdapter, "fetch_exact_public_ids", exact_posting)
            response = client.post(f"/api/jobs/{job_id}/recheck")
            assert response.status_code == 200, response.text

            db.refresh(job)
            db.refresh(application)
            db.refresh(prior_resume)
            db.refresh(override)
            assert response.json()["official_status"] == "open"
            assert job.id == job_id
            assert db.query(Job).filter(
                Job.owner_user_id == owner,
                Job.external_id == "1213000",
            ).count() == 1
            assert job.description and len(job.description) > 500
            assert "Python" in job.requirements and "C++" in job.requirements
            assert "learning new technologies" in job.preferred_qualifications
            assert job.location == "Tlaquepaque, Jalisco, Mexico"
            assert job.remote_type == "Hybrid"
            assert job.official_apply_url.rstrip("/") == HPE_URL.rstrip("/")
            assert job.official_status == "open" and job.verification_status == "verified"
            assert job.last_verified_at is not None
            assert job.candidate_job_override.force_apply_now is True
            assert override.force_apply_now is True
            assert application.id == application_id
            assert application.status == "Applied"
            assert application.notes == "Existing application note must survive recheck."
            assert application.submitted_resume_id == resume_id
            assert prior_resume.id == resume_id and prior_resume.status == "compiled"

            analysis = job.analysis
            assert analysis is not None
            assert {"python", "c++"}.issubset(
                {skill.casefold() for skill in analysis.matched_skills}
            )
            assert "java" in job.requirements.casefold()
            assert db.query(Job).filter(
                Job.owner_user_id.in_([JOSHUA_USER_ID, ALONSO_USER_ID]),
                Job.external_id == "1213000",
            ).count() == before_other_users

            resume_profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == owner))
            assert resume_profile is not None
            generated = generate_local_content(job, resume_profile)

        monkeypatch.setattr(
            "app.main.generate_resume",
            lambda *_args: (generated, "\\documentclass{article}", b"%PDF-1.4"),
        )
        response = client.post(f"/api/jobs/{job_id}/resume/generate")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "compiled"


def test_resume_generation_still_rejects_a_genuinely_empty_posting(request):
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            job = _adapter().normalize_job({
                **_official_hpe_raw(),
                "jobDescription": "",
                "jobRequirements": "",
            })
            data = job.to_dict()
            data.update({
                "owner_user_id": settings.effective_primary_user_id,
                "description": "",
                "requirements": "",
                "preferred_qualifications": "",
                "external_id": "hpe-empty-test-requisition",
            })
            record = Job(**data)
            db.add(record)
            db.commit()
            job_id = record.id
            request.addfinalizer(lambda: _cleanup_job(job_id))
        response = client.post(f"/api/jobs/{job_id}/resume/generate")
        assert response.status_code == 422
        assert response.json()["detail"] == "This job has no description to analyze."


def _cleanup_job(job_id: int) -> None:
    with SessionLocal() as db:
        _remove_test_job(db, job_id)
