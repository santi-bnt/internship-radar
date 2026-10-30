from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.application_selection import (
    ACADEMIC_EXPERIENCE_COMPANY,
    ACADEMIC_EXPERIENCE_DISCLAIMER,
    ACADEMIC_EXPERIENCE_TITLE,
    build_application_selection,
)
from app.services.resume_generation import (
    CANONICAL_DEGREE,
    CANONICAL_GPA,
    CANONICAL_GRADUATION,
    CANONICAL_EMAIL,
    CANONICAL_GITHUB,
    CANONICAL_INSTITUTION,
    CANONICAL_LINKEDIN,
    CANONICAL_LOCATION,
    CANONICAL_NAME,
    CANONICAL_PHONE,
    CANONICAL_STUDENT_TITLE,
    generate_local_content,
)
from app.services.resume_skills import build_verified_skill_registry
from app.services.seed import INTERNSHIP_RADAR_PROJECT, VERIFIED_RESUME_PROJECTS


def profile() -> SimpleNamespace:
    projects = [INTERNSHIP_RADAR_PROJECT, *VERIFIED_RESUME_PROJECTS]
    skills = list(dict.fromkeys(
        technology
        for project in projects
        for technology in project.get("technologies", [])
    ))
    return SimpleNamespace(
        full_name=CANONICAL_NAME,
        email=CANONICAL_EMAIL,
        phone=CANONICAL_PHONE,
        location=CANONICAL_LOCATION,
        linkedin_url=CANONICAL_LINKEDIN,
        github_url=CANONICAL_GITHUB,
        headline=CANONICAL_STUDENT_TITLE,
        summary="Canonical verified engineering profile.",
        skills_json=skills,
        projects_json=projects,
        coursework_json=[],
        experience_json=[],
        certifications_json=[],
        languages_json=["English — Fluent", "Spanish — Native"],
        forbidden_claims_json=["Power Automate", "GitHub Copilot", "CUDA", "C#"],
        education_json=[{
            "institution": CANONICAL_INSTITUTION,
            "degree": CANONICAL_DEGREE,
            "location": CANONICAL_LOCATION,
            "graduation": CANONICAL_GRADUATION,
            "gpa": CANONICAL_GPA,
        }],
    )


def job(title: str, description: str) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        company="Example",
        area="",
        location="Mexico",
        description=description,
        requirements=description,
        preferred_qualifications="",
        analysis=SimpleNamespace(
            missing_required_skills=[],
            matched_skills=[],
            overall_score=90,
        ),
    )


def selection(title: str, description: str) -> tuple[dict, SimpleNamespace, SimpleNamespace]:
    current_profile = profile()
    current_job = job(title, description)
    content = generate_local_content(current_job, current_profile)
    resume = SimpleNamespace(
        tailored_content_json=content.model_dump(mode="json"),
        selected_skills=content.selected_skills,
        job_skill_matches=[item.model_dump(mode="json") for item in content.job_skill_matches],
    )
    return build_application_selection(current_job, current_profile, resume), current_profile, resume


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        (
            "AI Workflow Automation Intern",
            "Build Python workflow automation with REST APIs, databases, SQL, Git, and AI integration using the OpenAI API.",
            ["Internship Radar - AI Resume Tailoring Platform", "SkiliAir Air Quality Monitoring System"],
        ),
        (
            "Full Stack Software Intern",
            "Develop a full-stack web application using TypeScript, Next.js, Python, FastAPI, PostgreSQL, MySQL, REST APIs, Git, and Docker.",
            ["Internship Radar - AI Resume Tailoring Platform", "SkiliAir Air Quality Monitoring System"],
        ),
        (
            "Embedded Firmware Intern",
            "Develop C and C++ firmware with FreeRTOS, microcontrollers, UART, GPIO, PWM, interrupts, and hardware debugging.",
            ["FreeRTOS Event-Driven System", "MATT Web-Controlled Writing Robot"],
        ),
    ],
)
def test_role_specific_experience_selects_strongest_resume_projects(title, description, expected):
    result, _, _ = selection(title, description)
    names = [project["name"] for project in result["selected_projects"]]
    assert names[:2] == expected


def test_fpga_and_cpp_roles_prioritize_direct_evidence():
    fpga, _, _ = selection(
        "FPGA Digital Design Intern",
        "Design Verilog and SystemVerilog RTL for FPGA, PWM, GPIO, UART, testbenches, and waveform validation.",
    )
    cpp, _, _ = selection(
        "C++ Software Engineering Intern",
        "Implement C++ object-oriented software using data structures, algorithms, and priority queues.",
    )
    assert fpga["selected_projects"][0]["name"] == "Intel MAX 10 Robotic Arm Controller"
    assert cpp["selected_projects"][0]["name"] == "Stock Exchange Matching Engine"
    assert [item["name"] for item in fpga["selected_projects"]] != [
        item["name"] for item in cpp["selected_projects"]
    ]
    assert fpga["selected_skills"] != cpp["selected_skills"]


def test_selection_is_verified_resume_consistent_and_excludes_unverified_requests():
    result, current_profile, resume = selection(
        "Automation Software Intern",
        "Use Python, REST APIs, Git, Microsoft Power Automate, GitHub Copilot, CUDA, and C#.",
    )
    registry = build_verified_skill_registry(current_profile)
    assert set(result["selected_skills"]) <= set(registry)
    assert set(result["selected_skills"]) <= set(resume.selected_skills)
    assert not {"Power Automate", "GitHub Copilot", "CUDA", "C#"} & set(result["selected_skills"])
    resume_projects = {
        project["name"] for project in resume.tailored_content_json["projects"]
    }
    assert {project["name"] for project in result["selected_projects"]} <= resume_projects
    for project in result["selected_projects"]:
        resume_project = next(
            item for item in resume.tailored_content_json["projects"]
            if item["name"] == project["name"]
        )
        assert set(project["application_bullets"]) <= set(resume_project["bullets"])


def test_user_edits_are_validated_and_preserved_in_generated_snapshot():
    default, current_profile, resume = selection(
        "Full Stack Intern",
        "Build TypeScript and Next.js interfaces with Python, FastAPI, PostgreSQL, REST APIs, and Git.",
    )
    chosen_project = default["selected_projects"][0]["name"]
    chosen_skills = default["selected_skills"][:2]
    edited = build_application_selection(
        job("Full Stack Intern", "TypeScript Next.js Python FastAPI PostgreSQL REST APIs Git"),
        current_profile,
        resume,
        selected_project_names=[chosen_project],
        selected_skills=[*chosen_skills, "CUDA"],
    )
    assert [project["name"] for project in edited["selected_projects"]] == [chosen_project]
    assert edited["selected_skills"] == chosen_skills
    assert any("CUDA" in warning for warning in edited["selection_warnings"])
    assert edited["generated_experience_text"].startswith(ACADEMIC_EXPERIENCE_DISCLAIMER)
    assert ACADEMIC_EXPERIENCE_TITLE == "Student Software Developer — Academic & Personal Projects"
    assert ACADEMIC_EXPERIENCE_COMPANY == "Tecnológico de Monterrey / Personal Projects"


def test_changing_job_description_changes_project_ranking_and_reasons():
    embedded, _, _ = selection("Engineering Intern", "C FreeRTOS firmware UART PWM interrupts")
    web, _, _ = selection("Engineering Intern", "TypeScript Next.js FastAPI PostgreSQL REST APIs full-stack web")
    assert embedded["selected_projects"][0]["name"] != web["selected_projects"][0]["name"]
    assert embedded["project_match_reasons"] != web["project_match_reasons"]
