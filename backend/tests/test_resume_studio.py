from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.resume_generation import generate_local_content, generate_structured_content, render_latex
from app.services.resume_studio import STUDIO_PROFILES, analyze_studio_profile, build_studio_job, rank_studio_projects
from app.security.identity import JOSHUA_EMAIL, JOSHUA_USER_ID
from app.security.rate_limit import sensitive_operation
from conftest import security_headers
from test_kospie_resumes import candidate


@pytest.mark.parametrize("profile_id", STUDIO_PROFILES)
def test_studio_preserves_evidence_languages_and_links(profile_id):
    profile = candidate()
    original = deepcopy(profile.__dict__)
    job = build_studio_job(profile_id)
    content = generate_structured_content(job, profile)
    assert content == generate_local_content(job, profile)
    assert content.application_type == "PROFILE_PORTFOLIO"
    assert len(content.projects) == 4
    assert "English - Fluent" in content.languages
    assert "English - IELTS Academic 6.5" not in content.languages
    assert "Spanish - Native" in content.languages
    assert not any("A2" in language for language in content.languages)
    source = {item["name"]: item for item in profile.projects_json}
    for project in content.projects:
        assert project.bullets == source[project.name]["bullets"]
    latex = render_latex(content, profile)
    assert r"\sectionheading{Projects}" in latex
    assert r"\sectionheading{Languages}" in latex
    assert "linkedin.com/in/example-candidate" in latex
    assert profile.__dict__ == original


def test_general_is_neutral_and_prioritizes_complete_complementary_systems():
    ranking = rank_studio_projects(candidate(), "general")
    assert all(item["components"]["relevance"] == 70 for item in ranking)
    selected = {item["name"] for item in ranking if item["selected"]}
    assert selected == {
        "Intel MAX 10 Robotic Arm Controller", "MATT Web-Controlled Writing Robot",
        "SkiliAir Air Quality Monitoring System", "Internship Radar - AI Resume Tailoring Platform",
    }
    assert all(len(item["reasons"]) == 5 for item in ranking)


def test_technology_list_alone_cannot_prove_depth_or_integration():
    profile = candidate()
    simple = {"name": "Short classroom exercise", "project_type": "laboratory practice",
              "bullets": ["Built an LED exercise.", "Tested one output."], "technologies": []}
    profile.projects_json = [simple]
    first = rank_studio_projects(profile, "embedded")[0]
    simple["technologies"] = ["ESP32", "FreeRTOS", "PWM", "Interrupts", "Sensors", "FPGA", "Python"]
    second = rank_studio_projects(profile, "embedded")[0]
    for key in ("technical_depth", "system_integration", "ownership", "outcome_completeness"):
        assert second["components"][key] == first["components"][key]
    assert second["project_type"] == "laboratory_practice"
    assert second["components"]["classroom_exercise_penalty"] > 0
    assert not second["selected"]


def test_role_relevance_changes_without_inflating_depth():
    profile = candidate()
    software = {item["name"]: item for item in rank_studio_projects(profile, "software")}
    embedded = {item["name"]: item for item in rank_studio_projects(profile, "embedded")}
    radar = "Internship Radar - AI Resume Tailoring Platform"
    assert software[radar]["components"]["relevance"] > embedded[radar]["components"]["relevance"]
    assert software[radar]["components"]["technical_depth"] == embedded[radar]["components"]["technical_depth"]
    fpga = rank_studio_projects(profile, "fpga")
    assert next(item for item in fpga if item["name"] == "Intel MAX 10 Robotic Arm Controller")["components"]["relevance"] == 100


def test_portfolio_selection_penalizes_redundant_capabilities():
    profile = candidate()
    radar = deepcopy(next(item for item in profile.projects_json if item["name"] == "Internship Radar - AI Resume Tailoring Platform"))
    radar["name"] = "Second equivalent resume platform"
    profile.projects_json.append(radar)
    ranking = rank_studio_projects(profile, "general")
    selected = {item["name"] for item in ranking if item["selected"]}
    assert len(selected) == 4
    assert not {radar["name"], "Internship Radar - AI Resume Tailoring Platform"} <= selected
    assert "MATT Web-Controlled Writing Robot" in selected


def test_generation_has_abuse_controls_but_analysis_does_not():
    assert sensitive_operation("/api/resume-studio/resumes", "POST").key == "resume"
    assert sensitive_operation("/api/resume-studio/analysis", "GET") is None


def test_insufficient_evidence_and_unknown_profile_are_actionable():
    profile = candidate()
    profile.projects_json = []
    assert analyze_studio_profile(profile, "general")["can_generate"] is False
    with pytest.raises(ValueError, match="at least two"):
        generate_local_content(build_studio_job("general"), profile)
    with pytest.raises(ValueError, match="Unknown resume profile"):
        rank_studio_projects(profile, "invalid")


def test_api_versions_are_private_profile_specific_and_immutable(monkeypatch):
    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact",
                        lambda source: (b"%PDF-1.4", 1, 85.0))
    with TestClient(app, headers=security_headers()) as client:
        assert client.get("/api/resume-studio/profiles", headers={"x-user-identity": "invalid"}).status_code in (401, 403)
        assert client.get("/api/resume-studio/analysis?profile_id=invalid").status_code == 422
        assert len(client.get("/api/resume-studio/profiles").json()) == 5
        assert client.get("/api/resume-studio/analysis").json()["can_generate"] is True
        first = client.post("/api/resume-studio/resumes")
        assert first.status_code == 200, first.text
        snapshot = deepcopy(first.json()["tailored_content_json"])
        second = client.post("/api/resume-studio/resumes")
        assert second.status_code == 200, second.text
        assert second.json()["version"] == first.json()["version"] + 1
        history = client.get("/api/resume-studio/resumes").json()
        assert next(item for item in history if item["id"] == first.json()["id"])["tailored_content_json"] == snapshot
        assert client.get("/api/resume-studio/resumes?profile_id=embedded").json() == []
        other = security_headers(JOSHUA_EMAIL, subject=JOSHUA_USER_ID)
        assert client.get("/api/resume-studio/resumes", headers=other).json() == []
        assert client.get(first.json()["tex_url"], headers=other).status_code == 404
        assert client.get(first.json()["tex_url"]).status_code == 200


def test_api_records_failed_versions_without_claiming_success(monkeypatch):
    def fail(*args):
        raise RuntimeError("Unable to compile CV")
    monkeypatch.setattr("app.main.generate_resume", fail)
    with TestClient(app, headers=security_headers()) as client:
        result = client.post("/api/resume-studio/resumes?profile_id=robotics")
        assert result.status_code == 422
        version = client.get("/api/resume-studio/resumes?profile_id=robotics").json()[0]
        assert version["status"] == "failed"
        assert version["generation_error"] == "Unable to compile CV"
