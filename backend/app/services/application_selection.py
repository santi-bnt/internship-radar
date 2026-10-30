from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models import ApplicationProfile, GeneratedResume, Job
from app.services.resume_generation import classify_job, score_project_for_job
from app.services.resume_skills import build_verified_skill_registry, canonicalize_skill, _occurrences


ACADEMIC_EXPERIENCE_DISCLAIMER = (
    "Academic and personal software projects; not professional employment."
)
ACADEMIC_EXPERIENCE_TITLE = "Student Software Developer — Academic & Personal Projects"
ACADEMIC_EXPERIENCE_COMPANY = "Tecnológico de Monterrey / Personal Projects"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).casefold()).strip()


def _job_text(job: Job) -> str:
    return " ".join(
        _clean(getattr(job, field, ""))
        for field in (
            "title",
            "company",
            "area",
            "description",
            "requirements",
            "preferred_qualifications",
        )
    )


def _resume_projects(resume: GeneratedResume) -> list[dict[str, Any]]:
    tailored = resume.tailored_content_json or {}
    projects = tailored.get("projects", []) if isinstance(tailored, dict) else []
    return [item for item in projects if isinstance(item, dict)]


def _matched_technologies(project: dict[str, Any], job_text: str) -> list[str]:
    normalized_job = _key(job_text)
    matches: list[str] = []
    for raw in project.get("technologies", []) or []:
        technology = _clean(raw)
        technology_key = _key(technology)
        if technology and technology_key and re.search(
            rf"(?:^| ){re.escape(technology_key)}(?: |$)", normalized_job
        ):
            matches.append(technology)
    return list(dict.fromkeys(matches))


def _application_bullets(
    source: dict[str, Any],
    resume_selection: dict[str, Any],
) -> list[str]:
    # The selected resume is already validated against the canonical project.
    # Only copy bullets from that immutable version or the canonical record.
    resume_bullets = resume_selection.get("bullets", [])
    source_bullets = source.get("bullets", [])
    chosen = resume_bullets if isinstance(resume_bullets, list) and resume_bullets else source_bullets
    return list(
        dict.fromkeys(_clean(item) for item in chosen if _clean(item))
    )[:3]


@dataclass(frozen=True)
class ApplicationExperienceSelection:
    selected_projects: list[dict[str, Any]]
    generated_experience_text: str
    project_match_reasons: dict[str, str]
    validation_warnings: list[str]


class ApplicationExperienceSelector:
    """Select application experience from one validated Recommended Resume."""

    def select(
        self,
        job: Job,
        profile: ApplicationProfile,
        resume: GeneratedResume,
        *,
        selected_project_names: list[str] | None = None,
        limit: int = 3,
    ) -> ApplicationExperienceSelection:
        canonical = {
            _key(item.get("name") or item.get("title")): item
            for item in profile.projects_json or []
            if isinstance(item, dict)
            and item.get("is_resume_eligible", True) is True
            and _clean(item.get("name") or item.get("title"))
        }
        requested = (
            {_key(name) for name in selected_project_names if _clean(name)}
            if selected_project_names is not None
            else None
        )
        classification = classify_job(job)
        job_text = _job_text(job)
        warnings: list[str] = []
        ranked: list[tuple[float, int, dict[str, Any], str]] = []

        for resume_order, resume_project in enumerate(_resume_projects(resume)):
            name = _clean(resume_project.get("name") or resume_project.get("title"))
            source = canonical.get(_key(name))
            if not source:
                warnings.append(f"Removed unverified project from application selection: {name or 'Unknown project'}")
                continue
            if requested is not None and _key(name) not in requested:
                continue
            canonical_technologies = list(dict.fromkeys(
                canonicalize_skill(item)
                for item in source.get("technologies", []) or []
                if _clean(item)
            ))
            canonical_technology_set = set(canonical_technologies)
            technologies = [
                canonicalize_skill(item)
                for item in resume_project.get("technologies", []) or []
                if canonicalize_skill(item) in canonical_technology_set
            ]
            if not technologies:
                technologies = canonical_technologies
            matches = _matched_technologies(source, job_text)
            score = score_project_for_job(source, classification, getattr(job, "talent_ranking_context", job_text))
            score += max(0, 6 - resume_order * 2)
            reasons = []
            if matches:
                reasons.append(f"Matches {', '.join(matches[:5])}")
            reasons.append(f"Relevant to {classification}")
            reason = "; ".join(reasons) + "."
            selected = {
                **source,
                "name": name,
                "technologies": list(dict.fromkeys(technologies)),
                "application_bullets": _application_bullets(source, resume_project),
                "resume_selection": resume_project,
                "relevance_score": round(min(100.0, score), 2),
                "relevance_reason": reason,
            }
            ranked.append((score, resume_order, selected, reason))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected_projects = [item[2] for item in ranked[: max(1, min(3, limit))]]
        reasons = {str(item[2]["name"]): item[3] for item in ranked[: len(selected_projects)]}
        blocks = []
        for project in selected_projects:
            technologies = ", ".join(project.get("technologies", [])[:6])
            heading = f"{project['name']}{f' — {technologies}' if technologies else ''}"
            bullets = "\n".join(f"• {bullet}" for bullet in project["application_bullets"])
            blocks.append(f"{heading}\n{bullets}".strip())
        experience_text = "\n\n".join(
            [ACADEMIC_EXPERIENCE_DISCLAIMER, *blocks]
        )
        return ApplicationExperienceSelection(
            selected_projects=selected_projects,
            generated_experience_text=experience_text,
            project_match_reasons=reasons,
            validation_warnings=warnings,
        )


@dataclass(frozen=True)
class ApplicationSkillSelection:
    selected_skills: list[str]
    skill_match_reasons: dict[str, str]
    validation_warnings: list[str]


class ApplicationSkillSelector:
    """Rank only verified skills already selected for the bound resume version."""

    def select(
        self,
        job: Job,
        profile: ApplicationProfile,
        resume: GeneratedResume,
        selected_projects: list[dict[str, Any]],
        *,
        selected_skills: list[str] | None = None,
        limit: int = 20,
    ) -> ApplicationSkillSelection:
        registry = build_verified_skill_registry(profile)
        resume_skills = [canonicalize_skill(item) for item in resume.selected_skills or []]
        job_text = _job_text(job)
        additional_skills = [skill for skill in registry if skill not in resume_skills and _occurrences(skill, job_text)]
        allowed = (set(resume_skills) | set(additional_skills)) & set(registry)
        requested = (
            [canonicalize_skill(item) for item in selected_skills]
            if selected_skills is not None
            else list(dict.fromkeys([*resume_skills, *additional_skills]))
        )
        selected_project_names = {
            _clean(project.get("name")) for project in selected_projects
        }
        match_records = {
            canonicalize_skill(item.get("skill")): item
            for item in resume.job_skill_matches or []
            if isinstance(item, dict) and _clean(item.get("skill"))
        }
        warnings: list[str] = []
        ranked: list[tuple[float, int, str, str]] = []
        for order, skill in enumerate(requested):
            if skill not in allowed:
                if _clean(skill):
                    warnings.append(f"Removed unverified or job-unrelated skill: {skill}")
                continue
            record = match_records.get(skill, {})
            score = float(record.get("score", 0) or 0)
            evidence = registry[skill].get("evidence", [])
            project_evidence = [
                item.removeprefix("Project: ")
                for item in evidence
                if item.startswith("Project: ")
                and item.removeprefix("Project: ") in selected_project_names
            ]
            reason = _clean(record.get("reason"))
            if project_evidence:
                reason = f"{reason}; demonstrated in {', '.join(project_evidence)}" if reason else f"Demonstrated in {', '.join(project_evidence)}"
                score += 5
            if not reason:
                reason = "Verified skill selected by the Recommended Resume" if skill in resume_skills else "Additional verified profile skill explicitly requested in this job"
            if skill in resume_skills:
                score += 1000  # Retain the CV's skills before adding optional profile matches.
            ranked.append((score, order, skill, reason.rstrip(".") + "."))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        ranked = ranked[: max(1, min(20, limit))]
        return ApplicationSkillSelection(
            selected_skills=[item[2] for item in ranked],
            skill_match_reasons={item[2]: item[3] for item in ranked},
            validation_warnings=warnings,
        )


def build_application_selection(
    job: Job,
    profile: ApplicationProfile,
    resume: GeneratedResume,
    *,
    selected_project_names: list[str] | None = None,
    selected_skills: list[str] | None = None,
) -> dict[str, Any]:
    experience = ApplicationExperienceSelector().select(
        job,
        profile,
        resume,
        selected_project_names=selected_project_names,
    )
    skills = ApplicationSkillSelector().select(
        job,
        profile,
        resume,
        experience.selected_projects,
        selected_skills=selected_skills,
    )
    return {
        "selected_projects": experience.selected_projects,
        "generated_experience_text": experience.generated_experience_text,
        "selected_skills": skills.selected_skills,
        "skill_match_reasons": skills.skill_match_reasons,
        "project_match_reasons": experience.project_match_reasons,
        "selection_warnings": [
            *experience.validation_warnings,
            *skills.validation_warnings,
        ],
    }
