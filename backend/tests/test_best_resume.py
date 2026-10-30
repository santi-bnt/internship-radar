from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import GeneratedResume, ResumeProfile
from app.services.best_resume import (
    BestResumePlan,
    _certification_rows,
    _course_rows,
    build_best_resume_job,
    build_best_resume_plan,
    generate_best_resume_content,
)
from app.services.resume_generation import generate_local_content, generate_resume, render_latex
from app.security.identity import ALONSO_EMAIL, ALONSO_USER_ID, JOSHUA_EMAIL, JOSHUA_USER_ID
from conftest import security_headers
from test_kospie_resumes import candidate


def test_best_resume_can_select_four_relevant_courses_and_certifications():
    courses = [
        {"name": f"Python Course {index}", "skills": ["Python"], "verified": True}
        for index in range(4)
    ]
    certifications = [
        {"name": f"Python Certificate {index}", "skills": ["Python"], "verified": True}
        for index in range(4)
    ]
    profile = SimpleNamespace(
        coursework_json=courses,
        education_json=[],
        certifications_json=certifications,
    )

    selected_courses = _course_rows(profile, {"Python"}, set())
    selected_certifications = _certification_rows(profile, {"Python"})

    assert len(selected_courses) == 4
    assert len(selected_certifications) == 4


def test_best_resume_is_general_evidence_weighted_and_not_job_tailored():
    profile = candidate()
    plan = build_best_resume_plan(profile, "santiago")
    job = build_best_resume_job(profile, "santiago", plan)

    content = generate_local_content(job, profile)

    assert content.target_role == "Best Resume"
    assert content.application_type == "PROFILE_PORTFOLIO"
    assert content.classification == "General Engineering"
    assert len(content.projects) == 4
    assert len(plan.selected_projects) == 4
    assert [project.name for project in content.projects] == plan.selected_projects
    assert not content.job_skill_matches or all(item.match_type == "contextual" for item in content.job_skill_matches)
    assert content.tailoring_plan["mode"] == "BEST_RESUME"
    assert content.tailoring_trace["candidate_id"] == "santiago"
    assert all(project.name in plan.bullet_decisions for project in content.projects)


def test_best_resume_prefers_one_page_and_removes_certifications_before_projects(monkeypatch):
    from app.services.resume_generation import fit_resume_to_one_page

    profile = candidate()
    plan = build_best_resume_plan(profile, "santiago")
    job = build_best_resume_job(profile, "santiago", plan)
    content = generate_local_content(job, profile)
    original_projects = [project.name for project in content.projects]
    original_certification_count = len(content.certifications)
    assert len(original_projects) == 4
    assert original_certification_count >= 2

    rendered = []
    def render(fitted, _profile):
        rendered.append(fitted.model_copy(deep=True))
        return "latex"

    monkeypatch.setattr("app.services.resume_generation.render_latex", render)
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda _: (b"two-pages", 2, 90)
        if len(rendered[-1].certifications) > 1 else (b"one-page", 1, 90),
    )

    fitted, _, pdf, _ = fit_resume_to_one_page(content, job, profile)

    assert pdf == b"one-page"
    assert fitted.quality_checks.one_page is True
    assert [project.name for project in fitted.projects] == original_projects
    assert len(fitted.certifications) < original_certification_count
    assert fitted.tailoring_plan["best_resume_plan"]["selected_certifications"] == [
        item.name for item in fitted.certifications
    ]


def test_best_resume_only_uses_stored_experience_and_verifies_project_labels():
    profile = candidate()
    profile.experience_json = [
        {"title": "Robotics Lab Assistant", "organization": "Tec Lab", "type": "academic project",
         "bullets": ["This academic project is not professional experience."]},
        {"title": "Software Intern", "organization": "Example Co", "verified": True,
         "type": "employment", "bullets": ["Maintained a Python data workflow."]},
    ]
    project = profile.projects_json[0]
    project["project_origin"] = "academic coursework"
    plan = build_best_resume_plan(profile, "santiago")
    content = generate_best_resume_content(build_best_resume_job(profile, "santiago", plan), profile)

    assert [item.title for item in content.experience] == ["Software Intern"]
    labeled = next(item for item in content.projects if item.name == project["name"])
    assert labeled.project_type_label == "Academic Project"
    assert "Academic Project" in render_latex(content, profile)
    assert "Robotics Lab Assistant" not in render_latex(content, profile)


def test_best_resume_does_not_invent_skills_metrics_or_employer_relationships():
    profile = candidate()
    profile.forbidden_claims_json = ["QuantumCryptography", "increased performance by 80%", "Intel employee"]
    plan = build_best_resume_plan(profile, "santiago")
    content = generate_best_resume_content(build_best_resume_job(profile, "santiago", plan), profile)
    rendered = render_latex(content, profile)

    assert "QuantumCryptography" not in content.selected_skills
    assert "increased performance by 80%" not in rendered
    assert "Intel employee" not in rendered


def test_best_resume_supports_candidates_with_fewer_than_two_projects():
    profile = candidate()
    profile.projects_json = [deepcopy(profile.projects_json[0])]
    plan = build_best_resume_plan(profile, "santiago")
    content = generate_best_resume_content(build_best_resume_job(profile, "santiago", plan), profile)
    assert len(content.projects) == 1


def test_best_resume_plan_is_bound_to_candidate_and_profile_snapshot():
    profile = candidate()
    plan = build_best_resume_plan(profile, "santiago")
    job = build_best_resume_job(profile, "joshua", plan)
    with pytest.raises(ValueError, match="does not match"):
        generate_best_resume_content(job, profile)

    job = build_best_resume_job(profile, "santiago", plan)
    profile.headline = "Changed candidate headline"
    with pytest.raises(ValueError, match="does not match"):
        generate_best_resume_content(job, profile)


def test_best_resume_versions_load_without_regeneration_and_are_immutable(monkeypatch):
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda source: (b"%PDF-1.4", 1, 85.0),
    )
    with TestClient(app, headers=security_headers()) as client:
        initial = client.get("/api/best-resume/versions")
        assert initial.status_code == 200, initial.text
        first = client.post("/api/best-resume/versions")
        assert first.status_code == 200, first.text
        assert first.json()["tailored_content_json"]["quality_checks"]["one_page"] is True
        snapshot = deepcopy(first.json()["tailored_content_json"])

        # Loading the existing resume is read-only; generation must be explicit.
        monkeypatch.setattr("app.main.generate_resume", lambda *args: pytest.fail("unexpected regeneration"))
        listed = client.get("/api/best-resume/versions")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == first.json()["id"]
        assert listed.json()[0]["tailored_content_json"] == snapshot

        monkeypatch.undo()
        monkeypatch.setattr(
            "app.services.resume_generation._compile_latex_artifact",
            lambda source: (b"%PDF-1.4", 1, 85.0),
        )
        second = client.post("/api/best-resume/versions")
        assert second.status_code == 200, second.text
        assert second.json()["version"] == first.json()["version"] + 1
        history = client.get("/api/best-resume/versions").json()
        old = next(item for item in history if item["id"] == first.json()["id"])
        assert old["tailored_content_json"] == snapshot


def test_best_resume_versions_are_candidate_scoped(monkeypatch):
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda source: (b"%PDF-1.4", 1, 85.0),
    )
    with TestClient(app, headers=security_headers()) as client:
        created = client.post("/api/best-resume/versions")
        assert created.status_code == 200, created.text
        for email, subject in ((JOSHUA_EMAIL, JOSHUA_USER_ID), (ALONSO_EMAIL, ALONSO_USER_ID)):
            headers = security_headers(email, subject=subject)
            response = client.get("/api/best-resume/versions", headers=headers)
            assert response.status_code in (200, 422), response.text
            assert response.status_code == 422 or created.json()["id"] not in {
                item["id"] for item in response.json()
            }


def test_profile_changes_mark_latest_best_resume_stale_without_regenerating(monkeypatch):
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda source: (b"%PDF-1.4", 1, 85.0),
    )
    with TestClient(app, headers=security_headers()) as client:
        created = client.post("/api/best-resume/versions")
        assert created.status_code == 200, created.text
        with SessionLocal() as db:
            profile = db.query(ResumeProfile).filter_by(user_id="internship-radar-primary").one()
            original_headline = profile.headline
            profile.headline = f"{profile.headline} Updated"
            db.commit()

        monkeypatch.setattr("app.main.generate_resume", lambda *args: pytest.fail("profile read regenerated CV"))
        versions = client.get("/api/best-resume/versions")
        assert versions.status_code == 200, versions.text
        latest = next(item for item in versions.json() if item["id"] == created.json()["id"])
        assert latest["is_stale"] is True
        assert latest["tailored_content_json"] == created.json()["tailored_content_json"]
        with SessionLocal() as db:
            profile = db.query(ResumeProfile).filter_by(user_id="internship-radar-primary").one()
            profile.headline = original_headline
            db.commit()


def test_queued_best_resume_uses_the_same_pipeline_and_one_page_validation(monkeypatch):
    queued = []
    monkeypatch.setattr(
        "app.main.resume_generation_queue.enqueue",
        lambda owner_user_id, work: queued.append((owner_user_id, work)),
    )
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda source: (b"%PDF-1.4", 1, 85.0),
    )
    with TestClient(app, headers=security_headers()) as client:
        pending = client.post("/api/best-resume/versions")
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == "queued"
        assert len(queued) == 1
        assert queued[0][0] == "internship-radar-primary"

        # The queue runs only after the request returns; its worker executes the standard
        # generate_resume -> fit -> render -> validate pipeline.
        queued[0][1]()
        versions = client.get("/api/best-resume/versions").json()
        generated = next(item for item in versions if item["id"] == pending.json()["id"])
        assert generated["status"] == "compiled"
        assert generated["tailored_content_json"]["quality_checks"]["one_page"] is True

        with SessionLocal() as db:
            record = db.get(GeneratedResume, generated["id"])
            snapshot = record.company_profile["profile_snapshot"]
            plan = BestResumePlan.model_validate(record.company_profile["best_resume_plan"])
            profile = SimpleNamespace(**snapshot)
            job = build_best_resume_job(profile, record.user_id, plan)
            direct, _, _ = generate_resume(job, profile, record.id)
        assert direct.model_dump() == generated["tailored_content_json"]
