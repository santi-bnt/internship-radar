from types import SimpleNamespace

import pytest

from app.services.tailoring_plan import SkillMatchState, build_tailoring_plan


def candidate(user_id: str, *, skills: list[str], projects: list[dict] | None = None):
    return SimpleNamespace(
        user_id=user_id,
        skills_json=skills,
        projects_json=projects or [],
        coursework_json=[],
        experience_json=[],
    )


def job(owner_user_id: str, *, title: str, requirements: str, preferred: str = "", description: str = ""):
    return SimpleNamespace(
        id=41,
        owner_user_id=owner_user_id,
        title=title,
        company="Example Corp",
        requirements=requirements,
        preferred_qualifications=preferred,
        description=description,
    )


def mapping(plan, normalized_requirement: str):
    return next(
        item for item in plan.requirement_evidence
        if item.requirement.normalized_requirement == normalized_requirement
    )


def test_software_api_and_embedded_jobs_produce_different_plans():
    profile = candidate(
        "user-a",
        skills=["Python", "REST APIs", "C", "FreeRTOS", "UART"],
        projects=[{
            "name": "Integrated Platform", "is_resume_eligible": True,
            "technologies": ["Python", "REST APIs", "C", "FreeRTOS", "UART"],
            "bullets": [
                "Designed and implemented a service API with validated endpoints.",
                "Integrated embedded controllers with UART communication and tested timing behavior.",
            ],
        }],
    )
    software = build_tailoring_plan(
        job("user-a", title="Software API Intern", requirements="Python and RESTful APIs required."),
        profile,
        owner_user_id="user-a",
    )
    embedded = build_tailoring_plan(
        job("user-a", title="Embedded Firmware Intern", requirements="C, FreeRTOS, and UART are required."),
        profile,
        owner_user_id="user-a",
    )

    assert software.required_skills != embedded.required_skills
    assert "Software Engineering" in software.role_categories
    assert "Embedded / Firmware" in embedded.role_categories
    assert mapping(software, "REST APIs").match_state == SkillMatchState.ALIAS_MATCH
    assert mapping(embedded, "FreeRTOS").match_state == SkillMatchState.EXACT_MATCH


def test_student_researcher_keeps_research_engineering_category_alongside_software():
    plan = build_tailoring_plan(
        job(
            "user-a", title="Student Researcher, BS/MS",
            requirements="Research engineering, Python, and algorithms are required.",
        ),
        candidate("user-a", skills=["Python"]),
        owner_user_id="user-a",
    )

    assert "Research / Research Engineering" in plan.role_categories
    assert "RESEARCH_ENGINEERING" in plan.role_category_codes


def test_java_is_not_matched_without_verified_java_evidence():
    plan = build_tailoring_plan(
        job("user-a", title="Software Intern", requirements="Java is required."),
        candidate("user-a", skills=["Python", "C++"]),
        owner_user_id="user-a",
    )

    result = mapping(plan, "Java")
    assert result.match_state == SkillMatchState.NOT_FOUND
    assert result.matched_candidate_evidence == []


def test_restful_apis_alias_matches_verified_rest_apis():
    plan = build_tailoring_plan(
        job("user-a", title="Backend Intern", requirements="Experience with RESTful APIs is required."),
        candidate("user-a", skills=["REST APIs"]),
        owner_user_id="user-a",
    )

    result = mapping(plan, "REST APIs")
    assert result.match_state == SkillMatchState.ALIAS_MATCH
    assert result.confidence == "medium"
    assert result.matched_candidate_evidence[0].claim == "REST APIs"


def test_semantic_support_still_requires_verified_evidence():
    plan = build_tailoring_plan(
        job("user-a", title="Backend Intern", requirements="API Development is required."),
        candidate("user-a", skills=["REST APIs"]),
        owner_user_id="user-a",
    )

    result = mapping(plan, "API Development")
    assert result.match_state == SkillMatchState.SUPPORTED_SEMANTIC_MATCH
    assert result.matched_candidate_evidence[0].source.value == "skill"


def test_unsupported_cybersecurity_requirements_are_not_found():
    plan = build_tailoring_plan(
        job(
            "user-a", title="Security Engineering Intern",
            requirements="Cybersecurity, Threat Modeling, and SIEM experience are required.",
        ),
        candidate("user-a", skills=["Python", "REST APIs"]),
        owner_user_id="user-a",
    )

    for skill in ("Cybersecurity", "Threat Modeling", "SIEM"):
        assert mapping(plan, skill).match_state == SkillMatchState.NOT_FOUND


def test_two_users_cannot_share_or_read_each_others_evidence():
    alpha = candidate("alpha", skills=["Python"], projects=[{
        "name": "Alpha API", "is_resume_eligible": True,
        "technologies": ["Python", "REST APIs"],
        "bullets": ["Developed a Python API.", "Tested request handling."],
    }])
    beta = candidate("beta", skills=["C"], projects=[{
        "name": "Beta Firmware", "is_resume_eligible": True,
        "technologies": ["C", "FreeRTOS"],
        "bullets": ["Implemented firmware tasks.", "Tested board behavior."],
    }])
    alpha_plan = build_tailoring_plan(
        job("alpha", title="Backend Intern", requirements="Python and REST APIs required."),
        alpha, owner_user_id="alpha",
    )
    beta_plan = build_tailoring_plan(
        job("beta", title="Firmware Intern", requirements="C and FreeRTOS required."),
        beta, owner_user_id="beta",
    )

    assert alpha_plan.owner_user_id == "alpha"
    assert beta_plan.owner_user_id == "beta"
    assert {item.project_name for item in alpha_plan.project_evaluations} == {"Alpha API"}
    assert {item.project_name for item in beta_plan.project_evaluations} == {"Beta Firmware"}
    assert all("Alpha" not in evidence.source_name for item in beta_plan.requirement_evidence for evidence in item.matched_candidate_evidence)
    with pytest.raises(ValueError, match="different user"):
        build_tailoring_plan(job("beta", title="Firmware Intern", requirements="C required."), alpha, owner_user_id="beta")
