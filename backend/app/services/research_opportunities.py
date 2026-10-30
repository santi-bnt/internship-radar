from __future__ import annotations

from typing import Any, Iterable

from app.services.resume_generation import (
    RESEARCH_SEMANTIC_GROUPS,
    generate_local_content,
    research_focus_groups,
    sanitize_resume_text,
)
from app.services.resume_skills import build_verified_skill_registry

UNVERIFIED_TECHNOLOGIES = (
    "ROS", "SLAM", "CUDA", "PyTorch", "Gazebo", "Isaac Sim",
    "Reinforcement Learning", "Machine Learning",
)


def _set_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    a = {sanitize_resume_text(item).lower() for item in left if sanitize_resume_text(item)}
    b = {sanitize_resume_text(item).lower() for item in right if sanitize_resume_text(item)}
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def resume_similarity(candidate: Any, previous: dict[str, Any]) -> float:
    current_projects = [item.name for item in candidate.projects]
    previous_projects = [str(item.get("name", "")) for item in previous.get("projects", [])]
    project_score = _set_similarity(current_projects, previous_projects)
    skill_score = _set_similarity(candidate.selected_skills, previous.get("selected_skills", []))
    area_score = _set_similarity(
        candidate.opportunity_research_areas,
        previous.get("opportunity_research_areas", []),
    )
    order_score = 1.0 if candidate.section_order == previous.get("section_order", []) else 0.5
    return round((project_score * 0.4 + skill_score * 0.35 + area_score * 0.15 + order_score * 0.1) * 100, 1)


def analyze_research_opportunity(profile: Any, opportunity: Any, recent_resumes: Iterable[Any] = ()) -> dict[str, Any]:
    opportunity.resume_target = "robotics_research"
    content = generate_local_content(opportunity, profile)
    registry = build_verified_skill_registry(profile)
    context = " ".join([
        sanitize_resume_text(getattr(opportunity, "description", "")),
        " ".join(getattr(opportunity, "research_areas", []) or []),
        sanitize_resume_text(getattr(opportunity, "lab", "")),
    ])
    focus = list(dict.fromkeys(
        [sanitize_resume_text(item) for item in (getattr(opportunity, "research_areas", []) or []) if sanitize_resume_text(item)]
        + research_focus_groups(context)
    ))[:10]
    lowered = context.lower()
    unverified = [
        item for item in UNVERIFIED_TECHNOLOGIES
        if item.lower() in lowered and item not in registry
    ]
    selected = set(content.selected_skills)
    strong = [item.skill for item in content.job_skill_matches if item.score >= 30]
    relevant = [item for item in content.selected_skills if item not in strong]
    not_selected = [
        skill for skill in registry
        if skill not in selected
    ][:12]
    source_projects = {
        sanitize_resume_text(item.get("name") or item.get("title")): item
        for item in profile.projects_json if isinstance(item, dict)
    }
    projects = []
    for item in content.projects:
        raw = str(source_projects.get(item.name, {})).lower()
        matches = []
        for group in research_focus_groups(context):
            if any(term in raw for term in RESEARCH_SEMANTIC_GROUPS[group]):
                matches.append(group)
        projects.append({
            "name": item.name,
            "match": round(item.relevance_score),
            "why": ", ".join(matches[:3]) or "Verified robotics-research technical evidence",
        })
    best_similarity = 0.0
    similar_id = None
    for resume in recent_resumes:
        score = resume_similarity(content, resume.tailored_content_json or {})
        if score > best_similarity:
            best_similarity, similar_id = score, resume.id
    confidence = min(100.0, 45 + len(focus) * 5 + len(strong) * 3)
    return {
        "research_focus": focus,
        "verified_matches": content.selected_skills,
        "unverified_keywords": unverified,
        "recommended_projects": projects,
        "recommended_skills": {"strong_match": strong, "relevant": relevant, "not_selected": not_selected},
        "research_interests": content.research_interests,
        "confidence": confidence,
        "similarity": best_similarity,
        "similar_resume_id": similar_id,
        "reuse_message": (
            "High similarity with existing Robotics Research CV. Minor tailoring recommended."
            if best_similarity >= 85 else "A tailored research variant is recommended."
        ),
    }
