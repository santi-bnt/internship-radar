from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models import Application, GeneratedResume, Job, JobAnalysis
from app.security.application_session_token import (
    ApplicationTokenError,
    create_application_session_token,
    validate_application_session_token,
)
from app.services.application_assistant import (
    classify_question,
    detect_portal,
    validate_application_consistency,
)
from conftest import security_headers


def _create_ready_job() -> tuple[int, int]:
    marker = str(datetime.now(timezone.utc).timestamp()).replace(".", "")
    with SessionLocal() as db:
        job = Job(
            owner_user_id="internship-radar-primary",
            source_name="apply-assistant-test",
            source_url=f"https://example.wd1.myworkdayjobs.com/source/{marker}",
            company="Example Workday Company",
            title="Software Engineering Intern",
            location="Monterrey, Mexico",
            country="Mexico",
            description="Build verified software systems.",
            requirements="Currently enrolled student with Python and Git.",
            apply_url=f"https://example.wd1.myworkdayjobs.com/en-US/jobs/job/Software-Intern_REQ-{marker}",
            official_apply_url=f"https://example.wd1.myworkdayjobs.com/en-US/jobs/job/Software-Intern_REQ-{marker}",
            official_status="open",
            verification_status="verified",
            raw_data_hash=f"apply-assistant-{marker}",
            status="active",
        )
        db.add(job)
        db.flush()
        job.analysis = JobAnalysis(
            technical_score=90,
            academic_score=90,
            eligibility_score=90,
            level_score=90,
            logistics_score=90,
            freshness_score=90,
            overall_score=90,
            effective_score=90,
            recommendation="Apply Today",
            eligibility_status="ELIGIBLE",
            recommended_resume_type="Software / SDE",
            explanation="Eligible test job.",
        )
        resume = GeneratedResume(
            user_id="internship-radar-primary",
            job_id=job.id,
            version=1,
            status="compiled",
            target_role=job.title,
            tailored_content_json={
                "projects": [
                    {
                        "name": "Internship Radar",
                        "bullets": ["Built a FastAPI and Next.js internship platform."],
                    }
                ]
            },
            latex_source="\\documentclass{article}\\begin{document}Test\\end{document}",
            selected_skills=["Python", "Git"],
            content_hash=f"resume-{marker}",
        )
        db.add(resume)
        db.commit()
        return job.id, resume.id


def _application_profile_payload() -> dict[str, object]:
    return {
        "full_name": "Candidate Example",
        "professional_email": "candidate@example.com",
        "phone": "+52 555 555 5555",
        "address_line1": "Verified address",
        "city": "Monterrey",
        "state": "Nuevo Leon",
        "postal_code": "64000",
        "country": "Mexico",
        "university": "Tecnologico de Monterrey",
        "degree": "B.S. in Robotics and Digital Systems Engineering",
        "field_of_study": "Robotics and Digital Systems Engineering",
        "gpa": 93.05,
        "gpa_scale": 100,
        "education_start_date": "2024-08-01",
        "expected_graduation_date": "2028-06-30",
        "languages_json": ["English — Fluent", "Spanish — Native"],
        "linkedin_url": "https://www.linkedin.com/in/example-candidate/",
        "github_url": "https://github.com/candidate",
        "skills_json": ["Python", "Git"],
        "projects_json": [
            {
                "name": "Internship Radar",
                "description": "FastAPI and Next.js internship platform.",
                "bullets": ["Built a FastAPI and Next.js internship platform."],
            }
        ],
        "work_experience_json": [],
        "academic_project_workaround_allowed": False,
    }


def test_readiness_binds_exact_compiled_resume_and_rejects_other_jobs_and_users():
    with TestClient(app, headers=security_headers()) as client:
        assert client.put("/api/application-profile", json=_application_profile_payload()).status_code == 200
        job_id, original_id = _create_ready_job()
        other_job_id, other_resume_id = _create_ready_job()
        with SessionLocal() as db:
            newer = GeneratedResume(
                user_id="internship-radar-primary", job_id=job_id, version=2, status="compiled",
                target_role="Software Engineering Intern", selected_skills=["Python", "Git"],
                content_hash=f"newer-for-{job_id}",
            )
            foreign = GeneratedResume(
                user_id="another-candidate", job_id=job_id, version=3, status="compiled",
                target_role="Software Engineering Intern", content_hash=f"foreign-for-{job_id}",
            )
            queued = GeneratedResume(
                user_id="internship-radar-primary", job_id=job_id, version=4, status="queued",
                target_role="Software Engineering Intern", content_hash=f"queued-for-{job_id}",
            )
            db.add_all([newer, foreign, queued])
            db.commit()
            foreign_id, queued_id = foreign.id, queued.id

        response = client.get(f"/api/jobs/{job_id}/application-readiness?resume_version_id={original_id}")
        assert response.status_code == 200, response.text
        assert response.json()["resume"]["id"] == original_id
        for invalid_id in (foreign_id, queued_id, other_resume_id):
            rejected = client.get(f"/api/jobs/{job_id}/application-readiness?resume_version_id={invalid_id}")
            assert rejected.status_code == 404, rejected.text
        assert other_job_id != job_id


def test_session_token_is_scoped_expires_and_rejects_tampering():
    token, _ = create_application_session_token(
        session_id=42,
        owner_user_id="internship-radar-primary",
        nonce="valid-nonce-value-123456",
        now=1000,
        lifetime_seconds=60,
    )
    claims = validate_application_session_token(
        token,
        required_scope="read_application_profile",
        now=1030,
    )
    assert claims.session_id == 42
    assert claims.owner_user_id == "internship-radar-primary"
    try:
        validate_application_session_token(token, now=1061)
    except ApplicationTokenError as exc:
        assert "expired" in str(exc).lower()
    else:
        raise AssertionError("Expired token was accepted")
    try:
        validate_application_session_token(f"{token[:-1]}x", now=1030)
    except ApplicationTokenError:
        pass
    else:
        raise AssertionError("Tampered token was accepted")


def test_question_matching_and_consistency_safety():
    classification = classify_question("Are you legally authorized to work in the United States?")
    assert classification["question_key"] == "US_WORK_AUTHORIZATION"
    assert classification["confidence"] >= 0.9
    assert classification["policy"] == "AUTO_FILL_REVIEW_REQUIRED"
    mexico_sponsorship = classify_question("Will you require sponsorship to work in Mexico?")
    assert mexico_sponsorship["question_key"] == "SPONSORSHIP_CURRENT_COUNTRY"
    assert mexico_sponsorship["policy"] == "AUTO_FILL_REVIEW_REQUIRED"
    assert classify_question("Please explain something unusual")["policy"] == "MANUAL_ONLY"
    assert detect_portal("https://intel.wd1.myworkdayjobs.com/en-US/jobs/job/JR0286207")["portal_type"] == "WORKDAY"
    issues = validate_application_consistency(
        {
            "contact": {"professional_email": "candidate@example.com", "city": "Monterrey"},
            "education": {"start_date": "2024-08-01", "expected_graduation_date": "2028-06-30"},
            "languages": ["English — Fluent", "Spanish — Native"],
            "verified_skills": ["Python"],
        },
        {
            "email": "wrong@example.com",
            "education_start_year": "2002",
            "address_line1": "same",
            "address_line2": "same",
            "skills": ["Invented Skill"],
            "resume_version_id": 99,
            "languages": ["English — Basic"],
            "work_authorization_answers": {"US_WORK_AUTHORIZATION": ["Yes", "No"]},
        },
        expected_resume_version_id=18,
    )
    assert {issue["code"] for issue in issues} >= {
        "MISMATCH_EMAIL",
        "BAD_EDUCATION_START_YEAR",
        "DUPLICATED_ADDRESS",
        "UNVERIFIED_SKILLS",
        "WRONG_RESUME",
        "INCONSISTENT_LANGUAGE_FLUENCY",
        "CONTRADICTORY_WORK_AUTHORIZATION",
    }


def test_application_session_lifecycle_requires_confirmation_and_preserves_resume(monkeypatch):
    monkeypatch.setattr("app.main.compile_latex", lambda source: b"%PDF-1.4 prepared")
    with TestClient(app, headers=security_headers()) as client:
        profile_response = client.put("/api/application-profile", json=_application_profile_payload())
        assert profile_response.status_code == 200, profile_response.text
        job_id, resume_id = _create_ready_job()

        readiness = client.get(f"/api/jobs/{job_id}/application-readiness")
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["checks"][0]["ready"] is True
        assert readiness.json()["ready"] is True
        assert readiness.json()["selected_experience"][0]["name"] == "Internship Radar"
        assert readiness.json()["selected_skills"] == ["Python", "Git"]
        assert readiness.json()["portfolio"]["filename"].endswith(".pdf")

        launched = client.post(
            f"/api/jobs/{job_id}/application-sessions",
            json={"resume_version_id": resume_id},
        )
        assert launched.status_code == 201, launched.text
        launch = launched.json()
        token = launch["application_session_token"]
        session_id = launch["session"]["id"]
        assert launch["session"]["selected_projects_json"] == launch["session"]["project_experience_json"]
        assert launch["session"]["selected_skills_json"] == ["Python", "Git"]
        assert launch["session"]["generated_experience_text"].startswith(
            "Academic and personal software projects; not professional employment."
        )
        assert launch["session"]["resume_version_id"] == resume_id
        assert "Internship Radar" in launch["session"]["project_match_reasons_json"]
        extension_headers = {"Authorization": f"Bearer {token}"}

        extension_payload = client.get(
            "/api/extension/application-session",
            headers=extension_headers,
        )
        assert extension_payload.status_code == 200, extension_payload.text
        assert extension_payload.json()["resume"]["id"] == resume_id
        assert extension_payload.json()["resume"]["filename"] == launch["session"]["resume_filename"]
        assert extension_payload.json()["resume"]["selected_skills"] == ["Python", "Git"]
        assert extension_payload.json()["resume"]["latex_source"] == ""
        assert extension_payload.json()["portfolio"]["id"] == launch["session"]["portfolio_version_id"]
        assert extension_payload.json()["ai_settings"]["ai_mode"] == "BALANCED"
        assert extension_payload.json()["final_submit_policy"] == "MANUAL_ONLY"

        agent_plan = client.post(
            "/api/extension/application-session/agent/analyze",
            headers=extension_headers,
            json={
                "page_url": "https://example.wd1.myworkdayjobs.com/apply",
                "page_title": "Application",
                "fields": [
                    {
                        "field_id": "major",
                        "raw_label": "Field of study",
                        "control_type": "select",
                        "available_options": ["Mechanical Engineering", "Computer Science", "Electrical Engineering", "Other"],
                        "required": True,
                    },
                    {"field_id": "city", "raw_label": "Current city", "required": True},
                    {"field_id": "disability", "raw_label": "Voluntary self identification of disability"},
                    {"field_id": "signature", "raw_label": "Electronic signature"},
                ],
            },
        )
        assert agent_plan.status_code == 200, agent_plan.text
        resolutions = {item["field_id"]: item for item in agent_plan.json()["resolutions"]}
        assert resolutions["major"]["selected_option"] == "Computer Science"
        assert resolutions["major"]["match_type"] == "RELATED_PROGRAMMING"
        assert resolutions["major"]["requires_review"] is True
        assert resolutions["city"]["selected_value"] == "Monterrey"
        assert resolutions["disability"]["action"] == "MANUAL_ONLY"
        assert resolutions["signature"]["action"] == "MANUAL_ONLY"
        assert agent_plan.json()["final_submit_policy"] == "MANUAL_ONLY"

        approved = client.post(
            "/api/extension/application-session/agent/approve-mapping",
            headers=extension_headers,
            json={
                "portal": "WORKDAY",
                "canonical_field": "FIELD_OF_STUDY",
                "canonical_value": "Robotics and Digital Systems Engineering",
                "portal_option": "Computer Science",
                "match_type": "RELATED_PROGRAMMING",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["portal"] == "WORKDAY"

        prepared_portfolio = client.get(
            "/api/extension/application-session/portfolio.pdf",
            headers=extension_headers,
        )
        assert prepared_portfolio.status_code == 200, prepared_portfolio.text
        assert prepared_portfolio.content.startswith(b"%PDF")
        assert launch["session"]["portfolio_filename"] in prepared_portfolio.headers["content-disposition"]

        unauthorized = client.get(
            "/api/extension/application-session",
            headers={"Authorization": "Bearer invalid"},
        )
        assert unauthorized.status_code == 401

        progress = client.patch(
            "/api/extension/application-session/progress",
            headers=extension_headers,
            json={
                "status": "WAITING_FOR_USER",
                "current_step": "Application Questions",
                "fields_filled_count": 8,
                "observed_fields": {"email": "candidate@example.com", "resume_version_id": resume_id},
            },
        )
        assert progress.status_code == 200, progress.text
        assert progress.json()["status"] == "WAITING_FOR_USER"

        # Reloading the extension or navigating to the next portal page reads
        # the same server-side session instead of starting over.
        resumed = client.get(
            "/api/extension/application-session",
            headers=extension_headers,
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["session"]["current_step"] == "Application Questions"
        assert resumed.json()["session"]["fields_filled_count"] == 8
        assert resumed.json()["session"]["resume_version_id"] == resume_id

        forbidden_submit_status = client.patch(
            "/api/extension/application-session/progress",
            headers=extension_headers,
            json={"status": "SUBMITTED_BY_USER"},
        )
        assert forbidden_submit_status.status_code == 409

        confirmation = client.post(
            "/api/extension/application-session/confirm-answer",
            headers=extension_headers,
            json={
                "question_key": "US_WORK_AUTHORIZATION",
                "normalized_question": "Are you legally authorized to work in the United States?",
                "answer": "No",
                "answer_type": "text",
                "classification_confidence": 1,
            },
        )
        assert confirmation.status_code == 200, confirmation.text
        assert confirmation.json()["sensitivity"] == "AUTO_FILL_REVIEW_REQUIRED"

        submitted = client.post(
            "/api/extension/application-session/confirm-submitted",
            headers=extension_headers,
            json={
                "confirmation_text": "Thank you for applying. Your application has been received.",
                "confirmation_url": "https://example.wd1.myworkdayjobs.com/confirmation",
            },
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "SUBMITTED_BY_USER"

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            application = db.scalar(
                select(Application).where(Application.application_session_id == session_id)
            )
            assert job is not None and job.status == "applied"
            assert application is not None
            assert application.status == "Applied"
            assert application.submitted_resume_id == resume_id
            assert db.get(GeneratedResume, resume_id) is not None

        revoked = client.get(
            "/api/extension/application-session",
            headers=extension_headers,
        )
        assert revoked.status_code == 401
