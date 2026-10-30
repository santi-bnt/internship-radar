from __future__ import annotations

import json
import uuid

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import (
    AIDecisionLog,
    ApplicationProfile,
    ApplicationSession,
    CandidateCorrectionMemory,
    GeneratedResume,
)
from app.schemas.api import AgentFieldInput, FieldResolution
from app.services.ai_privacy import CandidateAIContextBuilder, PrivacyPolicyEngine
from app.services.ai_router import AIMode, AIProvider, AIProviderError, AIRouter
from app.services.application_agent import ApplicationAgent, DropdownMatcher, FreeTextAnswerGenerator, QuestionClassifier


def test_degree_matching_prefers_programming_and_preserves_canonical_value():
    canonical = "Robotics and Digital Systems Engineering"
    match = DropdownMatcher().match_degree(
        canonical,
        ["Mechanical Engineering", "Computer Science", "Electrical Engineering", "Finance", "Other"],
    )
    assert match.selected_option == "Computer Science"
    assert match.match_type == "RELATED_PROGRAMMING"
    assert match.requires_review is True
    assert canonical == "Robotics and Digital Systems Engineering"


def test_degree_matching_exact_robotics_and_safe_other_fallback():
    robotics = DropdownMatcher().match_degree(
        "Robotics and Digital Systems Engineering",
        ["Mechanical Engineering", "Robotics Engineering", "Computer Science"],
    )
    assert robotics.selected_option == "Robotics Engineering"
    assert robotics.match_type == "STRONG_EQUIVALENT"
    assert robotics.requires_review is False
    unrelated = DropdownMatcher().match_degree(
        "Robotics and Digital Systems Engineering",
        ["Chemistry", "History", "Finance", "Other"],
    )
    assert unrelated.selected_option == "Other"
    assert unrelated.match_type == "OTHER"
    assert unrelated.requires_review is True


def test_free_text_uses_verified_python_evidence_and_character_limit():
    result = FreeTextAnswerGenerator().generate(
        "Describe your Python experience.",
        {
            "verified_skills": ["Python", "FastAPI", "automation", "REST APIs"],
            "verified_projects": [{
                "project_id": "project_radar",
                "name": "Internship Radar",
                "verified_skills": ["Python", "FastAPI", "automation", "REST APIs"],
                "verified_facts": ["Built a FastAPI service that automates internship analysis."],
            }],
        },
        {"title": "AI Automation Intern", "company": "Example", "requirements": "Python automation APIs"},
        maxlength=180,
    )
    assert "Internship Radar" in result.answer
    assert "Python" in result.answer
    assert result.evidence_project_ids == ["project_radar"]
    assert result.character_count <= 180
    assert not any(term in result.answer for term in ("Power Automate", "LangChain", "Copilot", "CUDA", "AWS"))


def test_external_payload_removes_identifiers_and_prohibited_data():
    safe, included, redacted = PrivacyPolicyEngine().prepare_external_payload({
        "email": "santiago@example.com",
        "phone": "+52 33 1234 5678",
        "address": "Private street 123",
        "password": "never-send",
        "mfa_code": "123456",
        "government_id": "CURP ABCD123456EFGH78",
        "question": "Describe Python experience for candidate@example.com",
        "verified_skills": ["Python", "FastAPI"],
    })
    serialized = json.dumps(safe)
    assert "santiago@example.com" not in serialized
    assert "candidate@example.com" not in serialized
    assert "+52" not in serialized
    assert "never-send" not in serialized
    assert "123456" not in serialized
    assert "ABCD123456EFGH78" not in serialized
    assert safe["verified_skills"] == ["Python", "FastAPI"]
    assert included
    assert any("email" in item for item in redacted)


class _RouterResult(BaseModel):
    answer: str


class _Provider(AIProvider):
    def __init__(self, name: str, location: str, *, result: str | None = None):
        self.name = name
        self.execution_location = location
        self.result = result
        self.contexts: list[dict] = []

    def complete(self, *, instructions: str, context: dict, schema: type[_RouterResult]):
        self.contexts.append(context)
        if self.result is None:
            raise AIProviderError(f"{self.name} unavailable")
        return schema(answer=self.result)


def test_ai_router_local_only_and_redacted_balanced_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ai_max_attempts", 1)
    local = _Provider("local-test", "LOCAL", result="local")
    external = _Provider("external-test", "EXTERNAL", result="external")
    result, provider, location = AIRouter(
        AIMode.BALANCED, local_provider=local, external_provider=external
    ).complete(
        instructions="Return structured output.", context={"verified_skills": ["Python"]},
        schema=_RouterResult, purpose="test",
    )
    assert (result.answer, provider, location) == ("local", "local-test", "LOCAL")
    assert external.contexts == []

    failing_local = _Provider("local-test", "LOCAL")
    audits: list[dict] = []
    result, provider, location = AIRouter(
        AIMode.BALANCED, local_provider=failing_local, external_provider=external
    ).complete(
        instructions="Return structured output.",
        context={"email": "private@example.com", "verified_skills": ["Python"]},
        schema=_RouterResult, purpose="safe fallback", audit=audits.append,
    )
    assert (result.answer, provider, location) == ("external", "external-test", "EXTERNAL")
    assert "email" not in external.contexts[-1]
    assert audits and any("email" in item for item in audits[0]["fields_redacted"])

    with pytest.raises(AIProviderError, match="LOCAL_ONLY"):
        AIRouter(
            AIMode.LOCAL_ONLY,
            local_provider=_Provider("local-test", "LOCAL"),
            external_provider=external,
        ).complete(
            instructions="Return structured output.", context={"verified_skills": ["Python"]},
            schema=_RouterResult, purpose="test",
        )


def test_application_agent_context_and_corrections_are_owner_scoped():
    init_db()
    marker = uuid.uuid4().hex
    owners = [f"santiago-{marker}", f"joshua-{marker}"]
    with SessionLocal() as db:
        sessions = []
        for owner, city, skill, project in (
            (owners[0], "Zapopan", "Python", "Internship Radar"),
            (owners[1], "Guadalajara", "C++", "Joshua Robot"),
        ):
            profile = ApplicationProfile(
                owner_user_id=owner,
                full_name=owner,
                professional_email=f"{owner}@example.com",
                city=city,
                state="Jalisco",
                country="Mexico",
                field_of_study="Robotics and Digital Systems Engineering",
                skills_json=[skill],
                projects_json=[{"name": project, "technologies": [skill], "bullets": [f"Built {project} with {skill}."]}],
            )
            resume = GeneratedResume(
                user_id=owner, version=1, status="compiled", target_role="Engineering Intern",
                selected_skills=[skill], content_hash=f"{owner}-resume",
            )
            db.add_all([profile, resume])
            db.flush()
            session = ApplicationSession(
                owner_user_id=owner,
                company="Example",
                portal_type="WORKDAY",
                application_url="https://example.wd1.myworkdayjobs.com/apply",
                resume_version_id=resume.id,
                profile_snapshot_json={
                    "contact": {"full_name": owner, "professional_email": f"{owner}@example.com", "city": city, "state": "Jalisco", "country": "Mexico"},
                    "education": {"field_of_study": "Robotics and Digital Systems Engineering"},
                    "work_authorization": {"work_authorized_countries": ["Mexico"]},
                },
                job_snapshot_json={"title": "Engineering Intern", "company": "Example", "requirements": skill},
                selected_projects_json=[{"name": project}],
                selected_skills_json=[skill],
            )
            db.add(session)
            db.flush()
            sessions.append(session)
        db.add(CandidateCorrectionMemory(
            owner_user_id=owners[0], scope="USER_GLOBAL", canonical_field="CURRENT_CITY",
            old_value_json={"value": "Guadalajara"}, corrected_value_json={"value": "Zapopan"}, verified=True,
        ))
        db.commit()

        field = AgentFieldInput(field_id="city", raw_label="Current city", required=True)
        first = ApplicationAgent().analyze(db, sessions[0], [field])
        second = ApplicationAgent().analyze(db, sessions[1], [field])
        assert first.resolutions[0].selected_value == "Zapopan"
        assert second.resolutions[0].selected_value == "Guadalajara"
        question = AgentFieldInput(field_id="project", raw_label="Describe a relevant project", control_type="textarea")
        first_answer = ApplicationAgent().analyze(db, sessions[0], [question]).resolutions[0]
        second_answer = ApplicationAgent().analyze(db, sessions[1], [question]).resolutions[0]
        assert "Internship Radar" in first_answer.selected_value
        assert "Joshua Robot" not in first_answer.selected_value
        assert "Joshua Robot" in second_answer.selected_value
        assert "Internship Radar" not in second_answer.selected_value
        first_context = CandidateAIContextBuilder().build(db.scalar(select(ApplicationProfile).where(ApplicationProfile.owner_user_id == owners[0])))
        second_context = CandidateAIContextBuilder().build(db.scalar(select(ApplicationProfile).where(ApplicationProfile.owner_user_id == owners[1])))
        assert "Joshua Robot" not in json.dumps(first_context)
        assert "Internship Radar" not in json.dumps(second_context)
        assert "@example.com" not in json.dumps(first_context) + json.dumps(second_context)
        logs = list(db.scalars(select(AIDecisionLog).where(AIDecisionLog.owner_user_id.in_(owners))))
        assert {log.owner_user_id for log in logs} == set(owners)


def test_model_cannot_request_final_submit_action():
    with pytest.raises(ValidationError):
        FieldResolution(
            field_id="submit", canonical_field="FINAL_SUBMIT", question_category="UNKNOWN",
            action="SUBMIT", confidence=1, reason_summary="Unsafe model output.",
        )


def test_question_specific_evidence_ranks_above_generic_job_overlap():
    context = {
        "verified_skills": ["Python", "C++", "FreeRTOS"],
        "verified_projects": [
            {"project_id": "api", "name": "Backend", "verified_skills": ["Python"], "verified_facts": ["Built a Python API."]},
            {"project_id": "motor", "name": "Motor Controller", "verified_skills": ["C++", "FreeRTOS"], "verified_facts": ["Implemented a FreeRTOS control task."]},
        ],
    }
    answer = FreeTextAnswerGenerator().generate(
        "Describe your C++ experience", context,
        {"title": "Software Intern", "company": "Example", "requirements": "Python"},
    )
    assert "Motor Controller" in answer.answer
    assert "C++" in answer.answer
    assert "Backend" not in answer.answer
    assert answer.evidence_project_ids == ["motor"]
    unsupported = FreeTextAnswerGenerator().generate("Describe your Java experience", context, {})
    assert unsupported.answer == ""
    assert unsupported.confidence < 0.8


def test_open_ended_questions_are_not_misclassified_as_profile_facts():
    classifier = QuestionClassifier()
    assert classifier.classify("Describe a project you completed at university")[0] == "EXPERIENCE_QUESTION"
    assert classifier.classify("Describe your Python experience")[0] == "EXPERIENCE_QUESTION"
    assert classifier.classify("Why are you interested in this role given your degree")[0] == "JOB_SPECIFIC_TEXT"
    assert classifier.classify("University")[0] == "PROFILE_FACT"
    assert classifier.classify("Describe your experience with export control")[0] == "LEGAL_COMPLIANCE"


def test_question_skill_matching_does_not_confuse_java_javascript_or_c_cpp():
    match = FreeTextAnswerGenerator._mentions
    assert not match("Describe JavaScript experience", "Java")
    assert not match("Describe C++ experience", "C")
    assert not match("Describe robotics experience", "C")
    assert match("Describe C++ experience", "C++")
    assert match("Describe your experience with Python.", "Python")
