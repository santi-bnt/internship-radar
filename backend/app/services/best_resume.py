from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.api import ResumeCertificationItem, ResumeCourseItem, ResumeExperienceItem
from app.services.resume_generation import (
    _item_value,
    _project_bullets,
    sanitize_resume_text,
    validate_generated_resume,
)
from app.services.resume_skills import select_job_skills
from app.services.resume_studio import (
    build_studio_job,
    generate_studio_content,
    rank_studio_projects,
)


PROFILE_VERSION_FIELDS = (
    "full_name", "email", "phone", "location", "linkedin_url", "github_url",
    "headline", "summary", "education_json", "skills_json", "experience_json",
    "projects_json", "coursework_json", "certifications_json", "languages_json",
    "language_credentials_json", "github_evidence_json", "forbidden_claims_json",
)


class BestResumePlan(BaseModel):
    candidate_id: str
    selected_experiences: list[str] = Field(default_factory=list)
    selected_projects: list[str] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    selected_certifications: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    bullet_decisions: dict[str, list[str]] = Field(default_factory=dict)
    project_decisions: list[dict[str, Any]] = Field(default_factory=list)
    excluded_projects: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    profile_version: str


def best_resume_profile_version(profile: Any) -> str:
    snapshot = {
        key: getattr(profile, key, None)
        for key in PROFILE_VERSION_FIELDS
    }
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def best_resume_profile_snapshot(profile: Any) -> dict[str, Any]:
    """Freeze the candidate evidence used by a queued immutable version."""
    return {key: getattr(profile, key, None) for key in PROFILE_VERSION_FIELDS}


def _source_project_label(item: dict[str, Any]) -> str:
    metadata = " ".join(
        str(item.get(key) or "")
        for key in (
            "project_origin", "project_context", "context", "setting", "scope_type",
            "experience_type", "project_type", "project_type_label", "type",
        )
    ).casefold()
    if item.get("is_academic") is True or re.search(r"\b(academic|coursework|classroom|laboratory|lab exercise)\b", metadata):
        return "Academic Project"
    if item.get("is_personal") is True or re.search(r"\b(personal|independent|side project)\b", metadata):
        return "Personal Project"
    return ""


def _experience_rows(profile: Any) -> list[tuple[str, dict[str, Any], list[str]]]:
    selected: list[tuple[str, dict[str, Any], list[str]]] = []
    for item in getattr(profile, "experience_json", []) or []:
        if not isinstance(item, dict) or item.get("verified") is not True or item.get("is_professional") is False:
            continue
        kind = " ".join(str(item.get(key) or "") for key in ("type", "experience_type", "relationship_type", "context")).casefold()
        if re.search(r"\b(academic project|personal project|class project|course project|partner collaboration)\b", kind):
            continue
        title = _item_value(item, "title", "role")
        organization = _item_value(item, "organization", "company")
        raw_bullets = item.get("bullets") or item.get("highlights") or []
        if isinstance(raw_bullets, str):
            raw_bullets = [raw_bullets]
        bullets = [sanitize_resume_text(value) for value in raw_bullets if isinstance(value, str) and value.strip()][:3]
        if not title or not organization or not bullets:
            continue
        key = f"{title} — {organization}"
        selected.append((key, item, bullets))
    return selected[:2]


def _course_rows(profile: Any, selected_skills: set[str], certification_names: set[str]) -> list[dict[str, Any]]:
    sources = list(getattr(profile, "coursework_json", []) or [])
    education = getattr(profile, "education_json", []) or []
    institution = _item_value(education[0], "institution", "school") if education and isinstance(education[0], dict) else ""
    if education and isinstance(education[0], dict):
        sources.extend(education[0].get("coursework", []) or [])
    rows: dict[str, tuple[int, dict[str, Any]]] = {}
    skills = {skill.casefold() for skill in selected_skills}
    for item in sources:
        if isinstance(item, str):
            record: dict[str, Any] = {"name": item, "institution": institution}
        elif isinstance(item, dict):
            record = item
        else:
            continue
        if record.get("verified") is False:
            continue
        name = _item_value(record, "name", "title", "course_name")
        if not name or name.casefold() in certification_names:
            continue
        areas = record.get("areas") or record.get("skills") or []
        if isinstance(areas, str):
            areas = [areas]
        areas_text = " ".join(str(value) for value in areas).casefold()
        overlap = sum(1 for skill in skills if skill and skill in areas_text)
        if not overlap and skills:
            overlap = sum(1 for skill in skills if skill and skill in name.casefold())
        rows[name] = (overlap, {
            "name": name,
            "institution": _item_value(record, "institution", "issuer", "organization") or institution,
            "issued": _item_value(record, "issued", "date", "issue_date"),
            "areas": [str(value) for value in areas if str(value).strip()][:4] if isinstance(areas, list) else [],
        })
    ranked = sorted(rows.values(), key=lambda row: (-row[0], row[1]["name"].casefold()))
    return [row[1] for row in ranked[:4]]


def _certification_rows(profile: Any, selected_skills: set[str]) -> list[dict[str, Any]]:
    skill_keys = {skill.casefold() for skill in selected_skills}
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in getattr(profile, "certifications_json", []) or []:
        if not isinstance(item, dict) or item.get("verified") is not True:
            continue
        if _item_value(item, "type").casefold() == "language":
            continue
        name = _item_value(item, "name", "title")
        if not name:
            continue
        supported = item.get("supported_skills") or item.get("relevant_skills") or item.get("skills") or []
        overlap = sum(1 for value in supported if str(value).casefold() in skill_keys) if isinstance(supported, list) else 0
        if overlap == 0:
            continue
        candidates.append((overlap, {
            "name": name,
            "issuer": _item_value(item, "issuer", "organization", "issuing_organization"),
            "date": _item_value(item, "date", "issued", "issue_date"),
            "url": _item_value(item, "url", "credential_url"),
        }))
    candidates.sort(key=lambda item: (-item[0], item[1]["name"].casefold()))
    return [item for _, item in candidates[:4]]


def build_best_resume_plan(profile: Any, candidate_id: str) -> BestResumePlan:
    project_rankings = rank_studio_projects(profile, "general", limit=4)
    selected_projects = [item for item in project_rankings if item["selected"]]
    selected_names = [item["name"] for item in selected_projects]
    job = build_studio_job("general")
    skills = select_job_skills(job, profile, "Software Engineering", selected_project_names=set(selected_names))
    selected_skills = list(skills["selected_skills"])
    certifications = _certification_rows(profile, set(selected_skills))
    coursework = _course_rows(profile, set(selected_skills), {item["name"].casefold() for item in certifications})
    experiences = _experience_rows(profile)
    section_order = ["summary", "education"]
    if experiences:
        section_order.append("experience")
    if selected_projects:
        section_order.append("projects")
    section_order.append("skills")
    if certifications:
        section_order.append("certifications")
    if coursework:
        section_order.append("coursework")
    if getattr(profile, "languages_json", None):
        section_order.append("languages")
    bullet_decisions = {
        key: bullets
        for key, _, bullets in experiences
    }
    for project in selected_projects:
        source = profile.projects_json[project["source_index"]]
        bullet_decisions[project["name"]] = _project_bullets(source)
    project_decisions = [
        {
            "name": item["name"], "decision": "SELECT", "score": item["score"],
            "reason": item["reasons"][0], "evidence": item["reasons"][1:],
            "project_type": item["project_type"],
        }
        for item in selected_projects
    ]
    excluded = [
        {
            "name": item["name"], "decision": "EXCLUDE", "score": item["score"],
            "reason": item["reasons"][0], "evidence": item["reasons"][1:],
        }
        for item in project_rankings if not item["selected"]
    ]
    return BestResumePlan(
        candidate_id=candidate_id,
        selected_experiences=[key for key, _, _ in experiences],
        selected_projects=selected_names,
        selected_skills=selected_skills,
        selected_coursework=[item["name"] for item in coursework],
        selected_certifications=[item["name"] for item in certifications],
        section_order=section_order,
        bullet_decisions=bullet_decisions,
        project_decisions=project_decisions,
        excluded_projects=excluded,
        profile_version=best_resume_profile_version(profile),
    )


def build_best_resume_job(profile: Any, candidate_id: str, plan: BestResumePlan | None = None) -> Any:
    """Construct the synthetic, profile-scoped job context for Best Resume."""
    job = build_studio_job("general")
    job.title = "Best Resume"
    job.area = "General Engineering"
    job.resume_target = "best_resume"
    job.portfolio_profile_id = "best"
    job.candidate_id = candidate_id
    job.best_resume_plan = plan or build_best_resume_plan(profile, candidate_id)
    return job


def generate_best_resume_content(job: Any, profile: Any) -> Any:
    candidate_id = str(getattr(job, "candidate_id", "") or "")
    plan = getattr(job, "best_resume_plan", None)
    if not isinstance(plan, BestResumePlan):
        plan = build_best_resume_plan(profile, candidate_id)
    if plan.candidate_id != candidate_id or plan.profile_version != best_resume_profile_version(profile):
        raise ValueError("BestResumePlan does not match the current candidate profile snapshot.")

    base = generate_studio_content(
        build_studio_job("general"), profile, minimum_projects=0, project_limit=4,
    )
    project_sources = {
        _item_value(item, "name", "title"): item
        for item in (getattr(profile, "projects_json", []) or [])
        if isinstance(item, dict) and _item_value(item, "name", "title")
    }
    projects = []
    for assessment in rank_studio_projects(profile, "general", limit=4):
        if not assessment["selected"]:
            continue
        source = project_sources.get(assessment["name"], {})
        project = next((item for item in base.projects if item.name == assessment["name"]), None)
        if project is None:
            continue
        projects.append(project.model_copy(update={"project_type_label": _source_project_label(source)}))

    experience_rows = _experience_rows(profile)
    experience = [ResumeExperienceItem(
        title=_item_value(source, "title", "role"),
        organization=_item_value(source, "organization", "company"),
        location=_item_value(source, "location"),
        dates=_item_value(source, "dates", "date"),
        bullets=bullets,
    ) for _, source, bullets in experience_rows]
    certification_rows = _certification_rows(profile, set(plan.selected_skills))
    coursework_rows = _course_rows(
        profile,
        set(plan.selected_skills),
        {item["name"].casefold() for item in certification_rows},
    )
    summary = _best_summary(profile, plan, projects, experience)
    content = base.model_copy(update={
        "target_role": "Best Resume",
        "classification": "General Engineering",
        "summary": summary,
        "experience": experience,
        "projects": projects,
        "certifications": [ResumeCertificationItem(**item) for item in certification_rows],
        "coursework": [ResumeCourseItem(**item) for item in coursework_rows],
        "section_order": plan.section_order,
        "tailoring_plan": {"mode": "BEST_RESUME", "best_resume_plan": plan.model_dump(mode="json")},
        "tailoring_trace": {
            "mode": "BEST_RESUME",
            "candidate_id": candidate_id,
            "profile_version": plan.profile_version,
            "project_scores": {item["name"]: item["score"] for item in plan.project_decisions},
        },
        "why_this_version": [
            "Evidence-weighted general resume; not tailored to a specific job.",
            "Selected projects are scored for technical depth, scope, integration, ownership, outcome, and portfolio breadth.",
            "Only skills backed by selected candidate evidence are included.",
        ],
    })
    return validate_generated_resume(content, profile, job, minimum_projects=0)


def _best_summary(profile: Any, plan: BestResumePlan, projects: list[Any], experience: list[Any]) -> str:
    headline = sanitize_resume_text(getattr(profile, "headline", ""))
    focus = ", ".join(plan.selected_skills[:3]) or "verified technical skills"
    if projects:
        names = [item["name"] for item in plan.project_decisions]
        domains = list(dict.fromkeys(
            domain
            for item in rank_studio_projects(profile, "general", limit=3)
            if item["name"] in names
            for domain in item["domains"]
        ))[:3]
        breadth = ", ".join(domains) or "software and engineering systems"
        summary = (
            f"{headline} with hands-on project work in {focus}. Selected work spans {breadth} and demonstrates practical implementation "
            "across complementary technical areas. The portfolio emphasizes documented engineering decisions, system behavior, and "
            "functional outcomes while keeping each claim grounded in the candidate's project evidence."
        )
    elif experience:
        organizations = ", ".join(item.organization for item in experience[:2])
        summary = (
            f"{headline} with experience at {organizations}. Applies {focus} to technical responsibilities documented in the candidate profile. "
            "This general resume presents verified education, selected work evidence, and technical capabilities without tailoring claims "
            "to a particular employer or job description."
        )
    else:
        degree = _item_value((getattr(profile, "education_json", []) or [{}])[0], "degree")
        summary = (
            f"{headline} pursuing {degree}, with verified technical skills in {focus}. This general resume presents the candidate's education, "
            "supported capabilities, and available portfolio evidence without assigning job-specific qualifications or inventing experience. "
            "Project and certification claims are limited to the evidence stored in the candidate profile."
        )
    words = summary.split()
    if len(words) < 35:
        summary += " The resume preserves the candidate's stated background and avoids unsupported metrics or employer relationships."
    return summary
