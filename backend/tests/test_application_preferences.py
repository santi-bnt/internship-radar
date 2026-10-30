from copy import deepcopy
from types import SimpleNamespace

from app.services.application_agent import FreeTextAnswerGenerator, QuestionClassifier
from app.services.application_selection import ApplicationSkillSelector


def test_application_skills_keep_cv_and_add_only_relevant_verified_profile_skills():
    profile = SimpleNamespace(
        skills_json=["Python", "SQL", "C++"], projects_json=[], coursework_json=[],
        certifications_json=[], forbidden_claims_json=[],
    )
    job = SimpleNamespace(title="Backend Intern", company="Example", description="Python and SQL APIs. Java preferred.", requirements="Python SQL", preferred_qualifications="Java", area="")
    resume = SimpleNamespace(selected_skills=["Python"], job_skill_matches=[])
    old_cv_skills = deepcopy(resume.selected_skills)
    result = ApplicationSkillSelector().select(job, profile, resume, [])
    assert result.selected_skills == ["Python", "SQL"]
    assert "C++" not in result.selected_skills
    assert "Java" not in result.selected_skills
    assert "explicitly requested" in result.skill_match_reasons["SQL"]
    assert resume.selected_skills == old_cv_skills
    other_profile = SimpleNamespace(skills_json=["C++"], projects_json=[], coursework_json=[], certifications_json=[], forbidden_claims_json=[])
    assert ApplicationSkillSelector().select(job, other_profile, resume, []).selected_skills == []


def test_general_experience_uses_most_relevant_project_without_claiming_employment():
    context = {
        "verified_skills": ["Python", "SQL", "C++"], "verified_work_experience": [],
        "verified_projects": [
            {"project_id": "motor", "name": "Motor Controller", "verified_skills": ["C++"], "verified_facts": ["Built an encoder control task."]},
            {"project_id": "backend", "name": "Backend Platform", "verified_skills": ["Python", "SQL"], "verified_facts": ["Built a Python API with SQL persistence."]},
        ],
    }
    assert QuestionClassifier().classify("Experience")[0] == "EXPERIENCE_QUESTION"
    assert QuestionClassifier().classify("Years of professional experience")[3] == "MANUAL_ONLY"
    assert QuestionClassifier().classify("Describe your professional experience")[3] == "MANUAL_ONLY"
    assert QuestionClassifier().classify("Describe your academic or professional experience")[0] == "EXPERIENCE_QUESTION"
    answer = FreeTextAnswerGenerator().generate("Experience", context, {"title": "Backend Intern", "requirements": "Python SQL"})
    assert "Backend Platform" in answer.answer
    assert "academic/personal project" in answer.answer
    assert answer.evidence_project_ids == ["backend"]
    assert "Motor Controller" not in answer.answer
