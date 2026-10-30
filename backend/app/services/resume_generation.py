from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
import time
import unicodedata
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from openai import OpenAI
from pypdf import PdfReader

from app.core.config import settings
from app.schemas.api import (
    ModelTailoringOutput,
    ResumeCourseItem,
    ResumeSkillGroup,
    ResumeSkillMatch,
    ResumeSkillVerification,
    TailoredResumeContent,
)
from app.services.language_evidence import resume_language_lines
from app.services.resume_skills import (
    build_verified_skill_registry,
    canonicalize_skill,
    filter_and_verify_skill_categories,
    select_job_skills,
)
from app.services.tailoring_plan import (
    EvidenceSource,
    SkillMatchState,
    TailoringPlan,
    build_tailoring_plan,
    decide_resume_content,
    job_content_hash,
    _primary_resume_role_category,
    _role_categories,
)
from app.services.ai_privacy import CandidateAIContextBuilder


logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "resume"
MAX_JOB_TEXT = 40_000
MAX_PROFILE_TEXT = 40_000
VERTICAL_MARGIN_POINTS = 0.58 * 72 * 2

CANONICAL_NAME = 'Alex Rivera'
CANONICAL_DEGREE = 'B.S. in Computer Engineering'
CANONICAL_STUDENT_TITLE = 'Computer Engineering Student'
CANONICAL_INSTITUTION = 'Example Institute of Technology'
CANONICAL_GRADUATION = 'Expected Graduation: May 2029'
CANONICAL_GPA = '3.70/4.00'
CANONICAL_LOCATION = 'Mexico City, Mexico'
CANONICAL_EMAIL = settings.resume_email.strip() or "resume@example.com"
CANONICAL_PHONE = '+52 55 0000 0000'
CANONICAL_LINKEDIN = 'https://www.linkedin.com/in/example-candidate/'
CANONICAL_LINKEDIN_LABEL = "linkedin.com/in/example-candidate"
LEGACY_LINKEDIN_URLS = {'https://www.linkedin.com/in/example-candidate/'}
CANONICAL_GITHUB = 'https://github.com/example-candidate'

INVALID_DEGREE_NAMES = {
    "Robotics and Intelligent Systems Engineering",
    "Robotics Engineering",
    "Computer Science",
    "Software Engineering",
}
ARTIFICIAL_PHRASES = {
    "documented application behavior",
    "verified embedded interfaces",
    "documented robotic platform",
    "documented monitoring workflow",
    "connected control architecture",
    "representative scenarios",
    "technical solutions relevant to",
    "verified hands-on skills include",
    "contributed to various tasks",
    "worked with different technologies",
    "passionate student",
    "hard-working individual",
    "seeking an opportunity",
}
PENALIZED_WORDS = {"documented", "verified", "relevant", "various", "different"}
CORRUPT_CHARACTERS = {"\u00ad", "\ufffe", "\ufffd"}
VALID_CLASSIFICATIONS = {
    "General Engineering",
    "Hardware / Systems Integration",
    "KOSPIE / Germany Engineering",
    "Talent Community",
    "Software Engineering",
    "Backend / Data",
    "Embedded / Firmware",
    "FPGA / Digital Design",
    "AI / API Integration",
    "Robotics / Controls",
    "Maps / Routing / Geospatial",
    "Full Stack / Web",
    "Developer Tools / Productivity",
    "Robotics Research",
    "Solutions / API Integration",
    "Security / Consulting",
}
VALID_SKILL_CATEGORIES = {
    "Digital Systems & Hardware",
    "Engineering Tools",
    "Languages",
    "Backend",
    "Backend / Web",
    "Development",
    "Debug & Validation",
    "Hardware",
    "Technical",
    "Programming",
    "Software Development",
    "Algorithms & Software",
    "Embedded Systems",
    "Hardware Interfaces",
    "Systems",
    "Systems & Data",
    "Tools",
    "FPGA / Digital Design",
    "Backend / Data",
    "Web & APIs", "Data", "Software Engineering", "RTOS", "Protocols",
}
ACTION_VERBS = {
    "added", "analyzed", "automated", "built", "configured", "created", "debugged",
    "designed", "developed", "implemented", "integrated", "modeled",
    "optimized", "programmed", "simulated", "tested", "validated", "investigated",
    "characterized", "measured", "experimented", "evaluated",
}
PROJECT_PRIORITIES = {
    "Hardware / Systems Integration": [
        "Intel MAX 10 Robotic Arm Controller",
        "MATT Web-Controlled Writing Robot",
        "BLE Virtual Mouse",
        "C.U.T.Y Desktop Companion Robot",
        "FreeRTOS Event-Driven System",
        "DC Motor PID Position Control System with WebXR Interface",
        "DC Motor Position Control System with WebXR Interface",
        "ESP32 Discrete PID Controller with Analog Reference",
        "SkiliAir Air Quality Monitoring System",
        "Internship Radar - AI Resume Tailoring Platform",
        "Stock Exchange Matching Engine",
    ],
    "Robotics Research": [],
    "Embedded / Firmware": [
        "FreeRTOS Event-Driven System",
        "MATT Web-Controlled Writing Robot",
        "BLE Virtual Mouse",
        "DC Motor PID Position Control System with WebXR Interface",
        "DC Motor Position Control System with WebXR Interface",
        "ESP32 Discrete PID Controller with Analog Reference",
        "C.U.T.Y Desktop Companion Robot",
        "Intel MAX 10 Robotic Arm Controller",
        "Internship Radar - AI Resume Tailoring Platform",
        "SkiliAir Air Quality Monitoring System",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
    ],
    "Software Engineering": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Forge the Code",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
        "SkiliAir Air Quality Monitoring System",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
    "Backend / Data": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Forge the Code",
        "SkiliAir Air Quality Monitoring System",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
    "FPGA / Digital Design": [
        "Intel MAX 10 Robotic Arm Controller",
        "FreeRTOS Event-Driven System",
        "MATT Web-Controlled Writing Robot",
        "Internship Radar - AI Resume Tailoring Platform",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
        "SkiliAir Air Quality Monitoring System",
    ],
    "AI / API Integration": [
        "Internship Radar - AI Resume Tailoring Platform",
        "SkiliAir Air Quality Monitoring System",
        "Stock Exchange Matching Engine",
        "MATT Web-Controlled Writing Robot",
        "Königsberg Graph Game",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
    "Robotics / Controls": [
        "MATT Web-Controlled Writing Robot",
        "Intel MAX 10 Robotic Arm Controller",
        "FreeRTOS Event-Driven System",
        "SkiliAir Air Quality Monitoring System",
        "Königsberg Graph Game",
        "Stock Exchange Matching Engine",
    ],
    "Maps / Routing / Geospatial": [
        "Königsberg Graph Game",
        "SkiliAir Air Quality Monitoring System",
        "Internship Radar - AI Resume Tailoring Platform",
        "Stock Exchange Matching Engine",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
    "Full Stack / Web": [
        "Internship Radar - AI Resume Tailoring Platform",
        "SkiliAir Air Quality Monitoring System",
        "MATT Web-Controlled Writing Robot",
        "Königsberg Graph Game",
        "Stock Exchange Matching Engine",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
    "Computer Vision": [
        "Fruit Freshness Detector",
        "SkiliAir Air Quality Monitoring System",
        "MATT Web-Controlled Writing Robot",
    ],
    "Developer Tools / Productivity": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Forge the Code",
        "SkiliAir Air Quality Monitoring System",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
        "Intel MAX 10 Robotic Arm Controller",
    ],
}

MAP_CLASSIFICATION_TERMS = (
    "maps", "mapping", "routing", "route planning", "path planning",
    "navigation", "geospatial", "geographic", "localization", "coordinates",
    "graph traversal", "shortest path", "pathfinding", "spatial data",
    "geographic data", "map services", "spatial planning",
)
MAP_STRUCTURAL_TERMS = ("graph", "roads", "nodes", "edges", "location")
MAP_PHYSICAL_TERMS = (
    "robot", "robotics", "vehicle", "autonomous", "flight", "physical system",
    "hardware/software", "hardware integration", "real-time system",
)

RESEARCH_SEMANTIC_GROUPS = {
    "Manipulation": ("manipulation", "grasp", "tactile", "servo", "motor", "actuator", "encoder", "control", "sensor"),
    "Controls": ("control", "controls", "pid", "feedback", "dynamics", "motor", "encoder", "matlab"),
    "Computer Vision": ("computer vision", "vision", "perception", "image processing", "camera", "opencv", "python"),
    "Embedded Systems": ("embedded", "microcontroller", "freertos", "rtos", "uart", "i2c", "spi", "electronics", "c++", " c "),
    "Autonomous Systems": ("autonomous", "autonomy", "planning", "navigation", "robot", "control", "vision", "sensor"),
    "Robot Learning": ("robot learning", "machine learning", "reinforcement learning", "perception", "vision", "python", "data analysis"),
    "Robotics": ("robot", "robotics", "mechatronics", "motor", "sensor", "actuator", "embedded", "control"),
}


def research_focus_groups(text: str) -> list[str]:
    lowered = sanitize_resume_text(text).lower()
    return [
        group for group, terms in RESEARCH_SEMANTIC_GROUPS.items()
        if any(_keyword_present(term, lowered) for term in terms[:4])
    ]


def sanitize_resume_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u00ad", "")
    normalized = normalized.replace("\u2010", "-").replace("\u2011", "-")
    normalized = normalized.replace("\u2012", "-").replace("\u2013", "-")
    normalized = normalized.replace("\u2014", "-").replace("\u2212", "-")
    normalized = "".join(
        char for char in normalized
        if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )
    return re.sub(r"\s+", " ", normalized).strip()


def latex_escape(value: Any) -> str:
    text = sanitize_resume_text(str(value or ""))
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", sanitize_resume_text(value)).strip("_")
    return cleaned[:120] or "Resume"


def _organization_token(organization: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", sanitize_resume_text(organization))
    ignored = {"of", "the", "and"}
    initials = "".join(word[0].upper() for word in words if word.lower() not in ignored)
    return initials if 2 <= len(initials) <= 8 else "_".join(words[:3])


def resume_filename(full_name: str, organization: str, resume_target: str, target_role: str = "", variant: str = "") -> str:
    if resume_target == "kospie_germany":
        stem = f"{full_name}_KOSPIE_DAAD_CV"
    elif resume_target == "robotics_research":
        context = "_".join(item for item in (_organization_token(organization), variant) if item)
        stem = f"{full_name}_{context}_{'Research_CV' if context else 'Robotics_Research_CV'}"
    else:
        stem = f"{full_name}_{organization}_{target_role}_Resume"
    return f"{sanitize_filename(stem)}.pdf"


def _profile_dict(profile: Any) -> dict[str, Any]:
    result = {
        key: getattr(profile, key)
        for key in (
            "full_name", "email", "phone", "location", "linkedin_url", "github_url",
            "headline", "summary", "education_json", "skills_json", "experience_json",
            "projects_json", "coursework_json", "certifications_json", "languages_json",
            "forbidden_claims_json",
        )
    }
    stored_linkedin = str(result.get("linkedin_url") or "").strip().rstrip("/").casefold()
    is_santiago = sanitize_resume_text(result.get("full_name")) == CANONICAL_NAME
    if is_santiago or stored_linkedin in LEGACY_LINKEDIN_URLS:
        result["linkedin_url"] = CANONICAL_LINKEDIN
        result["linkedin_label"] = CANONICAL_LINKEDIN_LABEL
    else:
        result["linkedin_label"] = "LinkedIn"
    return result


def _valid_url(value: str | None) -> bool:
    if not value:
        return True
    parsed = urlparse(sanitize_resume_text(value))
    return parsed.scheme == "https" and bool(parsed.netloc)


def _words(value: str) -> list[str]:
    return re.findall(r"\S+", sanitize_resume_text(value))


def _clean_list(value: Any, limit: int = 3) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[\r\n]+", value)
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [sanitize_resume_text(item) for item in values if sanitize_resume_text(item)][:limit]


def _item_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return sanitize_resume_text(value)
    return ""


def _keyword_present(keyword: str, text: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9+#]){re.escape(keyword.lower())}(?![A-Za-z0-9+#])"
    return re.search(pattern, text.lower()) is not None


def _profile_project_map(profile: Any) -> dict[str, dict[str, Any]]:
    return {
        sanitize_resume_text(item.get("name", "")): item
        for item in profile.projects_json
        if isinstance(item, dict) and sanitize_resume_text(item.get("name", ""))
    }


def validate_master_profile(profile: Any) -> None:
    for field in ("full_name", "email", "location"):
        if not sanitize_resume_text(getattr(profile, field, "")):
            raise ValueError(f"Resume Profile requires {field}.")
    if (
        sanitize_resume_text(getattr(profile, "full_name", "")) == CANONICAL_NAME
        and sanitize_resume_text(getattr(profile, "email", "")) != CANONICAL_EMAIL
    ):
        raise ValueError("Resume Profile email does not match the account owner.")
    if not profile.education_json or not isinstance(profile.education_json[0], dict):
        raise ValueError("Resume Profile must contain education.")
    education = profile.education_json[0]
    for field in ("degree", "institution", "graduation"):
        if not sanitize_resume_text(education.get(field, "")):
            raise ValueError(f"Resume Profile education requires {field}.")
    for field in ("linkedin_url", "github_url"):
        if getattr(profile, field, "") and not _valid_url(getattr(profile, field, "")):
            raise ValueError(f"Resume Profile contains an invalid {field}.")


def _contains_artificial_language(value: str) -> list[str]:
    lowered = sanitize_resume_text(value).lower()
    found = [phrase for phrase in ARTIFICIAL_PHRASES if phrase in lowered]
    overused = [
        word for word in PENALIZED_WORDS
        if len(re.findall(rf"\b{re.escape(word)}\b", lowered)) > 1
    ]
    return sorted(found + overused)


def _ensure_verified_skill_section(
    content: TailoredResumeContent,
    verified_profile: Any,
    job: Any,
) -> None:
    requested = [
        item
        for group in content.skill_categories
        for item in group.items
    ]
    _, verification = filter_and_verify_skill_categories(
        content.skill_categories, verified_profile
    )
    plan_snapshot = content.tailoring_plan or {}
    plan_decisions = plan_snapshot.get("resume_decisions", {}) if isinstance(plan_snapshot, dict) else {}
    if plan_decisions.get("status") == "PLANNED":
        planned = list(plan_decisions.get("selected_skills", []))
        if requested != planned:
            raise ValueError("Rendered skills do not match the TailoringPlan decisions.")
        if verification["removed"]:
            raise ValueError(
                "TailoringPlan contains unsupported skills: "
                + ", ".join(verification["removed"])
            )
        content.selected_skills = requested
        existing_matches = {item.skill: item for item in content.job_skill_matches}
        if set(existing_matches) != set(requested):
            raise ValueError("TailoringPlan skills require evidence explanations.")
        content.job_skill_matches = [existing_matches[skill] for skill in requested]
        content.skill_verification = ResumeSkillVerification.model_validate({
            "all_verified": True,
            "verified": requested,
            "removed": [],
            "registry_size": len(build_verified_skill_registry(verified_profile)),
        })
        return
    if content.application_type == "KOSPIE_PROGRAM" and not verification["removed"]:
        content.selected_skills = requested
        existing_matches = {item.skill: item for item in content.job_skill_matches}
        content.job_skill_matches = [existing_matches[skill] for skill in requested]
        content.skill_verification = ResumeSkillVerification.model_validate({
            "all_verified": True,
            "verified": requested,
            "removed": [],
            "registry_size": len(build_verified_skill_registry(verified_profile)),
        })
        return
    result = select_job_skills(
        job,
        verified_profile,
        content.classification,
        selected_project_names={project.name for project in (content.projects[:3] if content.application_type == "STANDARD_JOB" else content.projects)},
        model_requested=requested,
        # Preserve a lower limit chosen by one-page fitting on later validation
        # passes instead of expanding the section back to its original size.
        limit=min(12, max(8, len(requested))),
    )
    removed = list(dict.fromkeys(verification["removed"]))
    content.skill_categories = [
        ResumeSkillGroup.model_validate(group) for group in result["categories"]
    ]
    content.selected_skills = result["selected_skills"]
    content.job_skill_matches = [
        ResumeSkillMatch.model_validate(item) for item in result["matches"]
    ]
    content.skill_verification = ResumeSkillVerification.model_validate({
        **result["verification"],
        "all_verified": not removed,
        "removed": removed,
    })
    if removed:
        warning = f"Removed unverified skills: {', '.join(removed)}"
        if warning not in content.warnings:
            content.warnings.append(warning)
        logger.warning("Resume skill validation removed unsupported values: %s", removed)


def _synchronize_plan_after_layout_adjustment(content: TailoredResumeContent) -> None:
    """Keep a final rendered resume and its plan snapshot aligned.

    The one-page fitter may remove a lowest-priority skill or project only
    after the initial evidence-backed decisions have been made. That is a
    layout adjustment, not a new selection pass, so retain the original
    scores/reasons for surviving evidence while synchronizing the final list
    that is actually rendered and persisted.
    """
    plan_snapshot = content.tailoring_plan
    if not isinstance(plan_snapshot, dict):
        return
    if plan_snapshot.get("mode") == "BEST_RESUME":
        best_plan = plan_snapshot.get("best_resume_plan")
        if isinstance(best_plan, dict):
            best_plan["selected_skills"] = list(content.selected_skills)
            best_plan["selected_projects"] = [project.name for project in content.projects]
            best_plan["selected_coursework"] = [course.name for course in content.coursework]
            best_plan["selected_certifications"] = [item.name for item in content.certifications]
        if isinstance(content.tailoring_trace, dict):
            content.tailoring_trace["selected_skills"] = list(content.selected_skills)
            content.tailoring_trace["selected_projects"] = [project.name for project in content.projects]
        return
    decisions = plan_snapshot.get("resume_decisions")
    if not isinstance(decisions, dict) or decisions.get("status") != "PLANNED":
        return

    selected_skills = list(content.selected_skills)
    selected_projects = [project.name for project in content.projects]
    selected_coursework = [course.name for course in content.coursework]
    selected_certifications = [item.name for item in content.certifications]
    selected_experience = [item.organization for item in content.experience]
    decisions["selected_skills"] = selected_skills
    decisions["selected_projects"] = selected_projects
    decisions["selected_coursework"] = selected_coursework
    decisions["selected_certifications"] = selected_certifications
    decisions["selected_experience"] = selected_experience
    decisions["selected_skill_categories"] = [group.model_dump() for group in content.skill_categories]
    for key in ("selected_project_scores", "selected_project_reasons"):
        values = decisions.get(key)
        if isinstance(values, dict):
            decisions[key] = {name: values[name] for name in selected_projects if name in values}
    evidence = decisions.get("selected_skill_evidence")
    if isinstance(evidence, dict):
        decisions["selected_skill_evidence"] = {
            skill: evidence[skill] for skill in selected_skills if skill in evidence
        }
    if isinstance(content.tailoring_trace, dict):
        content.tailoring_trace["selected_skills"] = selected_skills


def validate_generated_resume(
    content: TailoredResumeContent,
    verified_profile: Any,
    job: Any,
    *,
    minimum_projects: int | None = None,
) -> TailoredResumeContent:
    validate_master_profile(verified_profile)
    payload = json.dumps(content.model_dump(), ensure_ascii=False)
    document_payload = json.dumps(
        content.model_dump(include={
            "headline", "summary", "skill_categories", "education", "experience",
            "projects", "coursework", "certifications", "languages", "research_interests",
            "additional_information",
        }),
        ensure_ascii=False,
    )
    lowered = document_payload.lower()
    expected_degree = _item_value(verified_profile.education_json[0], "degree")
    expected_title = sanitize_resume_text(getattr(verified_profile, "headline", ""))
    expected_email = sanitize_resume_text(getattr(verified_profile, "email", ""))
    if content.education.degree != expected_degree:
        raise ValueError("Generated resume contains an inconsistent degree name.")
    if expected_degree not in payload or not expected_title or expected_title not in content.headline:
        raise ValueError("Profile degree and student title must be present.")
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", payload))
    if emails and emails != {expected_email}:
        raise ValueError("Generated resume contains an email from another profile.")

    all_bullets = [bullet.strip().casefold() for project in content.projects for bullet in project.bullets]
    if len(all_bullets) != len(set(all_bullets)):
        raise ValueError("Generated resume contains duplicate project bullets.")

    artificial = _contains_artificial_language(re.sub(r"https?://[^\s\"']+", "", document_payload))
    if artificial:
        raise ValueError(f"Generated resume contains artificial language: {', '.join(artificial)}")
    if re.search(r"\b(\w+)\s+\1\b", lowered):
        raise ValueError("Generated resume contains repeated consecutive words.")

    if content.classification not in VALID_CLASSIFICATIONS:
        raise ValueError("Resume classification is not supported.")
    if content.classification != classify_job(job):
        raise ValueError("Resume classification does not match the job.")
    _ensure_verified_skill_section(content, verified_profile, job)
    plan_snapshot = content.tailoring_plan if isinstance(content.tailoring_plan, dict) else {}
    plan_decisions = plan_snapshot.get("resume_decisions", {}) if plan_snapshot else {}
    if plan_decisions.get("status") == "PLANNED":
        rendered_projects = [project.name for project in content.projects]
        if rendered_projects != list(plan_decisions.get("selected_projects", [])):
            raise ValueError("Rendered projects do not match the TailoringPlan decisions.")
    summary_words = len(_words(content.summary))
    is_kospie = content.application_type == "KOSPIE_PROGRAM"
    if is_kospie:
        if summary_words > 55:
            raise ValueError("KOSPIE summary must contain at most 55 words.")
    elif content.application_type == "TALENT_COMMUNITY":
        if summary_words > 35:
            raise ValueError("Company resume summary must be at most 35 words.")
    elif not 35 <= summary_words <= 55:
        raise ValueError("Summary must contain between 35 and 55 words.")
    if content.headline.count("|") > 3:
        raise ValueError("Headline may contain at most four elements.")

    verified_registry = build_verified_skill_registry(verified_profile)
    if any(interest not in verified_registry for interest in content.research_interests):
        raise ValueError("Research interests must be derived from verified profile skills.")
    if not 2 <= len(content.skill_categories) <= 4:
        raise ValueError("Resume must contain two to four skill categories.")
    total_skills = sum(len(group.items) for group in content.skill_categories)
    minimum_skills = min(8, len(verified_registry))
    if not minimum_skills <= total_skills <= 16:
        raise ValueError("Resume must contain approximately eight to sixteen verified skills.")
    flattened_skills = [item for group in content.skill_categories for item in group.items]
    if flattened_skills != content.selected_skills:
        raise ValueError("Selected skills must match the rendered skill categories.")
    if len(set(flattened_skills)) != len(flattened_skills):
        raise ValueError("Resume skill aliases must not create duplicate skills.")
    for group in content.skill_categories:
        if group.name not in VALID_SKILL_CATEGORIES:
            raise ValueError(f"Unsupported skill category: {group.name}")
        if not 2 <= len(group.items) <= 8:
            raise ValueError(f"Skill category {group.name} must contain two to eight items.")
        unsupported = [
            item for item in group.items
            if item not in verified_registry
        ]
        if unsupported:
            raise ValueError(f"Unverified skills: {', '.join(unsupported)}")
    if {item.skill for item in content.job_skill_matches} != set(content.selected_skills):
        raise ValueError("Every selected skill must retain its job match explanation.")

    project_map = _profile_project_map(verified_profile)
    project_minimum, project_maximum = (4, 5) if is_kospie else (2, 4)
    if minimum_projects is not None and not is_kospie:
        project_minimum = minimum_projects
    if not project_minimum <= len(content.projects) <= project_maximum:
        raise ValueError(
            f"Resume must contain {project_minimum} to {project_maximum} projects."
        )
    seen_bullets: set[str] = set()
    for project in content.projects:
        source = project_map.get(project.name)
        if source is None:
            raise ValueError(f"Unverified project: {project.name}")
        repository_url = _item_value(source, "repository_url", "github_url", "url") or None
        source_url = (
            repository_url
            if source.get("is_public", True) and _valid_url(repository_url)
            else None
        )
        if project.github_url != source_url:
            raise ValueError(f"Invalid or unverified project URL: {project.name}")
        source_live_url = _item_value(source, "live_url") or None
        expected_live_url = source_live_url if _valid_url(source_live_url) else None
        if project.live_url != expected_live_url:
            raise ValueError(f"Invalid or unverified live URL: {project.name}")
        source_technologies = {
            sanitize_resume_text(item).lower()
            for item in source.get("technologies", [])
        }
        if any(
            sanitize_resume_text(item).lower() not in source_technologies
            for item in project.technologies
        ):
            raise ValueError(f"Project contains unverified technologies: {project.name}")
        if len(project.technologies) > 5:
            raise ValueError(f"Project shows more than five technologies: {project.name}")
        if not 2 <= len(project.bullets) <= 3:
            raise ValueError(f"Project {project.name} must contain two or three bullets.")
        normalized_title = re.sub(r"[^a-z0-9 ]", "", project.name.lower())
        for bullet in project.bullets:
            count = len(_words(bullet))
            if not 14 <= count <= 28:
                raise ValueError(f"Project bullet must contain 14 to 28 words: {bullet}")
            first = re.sub(r"[^A-Za-z]", "", _words(bullet)[0]).lower()
            if first not in ACTION_VERBS:
                raise ValueError(f"Project bullet must begin with an action verb: {bullet}")
            normalized_bullet = re.sub(r"[^a-z0-9 ]", "", bullet.lower())
            if normalized_title and normalized_title in normalized_bullet:
                raise ValueError(f"Project bullet repeats its project title: {project.name}")
            if normalized_bullet in seen_bullets:
                raise ValueError("Generated resume contains duplicate project bullets.")
            seen_bullets.add(normalized_bullet)

    course_limit = 8 if is_kospie else 4 if content.application_type == "PROFILE_PORTFOLIO" else 2
    if len(content.coursework) > course_limit:
        raise ValueError(f"Resume may contain at most {course_limit} courses.")
    verified_courses = {
        _item_value(item, "name"): item
        for item in verified_profile.coursework_json
        if isinstance(item, dict) and _item_value(item, "name")
    }
    verified_courses.update({
        sanitize_resume_text(item): {"name": sanitize_resume_text(item), "institution": ""}
        for item in verified_profile.coursework_json
        if isinstance(item, str) and sanitize_resume_text(item)
    })
    if verified_profile.education_json and isinstance(verified_profile.education_json[0], dict):
        education = verified_profile.education_json[0]
        institution = _item_value(education, "institution", "school")
        verified_courses.update({
            sanitize_resume_text(item): {"name": sanitize_resume_text(item), "institution": institution}
            for item in education.get("coursework", [])
            if isinstance(item, str) and sanitize_resume_text(item)
        })
    for course in content.coursework:
        source = verified_courses.get(course.name)
        if source is None:
            raise ValueError(f"Unverified course: {course.name}")
        if course.institution != _item_value(source, "institution"):
            raise ValueError(f"Unverified course institution: {course.name}")
        if "credential" in course.model_dump_json().lower():
            raise ValueError("Course output may not contain credential IDs.")

    forbidden = {
        sanitize_resume_text(item).lower()
        for item in verified_profile.forbidden_claims_json
        if sanitize_resume_text(item)
    }
    violated = sorted(claim for claim in forbidden if claim in lowered)
    if violated:
        raise ValueError(f"Generated resume contains forbidden claims: {', '.join(violated)}")
    verified_certifications = {
        _item_value(item, "name", "title").lower()
        for item in verified_profile.certifications_json
        if isinstance(item, dict)
    }
    if any(item.name.lower() not in verified_certifications for item in content.certifications):
        raise ValueError("Generated resume contains an unverified certification.")
    if any(char in payload for char in CORRUPT_CHARACTERS):
        raise ValueError("Generated resume contains corrupt Unicode characters.")
    if is_kospie:
        expected_languages = set(getattr(job, "kospie_resume_languages", []) or [])
        if set(content.languages) != expected_languages:
            raise ValueError("KOSPIE resume languages must match verified language evidence.")
        verified_additional = set(getattr(job, "kospie_additional_information", []) or [])
        if any(item not in verified_additional for item in content.additional_information):
            raise ValueError("KOSPIE resume contains unverified additional information.")

    content.quality_checks.canonical_degree_name = True
    content.quality_checks.no_unsupported_claims = True
    content.quality_checks.no_artificial_language = True
    content.quality_checks.ats_text_clean = True
    return content


def validate_verified_content(content: TailoredResumeContent, profile: Any) -> None:
    """Backward-compatible validation entry point used by existing callers and tests."""
    job = type(
        "ValidationJob",
        (),
        {
            "title": content.target_role,
            "area": content.classification,
            "description": content.classification,
            "requirements": "",
            "preferred_qualifications": "",
        },
    )()
    validate_generated_resume(content, profile, job)


def classify_job(job: Any) -> str:
    if getattr(job, "portfolio_profile_id", None) == "best":
        return "General Engineering"
    if getattr(job, "application_type", "") == "TALENT_COMMUNITY":
        return "Talent Community"
    if getattr(job, "resume_target", "") == "robotics_research":
        return "Robotics Research"
    if getattr(job, "resume_target", "") == "kospie_germany":
        return "KOSPIE / Germany Engineering"
    explicit_targets = {
        "software_engineering": "Software Engineering",
        "embedded_firmware": "Embedded / Firmware",
        "electrical_validation": "FPGA / Digital Design",
        "hardware_engineering": "Hardware / Systems Integration",
    }
    if getattr(job, "resume_target", "") in explicit_targets:
        return explicit_targets[job.resume_target]
    title = sanitize_resume_text(getattr(job, "title", "")).lower()
    if any(term in title for term in (
        "security consultant", "security consulting", "security engineer", "security engineering",
        "cybersecurity", "cyber security",
    )):
        return "Security / Consulting"
    if any(term in title for term in ("solutions engineering", "customer engineering", "partner solutions engineering", "developer relations")):
        return "Solutions / API Integration"
    # Explicit role intent takes precedence over incidental software keywords.
    if any(term in title for term in ("hardware engineering", "hardware engineer", "hardware intern")):
        return "Hardware / Systems Integration"
    if any(term in title for term in ("embedded", "firmware", "microcontroller", "microcontrollers", "mcu")):
        return "Embedded / Firmware"
    text = " ".join(
        sanitize_resume_text(value).lower()
        for value in (
            getattr(job, "title", ""), getattr(job, "area", ""),
            getattr(job, "description", ""), getattr(job, "requirements", ""),
            getattr(job, "preferred_qualifications", ""),
        )
    )
    scores = {
        "Security / Consulting": sum(text.count(term) * 3 for term in (
            "security consultant", "security consulting", "security engineering", "security engineer",
            "cybersecurity", "cyber security", "system security", "threat", "vulnerability",
            "incident response", "siem", "soc",
        )),
        "Solutions / API Integration": sum(text.count(term) * 2 for term in (
            "technical integration", "api integration", "rest api", "restful api",
            "sdk", "webhook", "partner support", "developer support", "troubleshooting",
        )),
        "Hardware / Systems Integration": sum(2 for term in (
            "board design", "board bring-up", "signal integrity", "power integrity",
            "hardware validation", "hardware system", "electromechanical", "pcb", "circuit design",
        ) if term in text),
        "Embedded / Firmware": sum(text.count(term) for term in (
            "embedded", "firmware", "freertos", "rtos", "microcontroller", "microcontrollers",
            "mcu", "uart", "spi", "i2c", "can bus", "lin bus",
        )),
        "FPGA / Digital Design": sum(text.count(term) for term in (
            "fpga", "verilog", "rtl", "digital design", "asic", "systemverilog",
        )),
        "Backend / Data": sum(text.count(term) for term in (
            "backend", "database", "sql", "data service", "data pipeline", "mysql",
        )),
        "AI / API Integration": sum(text.count(term) for term in (
            "artificial intelligence", "machine learning", "llm", "openai", "ai integration",
        )),
        "Robotics / Controls": sum(text.count(term) for term in (
            "robotics", "robot", "controls", "control system", "motion", "autonomous",
        )),
        "Software Engineering": sum(text.count(term) for term in (
            "software", "sde", "c++", "object-oriented", "cross-platform", "algorithm",
        )),
        "Maps / Routing / Geospatial": (
            sum(text.count(term) * 3 for term in MAP_CLASSIFICATION_TERMS)
            + sum(text.count(term) for term in MAP_STRUCTURAL_TERMS)
        ),
        "Full Stack / Web": sum(text.count(term) * 2 for term in (
            "full-stack", "full stack", "next.js", "typescript", "frontend",
            "web application", "web platform", "react",
        )),
        "Developer Tools / Productivity": sum(text.count(term) * 2 for term in (
            "developer tools", "developer tooling", "productivity", "internal tools",
            "automation platform", "workflow tooling",
        )),
    }
    if any(term in title for term in ("maps", "mapping", "routing", "navigation", "geospatial")):
        scores["Maps / Routing / Geospatial"] += 16
    if any(term in title for term in ("embedded", "firmware", "microcontroller", "microcontrollers", "mcu")):
        scores["Embedded / Firmware"] += 12
    if "fpga" in title or "digital design" in title:
        scores["FPGA / Digital Design"] += 12
    if "backend" in title or "back-end" in title:
        scores["Backend / Data"] += 14
    if "controls" in title or "robot" in title:
        scores["Robotics / Controls"] += 10
    if "software" in title or "sde" in title:
        scores["Software Engineering"] += 8
    if "data" in title:
        scores["Backend / Data"] += 5
    if (
        ("ai" in title and "api" in title)
        or "api integration" in title
        or "artificial intelligence" in title
    ):
        scores["AI / API Integration"] += 14
    if "full-stack" in title or "full stack" in title or "web" in title:
        scores["Full Stack / Web"] += 14
    if "developer tool" in title or "productivity" in title:
        scores["Developer Tools / Productivity"] += 14
    return max(scores, key=scores.get)


def weighted_role_categories(job: Any) -> dict[str, int]:
    text = " ".join(str(getattr(job, field, "") or "") for field in (
        "title", "area", "description", "requirements", "preferred_qualifications",
    )).lower()
    signals = {
        "SECURITY_CONSULTING": ("security consultant", "security consulting", "security advisory"),
        "SECURITY_ENGINEERING": ("security engineering", "security engineer", "security consultant", "application security", "network security"),
        "CYBERSECURITY": ("cybersecurity", "cyber security", "security", "threat", "vulnerability", "siem"),
        "SYSTEM_SECURITY": ("system security", "systems security", "security consultant", "security engineering"),
        "SOLUTIONS_ENGINEERING": ("solutions engineering", "partner solutions", "customer engineering", "stakeholder", "problem scoping"),
        "API_INTEGRATION": ("rest api", "restful api", "api integration", "sdk", "webhook", "technical integration"),
        "SOFTWARE_ENGINEERING": ("software", "python", "c++", "developer"),
        "AUTOMATION": ("automation", "automate", "reusable solutions"),
        "DATA_ENGINEERING": ("data pipeline", "dashboard", "data processing"),
        "EMBEDDED": (
            "embedded", "firmware", "microcontroller", "microcontrollers", "mcu", "freertos",
            "rtos", "spi", "i2c", "uart", "can bus", "lin bus", "pwm",
        ),
        "ROBOTICS": ("robotics", "robot", "motion control"),
        "FPGA_RTL": ("fpga", "verilog", "rtl"),
    }
    return {category: score for category, terms in signals.items()
            if (score := sum(text.count(term) for term in terms)) > 0}


def extract_job_requirements(job: Any) -> dict[str, list[str]]:
    """Keep posting priorities separate from candidate evidence."""
    from app.services.resume_skills import _description_segments
    description = str(getattr(job, "description", "") or "")
    desc_required, desc_preferred, desc_contextual = _description_segments(description)
    sections = {
        "required": " ".join((str(getattr(job, "requirements", "") or ""), desc_required)),
        "preferred": " ".join((str(getattr(job, "preferred_qualifications", "") or ""), desc_preferred)),
        "responsibilities": desc_contextual,
    }
    terms = {
        "tools": ("SDKs", "Webhooks", "Git", "Linux", "Docker"),
        "technologies": ("Python", "C++", "C", "Java", "REST APIs", "RESTful APIs", "JSON", "PostgreSQL", "MySQL", "FastAPI", "Flask"),
        "domain_signals": ("technical integrations", "automation", "data pipelines", "dashboards", "technical troubleshooting", "partner support", "developer support"),
    }
    output = {section: [term for term in (
        "Python", "C++", "C", "Java", "REST APIs", "RESTful APIs", "JSON", "SDKs", "Webhooks",
        "data pipelines", "dashboards", "technical troubleshooting", "technical integrations", "automation",
    ) if _keyword_present(term, value)] for section, value in sections.items()}
    all_text = " ".join(sections.values())
    output.update({section: [term for term in choices if _keyword_present(term, all_text)]
                   for section, choices in terms.items()})
    return output


def _headline(classification: str) -> str:
    suffixes = {
        "Hardware / Systems Integration": "Hardware/Software Integration | FPGA | Embedded Systems",
        "KOSPIE / Germany Engineering": "Robotics | Embedded Systems | Digital Systems",
        "Robotics Research": "Robotics Research | Embedded Systems | Controls",
        "Embedded / Firmware": "Embedded Software | C/C++ | FreeRTOS",
        "Software Engineering": "C++ | Python | Software Development",
        "Backend / Data": "Python | REST APIs | MySQL",
        "FPGA / Digital Design": "Verilog | FPGA | Digital Design",
        "AI / API Integration": "Python | REST APIs | Backend Integration",
        "Robotics / Controls": "Robotics | C/C++ | Control Systems",
        "Maps / Routing / Geospatial": "C++ | Python | Algorithms",
        "Full Stack / Web": "TypeScript | Python | Full-Stack Development",
        "Developer Tools / Productivity": "Python | TypeScript | Developer Tools",
    }
    return f"{CANONICAL_STUDENT_TITLE} | {suffixes[classification]}"


def _profile_headline(profile: Any, classification: str, selected_skills: list[str]) -> str:
    if classification != "Solutions / API Integration" and sanitize_resume_text(getattr(profile, "full_name", "")) == CANONICAL_NAME:
        return _headline(classification)
    title = sanitize_resume_text(getattr(profile, "headline", ""))
    return " | ".join([title, *selected_skills[:3]])


def _profile_summary(profile: Any, classification: str, selected_skills: list[str]) -> str:
    if classification == "Solutions / API Integration":
        focus = "software services, technical integrations, and application workflows"
    elif classification == "Embedded / Firmware":
        focus = "firmware, real-time systems, microcontroller interfaces, and debugging"
    elif classification == "FPGA / Digital Design":
        focus = "digital logic, FPGA design, simulation, and hardware validation"
    elif classification == "Robotics Research":
        focus = "robotics, sensing, embedded control, and system integration"
    else:
        focus = f"{classification.lower()} projects and practical engineering systems"
    title = sanitize_resume_text(getattr(profile, "headline", ""))
    if title.endswith(" Student"):
        title = title[:-8] + " student"
    skills = ", ".join(selected_skills[:7])
    return (
        f"{title} with project experience building {focus}. "
        f"Developed and tested systems using {skills}. "
        "Applies debugging, integration, and structured problem solving to deliver "
        "reliable technical solutions."
    )


def _summary(classification: str) -> str:
    summaries = {
        "Hardware / Systems Integration": (
            "Robotics and Digital Systems Engineering student with project experience building "
            "FPGA controllers, robotic systems, and embedded hardware interfaces. Integrates "
            "digital logic, microcontrollers, communications, and actuators using Intel MAX 10, "
            "Verilog, C/C++, UART, and PWM, with hands-on system testing and debugging."
        ),
        "Robotics Research": (
            "Robotics and Digital Systems Engineering student with hands-on project experience in "
            "robotics, embedded systems, sensing, and hardware/software integration. Designs, integrates, "
            "tests, and validates physical systems using verified C/C++, Python, microcontroller, control, "
            "communication, computer vision, Linux, Git, and engineering prototyping skills."
        ),
        "Embedded / Firmware": (
            "Robotics and Digital Systems Engineering student with hands-on experience developing "
            "C/C++ firmware, FreeRTOS applications, hardware interfaces, and robotic systems. Built "
            "and debugged software across FRDM-KL25Z, ESP32, Raspberry Pi, and FPGA platforms using "
            "UART, SPI, I2C, PWM, interrupts, Linux, and board-level testing."
        ),
        "Software Engineering": (
            "Robotics and Digital Systems Engineering student who built C++ matching and graph "
            "applications, Python services, and hardware-connected software. Applies object-oriented "
            "programming, data structures, algorithms, REST APIs, Linux, Git, and testing to implement "
            "modular, maintainable software across multidisciplinary engineering projects."
        ),
        "Backend / Data": (
            "Robotics and Digital Systems Engineering student with project experience building Python "
            "services, REST APIs, MySQL data pipelines, and live dashboards. Developed software that "
            "connects sensors, databases, and web clients using Flask, SQL, Linux, Git, structured "
            "testing, and object-oriented design."
        ),
        "FPGA / Digital Design": (
            "Robotics and Digital Systems Engineering student with project experience designing FPGA "
            "controllers, Verilog modules, testbenches, and hardware interfaces. Built digital systems "
            "for robotic control using Intel MAX 10, SystemVerilog, GPIO, PWM, UART, simulation, and "
            "signal-level testing across integrated hardware components."
        ),
        "AI / API Integration": (
            "Robotics and Digital Systems Engineering student who built Python APIs, database-backed "
            "services, dashboards, and connected embedded applications. Applies Flask, REST APIs, "
            "MySQL, algorithms, Linux, Git, and structured testing to integrate software components "
            "and technical data across multidisciplinary engineering systems."
        ),
        "Robotics / Controls": (
            "Robotics and Digital Systems Engineering student with project experience building robotic "
            "controllers, embedded communication, sensor interfaces, and motion software. Developed "
            "systems using C/C++, Python, ESP32, FRDM-KL25Z, FPGA, UART, PWM, interrupts, Linux, and "
            "hardware debugging across integrated control platforms."
        ),
        "Maps / Routing / Geospatial": (
            "Robotics and Digital Systems Engineering student with experience building C++ graph "
            "applications, Python services, and hardware-connected systems. Applies object-oriented "
            "programming, data structures, graph algorithms, path validation, REST APIs, Linux, Git, "
            "and testing to develop modular software for routing, data processing, and multidisciplinary "
            "engineering problems."
        ),
        "Full Stack / Web": (
            "Robotics and Digital Systems Engineering student with experience building full-stack "
            "applications using Next.js, TypeScript, FastAPI, Python, and PostgreSQL. Applies structured "
            "validation, authenticated routes, REST APIs, relational data modeling, Git, Docker, and "
            "testing to develop maintainable web platforms and reusable software interfaces."
        ),
        "Developer Tools / Productivity": (
            "Robotics and Digital Systems Engineering student with experience building developer-facing "
            "tools, automated document workflows, and full-stack applications. Applies Python, TypeScript, "
            "FastAPI, Pydantic, PostgreSQL, Jinja2, LaTeX, Git, Docker, and testing to create reusable "
            "interfaces with deterministic validation and structured outputs."
        ),
    }
    return summaries[classification]


def score_project_for_job(
    item: dict[str, Any],
    classification: str,
    job_requirements: str,
) -> float:
    name = _item_value(item, "name", "title")
    priority = PROJECT_PRIORITIES.get(classification, [])
    project_text = json.dumps(item, ensure_ascii=False).lower()
    job_text = sanitize_resume_text(job_requirements).lower()
    if classification == "Talent Community":
        from app.services.talent_matching import score_talent_project
        return score_talent_project(item, job_requirements)
    if classification == "Solutions / API Integration":
        # Score facts in project evidence against responsibilities, not the degree.
        signals = (
            (("rest api", "restful api", "api integration"), ("rest api", "fastapi", "flask", "api"), 18),
            (("python",), ("python",), 12),
            (("technical integration", "integration", "integrations"), ("integrat", "connect", "coordinat", "backend and frontend", "full-stack"), 14),
            (("data pipeline", "data collection", "data processing"), ("sensor data", "data storage", "database", "postgresql", "mysql"), 10),
            (("dashboard", "visualization"), ("dashboard", "visualization", "chart.js"), 10),
            (("troubleshoot", "debug"), ("debug", "validat", "test"), 10),
            (("automation", "automate"), ("automat", "workflow"), 9),
            (("developer", "support", "partner"), ("platform", "interface", "service", "web"), 6),
            (("json", "structured data"), ("json", "structured data", "validation"), 5),
        )
        score = 8.0
        for job_terms, evidence_terms, weight in signals:
            if any(term in job_text for term in job_terms) and any(term in project_text for term in evidence_terms):
                score += weight
        # Technology overlap is direct evidence, but is not a replacement for responsibilities.
        score += min(12, 3 * sum(
            _keyword_present(str(tech), job_text) for tech in item.get("technologies", []) or []
        ))
        if any(term in project_text for term in ("trading", "stock exchange", "graph game")):
            score -= 10
        if "fpga" in project_text and not any(term in job_text for term in ("fpga", "rtl", "digital design")):
            score -= 8
        if item.get("project_type") == "complete project":
            score += 6
        elif item.get("project_type") in {"focused technical exercise", "laboratory practice"}:
            score -= 6
        return min(100.0, score)
    if classification == "Robotics Research":
        positive = (
            "robot", "robotics", "embedded", "control", "sensor", "actuator", "motor",
            "encoder", "microcontroller", "freertos", "rtos", "esp32", "kl25z", "arm",
            "computer vision", "opencv", "camera", "hardware", "electronics", "real-time",
            "raspberry pi", "uart", "i2c", "spi", "pwm", "physical system",
        )
        negative = ("frontend", "crud", "website", "full-stack", "full stack", "trading", "game")
        base = 18.0 + min(72.0, sum(8 for term in positive if _keyword_present(term, project_text)))
        base += min(10.0, sum(2 for term in positive if _keyword_present(term, job_text)))
        if not any(_keyword_present(term, project_text) for term in positive):
            base -= sum(5 for term in negative if _keyword_present(term, project_text))
        for group in research_focus_groups(job_text):
            overlap = sum(
                1 for term in RESEARCH_SEMANTIC_GROUPS[group]
                if _keyword_present(term, project_text)
            )
            base += min(24, overlap * 6)
    elif classification == "Maps / Routing / Geospatial":
        base = 70 - priority.index(name) * 13 if name in priority else 12
    else:
        base = 58 - priority.index(name) * 7 if name in priority else 12
    technologies = [
        sanitize_resume_text(value).lower()
        for value in item.get("technologies", [])
    ]
    score = float(base)
    if classification == "Maps / Routing / Geospatial":
        signals = (
            (("graph", "nodes", "edges"), 20),
            (("traversal", "path", "route"), 20),
            (("c++",), 12),
            (("algorithm", "data structures"), 12),
            (("python",), 8),
            (("api", "data service", "data generation", "data transformation"), 8),
            (("testing", "debugging", "validation"), 5),
        )
        for terms, weight in signals:
            job_match = any(_keyword_present(term, job_text) for term in terms)
            project_match = any(
                _keyword_present(term, project_text) or term in technologies
                for term in terms
            )
            if job_match and project_match:
                score += weight
        if any(term in project_text for term in ("embedded", "fpga", "freertos", "uart")):
            score += 1
        if (
            any(term in job_text for term in MAP_PHYSICAL_TERMS)
            and any(term in project_text for term in ("robot", "movement", "hardware", "motor"))
        ):
            score += 8
    else:
        matched_technologies = {
            value for value in technologies if _keyword_present(value, job_text)
        }
        score += min(18, len(matched_technologies) * 3)
        if (
            name == "Stock Exchange Matching Engine"
            and classification == "Software Engineering"
            and any(term in job_text for term in (
                "c++ software", "c++ developer", "c++ engineering", "c++ intern",
            ))
        ):
            score += 24
        if (
            name == "SkiliAir Air Quality Monitoring System"
            and classification in {"AI / API Integration", "Developer Tools / Productivity"}
            and any(_keyword_present(term, job_text) for term in (
                "automation", "database", "sql", "rest api", "python",
            ))
        ):
            score += 12
    return min(100.0, max(0.0, score))


def _project_score(item: dict[str, Any], job_text: str, classification: str) -> float:
    return score_project_for_job(item, classification, job_text)


def _project_evidence_matches(item: dict[str, Any], job_text: str) -> list[dict[str, Any]]:
    """Conservative semantic matches, each tied to a stored project fact."""
    facts = [*item.get("technologies", []), *item.get("bullets", [])]
    rules = (
        ("REST APIs", ("restful api", "rest api"), ("rest api",)),
        ("data pipelines", ("data pipeline", "data collection"), ("mysql logging", "data storage")),
        ("dashboards", ("dashboard", "visualization"), ("dashboard", "chart.js visualization")),
        ("technical troubleshooting", ("troubleshoot", "debug"), ("debug", "isolat", "fault")),
        ("technical integrations", ("technical integration", "integrations"), ("integrat", "connect", "coordinat")),
    )
    matches: list[dict[str, Any]] = []
    for label, job_aliases, fact_aliases in rules:
        if not any(alias in job_text.lower() for alias in job_aliases):
            continue
        fact = next((str(fact) for fact in facts if any(alias in str(fact).lower() for alias in fact_aliases)), None)
        if fact:
            matches.append({"job_term": label, "matched_candidate_fact": fact,
                            "match_type": "SEMANTIC_SUPPORTED", "confidence": 0.8,
                            "evidence_id": _item_value(item, "name", "title")})
    return matches


def _project_bullets(item: dict[str, Any]) -> list[str]:
    bullets = _clean_list(item.get("bullets"), limit=3)
    unique: list[str] = []
    seen: set[str] = set()
    for bullet in bullets:
        if _contains_artificial_language(bullet):
            continue
        normalized = re.sub(r"[^a-z0-9 ]", "", bullet.lower())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(bullet)
    return unique


def _internship_radar_bullets(classification: str) -> list[str]:
    variants = {
        "AI / API Integration": [
            "Integrated the OpenAI API with structured outputs to transform verified profile data and job requirements into validated resume content.",
            "Built validation safeguards that reject unsupported skills, certifications, technologies, and experience before rendering a resume.",
            "Implemented dynamic Jinja2 and LaTeX generation with automated compilation and PDF validation for consistent one-page resumes.",
        ],
        "Backend / Data": [
            "Developed FastAPI endpoints and PostgreSQL models for jobs, verified profiles, generated resumes, and version history.",
            "Implemented Pydantic validation, SQLAlchemy persistence, authenticated requests, and secure PDF and LaTeX delivery throughout the platform.",
            "Integrated structured AI processing with deterministic validation and document-generation services for reusable, job-specific resume workflows.",
        ],
    }
    if classification in variants:
        return variants[classification]
    return [
        "Built a full-stack platform using Next.js, TypeScript, FastAPI, and PostgreSQL to track internships and generate job-specific resumes.",
        "Implemented modular backend services, structured data validation, authenticated routes, and persistent resume versioning with FastAPI and PostgreSQL.",
        "Developed reusable interfaces for PDF preview, LaTeX source viewing, downloading, and job-specific content comparison.",
    ]


def _visible_project_technologies(
    item: dict[str, Any],
    job_text: str,
    classification: str,
    verified_skills: set[str],
) -> list[str]:
    technologies = [
        sanitize_resume_text(value)
        for value in item.get("technologies", [])
        if sanitize_resume_text(value).lower() in verified_skills
    ]
    if _item_value(item, "name", "title") != "Internship Radar - AI Resume Tailoring Platform":
        return technologies[:5]
    preferred = {
        "Backend / Data": ["FastAPI", "PostgreSQL", "SQLAlchemy", "Pydantic", "Python"],
        "AI / API Integration": ["OpenAI API", "Pydantic", "Python", "Jinja2", "FastAPI"],
        "Full Stack / Web": ["Next.js", "TypeScript", "FastAPI", "PostgreSQL", "Auth.js"],
        "Developer Tools / Productivity": ["Python", "TypeScript", "Pydantic", "Jinja2", "Docker"],
    }.get(
        classification,
        ["Next.js", "TypeScript", "FastAPI", "PostgreSQL", "OpenAI API"],
    )
    requested = [
        value for value in technologies
        if _keyword_present(value, job_text)
    ]
    return list(dict.fromkeys(requested + preferred + technologies))[:5]


def _select_projects(
    job: Any,
    profile: Any,
    classification: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    job_text = " ".join(
        sanitize_resume_text(value)
        for value in (
            getattr(job, "title", ""), getattr(job, "description", ""),
            getattr(job, "requirements", ""), getattr(job, "preferred_qualifications", ""),
        )
    )
    scored: list[tuple[float, dict[str, Any]]] = []
    verified_skills = {skill.lower() for skill in build_verified_skill_registry(profile)}
    for item in profile.projects_json:
        if not isinstance(item, dict):
            continue
        if item.get("is_resume_eligible", True) is not True:
            continue
        technologies = _visible_project_technologies(
            item, job_text, classification, verified_skills
        )
        score = _project_score(item, getattr(job, "talent_ranking_context", job_text), classification)
        name = _item_value(item, "name", "title")
        repository_url = _item_value(item, "repository_url", "github_url", "url") or None
        github_url = (
            repository_url
            if item.get("is_public", True) and _valid_url(repository_url)
            else None
        )
        live_url = _item_value(item, "live_url") or None
        scored.append((score, {
            "name": name,
            "technologies": technologies,
            "status": _item_value(item, "status"),
            "dates": _item_value(item, "dates", "date"),
            "github_url": github_url,
            "live_url": live_url if _valid_url(live_url) else None,
            "relevance_score": score,
            "bullets": sorted(_project_bullets(item), key=lambda bullet: -sum(
                    _keyword_present(term, bullet.lower()) and _keyword_present(term, job_text.lower())
                    for term in ("api", "python", "integrat", "dashboard", "data", "debug", "automat", "uart", "pwm", "fpga")
                )),
        }))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if classification == "Talent Community" and limit == 4 and len(scored) > 4:
        targets = getattr(job, "target_role_categories", [])
        if "Software Engineering" in targets:
            # Add complementary software evidence after the strongest three projects.
            from app.services.talent_matching import score_talent_project
            software_context = json.dumps({"company_areas": [], "targets": ["Software Engineering"]})
            sources = _profile_project_map(profile)
            supporting = max(scored[3:], key=lambda pair: score_talent_project(sources[pair[1]["name"]], software_context))
            scored = scored[:3] + [supporting] + [pair for pair in scored[3:] if pair is not supporting]
    return [project for _, project in scored[:limit]]


def _maps_fourth_project_allowed(
    job: Any,
    classification: str,
    projects: list[Any],
    minimum_score: float = 55,
) -> bool:
    if classification != "Maps / Routing / Geospatial" or len(projects) < 4:
        return True
    fourth = projects[3]
    if fourth.name != "MATT Web-Controlled Writing Robot":
        return fourth.relevance_score >= minimum_score
    text = " ".join(
        sanitize_resume_text(value).lower()
        for value in (
            getattr(job, "title", ""), getattr(job, "description", ""),
            getattr(job, "requirements", ""), getattr(job, "preferred_qualifications", ""),
        )
    )
    return (
        fourth.relevance_score >= minimum_score
        and any(term in text for term in MAP_PHYSICAL_TERMS)
    )


def _fourth_project_adds_value(projects: list[Any]) -> bool:
    if len(projects) < 4:
        return False
    existing = {
        sanitize_resume_text(technology).lower()
        for project in projects[:3]
        for technology in project.technologies
    }
    candidate = {
        sanitize_resume_text(technology).lower()
        for technology in projects[3].technologies
    }
    return len(candidate - existing) >= 2 or projects[3].relevance_score >= 70


def _select_courses(
    job: Any,
    profile: Any,
    classification: str,
    limit: int = 2,
) -> list[dict[str, Any]]:
    if classification in {"Embedded / Firmware", "FPGA / Digital Design", "Hardware / Systems Integration"}:
        return []
    job_text = " ".join(
        sanitize_resume_text(value).lower()
        for value in (
            getattr(job, "title", ""), getattr(job, "description", ""),
            getattr(job, "requirements", ""), getattr(job, "preferred_qualifications", ""),
        )
    )
    scored: list[tuple[float, dict[str, Any]]] = []
    for raw in profile.coursework_json:
        if not isinstance(raw, dict):
            continue
        name = _item_value(raw, "name")
        priority = _item_value(raw, "priority").lower() or "normal"
        if name == "Programming for Everybody (Getting Started with Python)":
            introductory = any(
                term in job_text for term in ("introductory", "beginner", "getting started")
            )
            if len(profile.projects_json) >= 3 and not introductory:
                continue
        score = 10.0 if priority == "low" else 40.0
        areas = [
            sanitize_resume_text(value)
            for value in raw.get("areas", [])
            if sanitize_resume_text(value)
        ]
        score += sum(8 for area in areas if _keyword_present(area, job_text))
        if name == "Python Data Structures" and classification in {
            "Software Engineering", "Backend / Data", "AI / API Integration",
            "Maps / Routing / Geospatial", "Full Stack / Web",
            "Developer Tools / Productivity",
        }:
            score += 24
        if name == "Using Python to Access Web Data" and classification in {
            "Backend / Data", "AI / API Integration", "Full Stack / Web",
        }:
            score += 24
        scored.append((score, {
            "name": name,
            "institution": _item_value(raw, "institution"),
            "issued": _item_value(raw, "issued"),
            "areas": areas[:4],
            "priority": priority,
        }))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [course for _, course in scored[:limit]]


def _canonical_education(profile: Any) -> dict[str, Any]:
    item = profile.education_json[0]
    return {
        "institution": _item_value(item, "institution"),
        "degree": _item_value(item, "degree"),
        "location": _item_value(item, "location"),
        "graduation": _item_value(item, "graduation"),
        "gpa": _item_value(item, "gpa"),
        "coursework": [],
    }


def _job_education(profile: Any, job: Any) -> dict[str, Any]:
    education = _canonical_education(profile)
    posting = " ".join(str(getattr(job, key, "") or "") for key in (
        "description", "requirements", "preferred_qualifications",
    ))
    if re.search(r"graduation.{0,35}(?:MM/YY|MM / YY)", posting, re.I):
        graduation = education["graduation"]
        match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)", graduation, re.I)
        if match:
            months = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
            education["graduation"] = f"Expected Graduation: {months.index(match.group(1).lower()) + 1:02d}/{match.group(2)[2:]}"
    return education


def _certifications(profile: Any, selected_names: set[str] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "name": _item_value(item, "name", "title"),
            "issuer": _item_value(item, "issuer", "organization"),
            "date": _item_value(item, "date", "issued"),
            "url": _item_value(item, "url", "credential_url"),
        }
        for item in profile.certifications_json
        if isinstance(item, dict)
        and _item_value(item, "name", "title")
        and _item_value(item, "type").lower() != "language"
        and (selected_names is None or _item_value(item, "name", "title") in selected_names)
    ]


def _certifications_from_tailoring_plan(plan: TailoringPlan, profile: Any) -> list[dict[str, Any]]:
    """Render only certifications whose verified evidence helped this job."""
    return _certifications(profile, set(plan.resume_decisions.selected_certifications))


def _languages_for_job(job: Any, profile: Any, classification: str = "") -> list[str]:
    """Use canonical language evidence shared by every resume target."""
    verified = resume_language_lines(profile)
    if classification == "Talent Community":
        return verified
    job_text = " ".join(
        sanitize_resume_text(getattr(job, field, ""))
        for field in ("title", "location", "description", "requirements", "preferred_qualifications")
    ).lower()
    selected: list[str] = []
    for language in verified:
        name = language.split("—", 1)[0].split("-", 1)[0].strip().lower()
        if name in {"spanish", "english"}:
            selected.append(language)
        elif name == "french" and any(term in job_text for term in ("french", "français", "france")):
            selected.append(language)
        elif name == "german" and any(term in job_text for term in ("german", "deutsch", "germany")):
            selected.append(language)
    return selected


def _scoped_tailoring_plan(
    job: Any,
    profile: Any,
    *,
    project_limit: int,
    existing_plan: TailoringPlan | None = None,
) -> TailoringPlan | None:
    """Resolve an exact plan for the current job/profile snapshot.

    Older import/test utilities sometimes construct anonymous in-memory
    profiles. They retain the legacy deterministic path; production
    ``ResumeProfile`` records always carry ``user_id`` and therefore cannot
    fall back to another candidate's data.
    """
    owner_user_id = sanitize_resume_text(getattr(profile, "user_id", ""))
    if not owner_user_id:
        return None
    if existing_plan is not None and _tailoring_plan_matches_job(existing_plan, job, profile):
        # A Phase 1 plan may be an evidence snapshot only.  It is valid for
        # this user/job but cannot be rendered until its Phase 2 decisions
        # exist.  Resolve those decisions from the same snapshot rather than
        # falling back to legacy skill selection.
        if existing_plan.resume_decisions.status == "PLANNED":
            return existing_plan
        return decide_resume_content(existing_plan, profile, project_limit=project_limit)
    return decide_resume_content(
        build_tailoring_plan(job, profile, owner_user_id=owner_user_id),
        profile,
        project_limit=project_limit,
    )


def _tailoring_plan_matches_job(
    tailoring_plan: TailoringPlan,
    job: Any,
    profile: Any,
) -> bool:
    """Return true only for the exact user-owned, current posting snapshot."""
    owner_user_id = sanitize_resume_text(getattr(profile, "user_id", ""))
    if tailoring_plan.owner_user_id != owner_user_id:
        return False
    current_job_id = getattr(job, "id", None)
    if current_job_id is not None and tailoring_plan.job_id != current_job_id:
        return False
    if not tailoring_plan.job_content_hash or tailoring_plan.job_content_hash != job_content_hash(job):
        return False
    # A classification/ranking rule change can make an otherwise content-identical
    # snapshot stale (for example, an MCU role previously treated as software).
    # Keep that old snapshot reproducible, but build a fresh plan for new resumes.
    if tailoring_plan.role_categories != _role_categories(job):
        return False
    existing_primary = tailoring_plan.resume_decisions.primary_role_category
    return not existing_primary or existing_primary == _primary_resume_role_category(tailoring_plan)


def _assert_tailoring_plan_matches_job(
    tailoring_plan: TailoringPlan,
    job: Any,
    profile: Any,
) -> None:
    """Guard direct callers; normal generation resolves stale plans first."""
    if not _tailoring_plan_matches_job(tailoring_plan, job, profile):
        raise ValueError("TailoringPlan does not match the current job snapshot or owner.")


def _projects_from_tailoring_plan(
    plan: TailoringPlan,
    profile: Any,
) -> list[dict[str, Any]]:
    sources = _profile_project_map(profile)
    registry = build_verified_skill_registry(profile)
    selected_skill_order = {
        skill: index for index, skill in enumerate(plan.resume_decisions.selected_skills)
    }
    projects: list[dict[str, Any]] = []
    for name in plan.resume_decisions.selected_projects:
        source = sources.get(name)
        if source is None:
            continue
        technologies = [
            canonicalize_skill(value)
            for value in source.get("technologies", [])
            if canonicalize_skill(value) in registry
        ]
        technologies = list(dict.fromkeys(technologies))
        technologies.sort(key=lambda item: selected_skill_order.get(item, len(selected_skill_order)))
        repository_url = _item_value(source, "repository_url", "github_url", "url") or None
        live_url = _item_value(source, "live_url") or None
        projects.append({
            "name": name,
            "technologies": technologies[:5],
            "status": _item_value(source, "status"),
            "dates": _item_value(source, "dates", "date"),
            "github_url": (
                repository_url
                if source.get("is_public", True) and _valid_url(repository_url)
                else None
            ),
            "live_url": live_url if _valid_url(live_url) else None,
            "relevance_score": plan.resume_decisions.selected_project_scores.get(name, 0),
            # Preserve the candidate's source bullets. Classification-specific
            # canned project copy is not part of the plan-based path.
            "bullets": _project_bullets(source),
        })
    return projects


def _courses_from_tailoring_plan(plan: TailoringPlan, profile: Any) -> list[ResumeCourseItem]:
    sources = {
        _item_value(item, "name"): item
        for item in profile.coursework_json
        if isinstance(item, dict) and _item_value(item, "name")
    }
    return [
        ResumeCourseItem.model_validate({
            "name": name,
            "institution": _item_value(sources[name], "institution"),
            "issued": _item_value(sources[name], "issued"),
            "areas": [sanitize_resume_text(item) for item in sources[name].get("areas", [])][:4],
            "priority": _item_value(sources[name], "priority") or "normal",
        })
        for name in plan.resume_decisions.selected_coursework
        if name in sources
    ]


def _experience_from_tailoring_plan(plan: TailoringPlan, profile: Any) -> list[dict[str, Any]]:
    sources = {
        _item_value(item, "organization", "company", "title"): item
        for item in profile.experience_json
        if isinstance(item, dict) and _item_value(item, "organization", "company", "title")
    }
    experience: list[dict[str, Any]] = []
    for name in plan.resume_decisions.selected_experience:
        source = sources.get(name)
        if source is None:
            continue
        bullets = _clean_list(source.get("bullets", source.get("highlights", [])), limit=3)
        if bullets:
            experience.append({
                "title": _item_value(source, "title", "role"),
                "organization": _item_value(source, "organization", "company"),
                "location": _item_value(source, "location"),
                "dates": _item_value(source, "dates", "date"),
                "bullets": bullets,
            })
    return experience


def _skill_matches_from_tailoring_plan(plan: TailoringPlan) -> list[ResumeSkillMatch]:
    matches: list[ResumeSkillMatch] = []
    for skill in plan.resume_decisions.selected_skills:
        supporting = [
            mapping for mapping in plan.requirement_evidence
            if mapping.match_state != SkillMatchState.NOT_FOUND
            and any(item.canonical_skill == skill for item in mapping.matched_candidate_evidence)
        ]
        if supporting:
            primary = max(supporting, key=lambda item: item.requirement.importance_weight)
            evidence = [
                f"{item.source.value.title()}: {item.source_name}"
                for item in primary.matched_candidate_evidence
                if item.canonical_skill == skill
            ]
            match_type = primary.requirement.importance.value
            score = min(100, primary.requirement.importance_weight)
            reason = primary.explanation
        else:
            evidence = [
                f"{item.source.value.title()}: {item.source_name}"
                for item in plan.resume_decisions.selected_skill_evidence.get(skill, [])
            ]
            match_type = "contextual"
            score = 20
            reason = "Demonstrated in a selected project."
        category = next(
            (group["name"] for group in plan.resume_decisions.selected_skill_categories if skill in group["items"]),
            "Technical",
        )
        matches.append(ResumeSkillMatch(
            skill=skill, category=category, match_type=match_type,
            score=score, reason=reason, evidence=list(dict.fromkeys(evidence)),
            job_occurrences=len(supporting),
        ))
    return matches


def _headline_from_tailoring_plan(profile: Any, plan: TailoringPlan) -> str:
    # Preserve the verified profile headline verbatim (the validation layer
    # treats it as candidate-owned contact/profile evidence) while adding only
    # as much job direction as the four-part rendering limit permits.
    profile_headline = sanitize_resume_text(profile.headline)
    parts = [item.strip() for item in profile_headline.split("|") if item.strip()]
    for item in plan.resume_decisions.headline_direction.split("|"):
        cleaned = item.strip()
        if cleaned and cleaned not in parts and len(parts) < 4:
            parts.append(cleaned)
    return " | ".join(parts)


def _summary_from_tailoring_plan(profile: Any, plan: TailoringPlan) -> str:
    decisions = plan.resume_decisions
    role = decisions.primary_role_category or (plan.role_categories[0] if plan.role_categories else "Engineering")
    projects = ", ".join(decisions.selected_projects[:2]) or "technical projects"
    skills = ", ".join(decisions.selected_skills[:4]) or "engineering skills"
    covered = [
        item.requirement.normalized_requirement
        for item in plan.requirement_evidence
        if item.match_state != SkillMatchState.NOT_FOUND and item.requirement.type == "technology"
    ]
    requirements = ", ".join(covered[:3]) or "the stated role requirements"
    return (
        f"{sanitize_resume_text(profile.headline)} with hands-on project experience in {skills}. "
        f"For this {role} role, brings evidence from {projects} to address {requirements}. "
        "Emphasizes implementation, integration, testing, and debugging through documented technical work."
    )


def _trace_from_tailoring_plan(plan: TailoringPlan) -> dict[str, Any]:
    """Expose the plan's evidence decisions through the pre-existing trace field."""
    decisions = plan.resume_decisions
    evaluations = {item.project_name: item for item in plan.project_evaluations}
    ranked_names = sorted(
        evaluations,
        key=lambda name: (
            -decisions.selected_project_scores.get(name, evaluations[name].job_relevance),
            name.casefold(),
        ),
    )
    project_ranking = []
    for name in ranked_names:
        evaluation = evaluations[name]
        matched_requirements = [
            mapping.requirement.normalized_requirement
            for mapping in plan.requirement_evidence
            if any(
                evidence.source == EvidenceSource.PROJECT and evidence.source_name == name
                for evidence in mapping.matched_candidate_evidence
            )
        ]
        project_ranking.append({
            "name": name,
            "score": decisions.selected_project_scores.get(name, evaluation.job_relevance),
            "evidence": evaluation.evidence_notes,
            "semantic_matches": matched_requirements,
        })
    return {
        "job": plan.job_title,
        "classification": (
            plan.resume_decisions.primary_role_category
            or (plan.role_categories[0] if plan.role_categories else "General Engineering")
        ),
        "role_categories": plan.role_categories,
        "requirements": {
            "required": plan.required_skills,
            "preferred": plan.preferred_skills,
            "responsibilities": plan.responsibilities,
        },
        "project_ranking": project_ranking,
        "selected_skills": decisions.selected_skills,
        "rejected_job_skills": decisions.missing_requirements,
        "rejected_job_matches": [
            {"job_term": skill, "match_type": SkillMatchState.NOT_FOUND.value,
             "reason": "No verified candidate evidence"}
            for skill in decisions.missing_requirements
        ],
    }


def generate_local_content(
    job: Any,
    profile: Any,
    project_limit: int = 4,
    tailoring_plan: TailoringPlan | None = None,
) -> TailoredResumeContent:
    if getattr(job, "portfolio_profile_id", None):
        if getattr(job, "portfolio_profile_id", None) == "best":
            from app.services.best_resume import generate_best_resume_content
            return generate_best_resume_content(job, profile)
        from app.services.resume_studio import generate_studio_content
        return generate_studio_content(job, profile)
    classification = classify_job(job)
    if classification == "KOSPIE / Germany Engineering":
        from app.services.kospie import generate_kospie_content
        return generate_kospie_content(job, profile)
    if classification != "Talent Community":
        tailoring_plan = _scoped_tailoring_plan(
            job,
            profile,
            project_limit=project_limit,
            existing_plan=tailoring_plan,
        )
    if tailoring_plan is not None:
        _assert_tailoring_plan_matches_job(tailoring_plan, job, profile)
    analysis = getattr(job, "analysis", None)
    from app.services.scoring import _skill_matches
    analyzed_matches, missing_required, missing_preferred, _ = _skill_matches(job, profile)
    missing = _clean_list([*missing_required, *missing_preferred], limit=8)
    matched = _clean_list(analyzed_matches, limit=12)
    overall_score = getattr(analysis, "overall_score", None)
    if tailoring_plan is not None:
        selected_projects = _projects_from_tailoring_plan(tailoring_plan, profile)
        skill_result = {
            "categories": tailoring_plan.resume_decisions.selected_skill_categories,
            "selected_skills": tailoring_plan.resume_decisions.selected_skills,
            "matches": _skill_matches_from_tailoring_plan(tailoring_plan),
            "verification": {
                "all_verified": True,
                "verified": tailoring_plan.resume_decisions.selected_skills,
                "removed": [],
                "registry_size": len(build_verified_skill_registry(profile)),
            },
        }
        missing = tailoring_plan.resume_decisions.missing_requirements
        matched = [
            item.requirement.normalized_requirement
            for item in tailoring_plan.requirement_evidence
            if item.requirement.type == "technology"
            and item.match_state != SkillMatchState.NOT_FOUND
        ]
        selected_coursework = _courses_from_tailoring_plan(tailoring_plan, profile)
        selected_certifications = _certifications_from_tailoring_plan(tailoring_plan, profile)
        selected_experience = _experience_from_tailoring_plan(tailoring_plan, profile)
        headline = _headline_from_tailoring_plan(profile, tailoring_plan)
        summary = _summary_from_tailoring_plan(profile, tailoring_plan)
    else:
        # Legacy fallback for anonymous in-memory callers only. Production
        # ResumeProfile records are scoped and use TailoringPlan above.
        selected_projects = _select_projects(job, profile, classification, project_limit)
        if len(selected_projects) == 4 and classification != "Talent Community":
            from app.services.kospie import kospie_project_assessment
            source = _profile_project_map(profile)[selected_projects[3]["name"]]
            evidence = {"name": "", "bullets": source.get("bullets", [])}
            for key in ("project_type", "scope_type", "status"):
                if key in source:
                    evidence[key] = source[key]
            assessment = kospie_project_assessment(evidence, [])
            if (
                assessment["components"]["resume_value"] < 40
                or (assessment["project_type"] == "laboratory_practice" and assessment["components"]["technical_depth"] < 75)
                or not _maps_fourth_project_allowed(job, classification, [SimpleNamespace(**project) for project in selected_projects])
            ):
                selected_projects = selected_projects[:3]
        skill_result = select_job_skills(
            job,
            profile,
            classification,
            selected_project_names={project["name"] for project in (selected_projects if classification == "Talent Community" else selected_projects[:3])},
        )
        selected_coursework = (
            [ResumeCourseItem.model_validate(course) for course in _select_courses(
                job, profile, classification, limit=2,
            )]
            if classification == "Talent Community" else []
        )
        selected_experience = []
        selected_certifications = []
        headline = (sanitize_resume_text(profile.headline) if classification == "Talent Community" else _profile_headline(profile, classification, skill_result["selected_skills"]))
        summary = "" if classification == "Talent Community" else _profile_summary(profile, classification, skill_result["selected_skills"])
    research_interests = []
    if classification == "Robotics Research":
        verified = build_verified_skill_registry(profile)
        for interest in ("Robotics", "Embedded Systems", "Autonomous Systems", "Controls", "Computer Vision"):
            if interest in verified:
                research_interests.append(interest)
    content = TailoredResumeContent(
        target_role=sanitize_resume_text(job.title),
        classification=classification,
        application_type=getattr(job, "application_type", "STANDARD_JOB"),
        headline=headline,
        summary=summary,
        skill_categories=skill_result["categories"],
        selected_skills=skill_result["selected_skills"],
        job_skill_matches=skill_result["matches"],
        skill_verification=skill_result["verification"],
        education=_job_education(profile, job),
        experience=selected_experience,
        projects=selected_projects,
        coursework=selected_coursework,
        certifications=selected_certifications,
        languages=_languages_for_job(job, profile, classification),
        research_interests=research_interests,
        opportunity_research_areas=[
            sanitize_resume_text(item) for item in (getattr(job, "research_areas", []) or [])
            if sanitize_resume_text(item)
        ],
        section_order=(
            ["education", "skills", "projects", "coursework", "languages"] if classification == "Talent Community" else
            ["education", "skills", "research_interests", "projects", "experience", "certifications", "languages"]
            if classification == "Robotics Research" else
            ["summary", "education", "projects", "skills", "coursework", "certifications", "languages"]
        ),
        match_score=float(overall_score) if overall_score is not None else 0,
        keywords_used=[skill for skill in matched if skill.casefold() in {item.casefold() for item in skill_result["selected_skills"]}],
        keywords_missing=missing,
        unsupported_requirements=missing,
        changes=([{
            "section": "Projects",
            "description": "Prioritized robotics, embedded, control, sensing, and hardware integration projects.",
            "reason": "Technical evidence is most relevant to university laboratories and research internships.",
        }, {
            "section": "Education",
            "description": "Moved Education to the top for an academic audience.",
            "reason": "Degree progress and academic preparation matter strongly to research supervisors.",
        }, {
            "section": "Skills",
            "description": "Selected only verified robotics-research skills and deprioritized unrelated web work.",
            "reason": "Candidate evidence plus opportunity relevance; opportunity keywords never create skills.",
        }] if classification == "Robotics Research" else [{
            "section": "Tailoring",
            "description": (
                "Used the job-specific TailoringPlan to select evidence-backed projects and skills."
                if tailoring_plan is not None else
                f"Classified the vacancy as {classification} and ranked canonical projects."
            ),
            "reason": (
                "Requirement coverage, verified candidate evidence, project quality, and complementary portfolio value."
                if tailoring_plan is not None else
                "Reusable job classification, skill matrix, and project priority rules."
            ),
        }]),
        warnings=(
            ["Generated locally from canonical profile data; review before applying."]
            + ([f"Unsupported requirements omitted: {', '.join(missing)}"] if missing else [])
        ),
        tailoring_plan=tailoring_plan.model_dump(mode="json") if tailoring_plan is not None else {},
        tailoring_trace=(
            _trace_from_tailoring_plan(tailoring_plan)
            if tailoring_plan is not None else {
            "job": sanitize_resume_text(job.title),
            "classification": classification,
            "role_categories": weighted_role_categories(job),
            "requirements": extract_job_requirements(job),
            "project_ranking": [
                {"name": item["name"], "score": item["relevance_score"],
                 "evidence": item["technologies"],
                 "semantic_matches": _project_evidence_matches(
                     _profile_project_map(profile)[item["name"]],
                     " ".join((job.description or "", job.requirements or "", getattr(job, "preferred_qualifications", "") or "")),
                 )}
                for item in _select_projects(job, profile, classification, limit=len(profile.projects_json))
            ],
            "selected_skills": skill_result["selected_skills"],
            "rejected_job_skills": [skill for skill in ("Java", "SDKs", "Webhooks")
                                    if _keyword_present(skill, " ".join((job.description or "", job.requirements or "", getattr(job, "preferred_qualifications", "") or "")))
                                    and skill not in build_verified_skill_registry(profile)],
            "rejected_job_matches": [
                {"job_term": skill, "match_type": "NOT_FOUND", "reason": "No verified candidate evidence"}
                for skill in ("Java", "SDKs", "Webhooks")
                if _keyword_present(skill, " ".join((job.description or "", job.requirements or "", getattr(job, "preferred_qualifications", "") or "")))
                and skill not in build_verified_skill_registry(profile)
            ],
        }),
    )
    return validate_generated_resume(content, profile, job)


def _compose_model_output(
    output: ModelTailoringOutput,
    job: Any,
    profile: Any,
    tailoring_plan: TailoringPlan | None = None,
) -> TailoredResumeContent:
    if tailoring_plan is not None:
        # Phase 2 locks both the selections and the evidence-derived wording.
        # Model prose is not allowed to introduce an unsupported implication;
        # a future editing phase can add sentence-level claim verification.
        return generate_local_content(job, profile, tailoring_plan=tailoring_plan)
    requested_skills = [
        sanitize_resume_text(item)
        for group in output.skill_categories
        for item in group.items
    ]
    classification = classify_job(job)
    ranked_projects = _select_projects(job, profile, classification, limit=4)
    skill_result = select_job_skills(
        job,
        profile,
        classification,
        selected_project_names={project["name"] for project in ranked_projects},
        model_requested=requested_skills,
    )
    return TailoredResumeContent(
        target_role=sanitize_resume_text(job.title),
        classification=classification,
        headline=_profile_headline(profile, classification, skill_result["selected_skills"]),
        summary=_profile_summary(profile, classification, skill_result["selected_skills"]),
        skill_categories=skill_result["categories"],
        selected_skills=skill_result["selected_skills"],
        job_skill_matches=skill_result["matches"],
        skill_verification=skill_result["verification"],
        education=_job_education(profile, job),
        experience=[],
        projects=ranked_projects,
        coursework=[],
        certifications=(
            _certifications_from_tailoring_plan(tailoring_plan, profile)
            if tailoring_plan is not None else []
        ),
        languages=_languages_for_job(job, profile, classification),
        research_interests=(
            [item for item in ("Robotics", "Embedded Systems", "Autonomous Systems", "Controls", "Computer Vision")
             if item in build_verified_skill_registry(profile)]
            if classification == "Robotics Research" else []
        ),
        opportunity_research_areas=[
            sanitize_resume_text(item) for item in (getattr(job, "research_areas", []) or [])
            if sanitize_resume_text(item)
        ],
        section_order=(
            ["education", "skills", "research_interests", "projects", "experience", "certifications", "languages"]
            if classification == "Robotics Research" else
            ["summary", "education", "projects", "skills", "coursework", "certifications", "languages"]
        ),
        match_score=0,
        keywords_used=output.keywords_used,
        keywords_missing=output.keywords_missing,
        unsupported_requirements=output.unsupported_requirements,
        changes=[{
            "section": "Tailoring",
            "description": "Selected canonical skills and projects for the vacancy.",
            "reason": "Structured model output validated against the master profile.",
        }],
        warnings=output.warnings,
    )


def generate_openai_content(
    job: Any,
    profile: Any,
    tailoring_plan: TailoringPlan | None = None,
) -> TailoredResumeContent:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    verified_profile = json.dumps(
        CandidateAIContextBuilder().for_resume(profile),
        ensure_ascii=False,
        default=str,
    )[:MAX_PROFILE_TEXT]
    profile_title = sanitize_resume_text(getattr(profile, "headline", ""))
    instructions = (
        "Return ModelTailoringOutput only. The job description drives relevance; the degree does not define the resume target. "
        "Use only verified candidate facts. Never infer Java from C++, ROS from robotics, AWS from cloud, or technologies from the job. "
        "Prefer projects demonstrating the job responsibilities; deprioritize unrelated technical projects. "
        "Reframe verified bullets toward those responsibilities without inventing facts or metrics. "
        "Do not generate personal information, education, "
        "certifications, or experience; the server injects canonical fields. Classify the job as "
        "Software Engineering, Backend / Data, Embedded / Firmware, FPGA / Digital Design, Hardware / Systems Integration, "
        "AI / API Integration, Robotics / Controls, Full Stack / Web, "
        "Developer Tools / Productivity, or Maps / Routing / Geospatial. "
        "Select and rank 8-16 skills using only the exact VERIFIED_PROFILE skill, project, course, "
        "or experience evidence. Group them into 2-4 compact ATS-readable categories. Never add "
        "a technology merely because the employer or job description mentions it; unsupported "
        "requirements belong in unsupported_requirements. Show at most five technologies per project. "
        "Prefer four substantial, complementary verified projects when available, rather than "
        "stopping at three. Never use a weak classroom practice merely to fill space. "
        f"Summary must contain 35-55 concrete words and use the profile title '{profile_title}'. "
        f"Headline must begin with '{profile_title}' and contain at most four pipe-separated elements. Use 2-3 unique "
        "project bullets of 14-28 words beginning with action verbs. Avoid vague language, invented "
        "metrics, unsupported claims, and the supplied forbidden phrases."
    )
    if tailoring_plan is not None:
        instructions += (
            " TAILORING_PLAN is an evidence-only server decision record. Its selected projects, "
            "skills, coursework, and experience are locked: do not add, remove, reorder, or "
            "substitute them. Generate only a concise headline and summary that accurately "
            "describe that selected evidence."
        )
    if getattr(job, "resume_target", "") == "robotics_research":
        instructions += (
            " The audience is a university professor or robotics researcher. Classify as Robotics "
            "Research and prioritize demonstrated robotics, embedded systems, control, sensing, "
            "hardware/software integration, experimentation, and technical depth. Academic projects "
            "can be highly relevant. Prefer designed and evaluated, integrated, developed and tested, "
            "investigated, implemented and validated, characterized, measured, or analyzed only when "
            "the verified source facts support that wording. Never fabricate publications, research "
            "positions, metrics, technologies, outcomes, or skills. Prefer technically specific "
            "language over corporate buzzwords."
        )
    user_input = "\n".join([
        f"VERIFIED_PROFILE:\n{verified_profile}",
        f"ARTIFICIAL_PHRASES:\n{json.dumps(sorted(ARTIFICIAL_PHRASES))}",
        f"FORBIDDEN_CLAIMS:\n{json.dumps(profile.forbidden_claims_json)}",
        f"JOB_TITLE: {job.title}",
        f"COMPANY: {job.company}",
        f"LAB: {getattr(job, 'lab', '')}",
        f"PROFESSOR_OR_SUPERVISOR: {getattr(job, 'supervisor', '')}",
        f"RESEARCH_AREAS: {json.dumps(getattr(job, 'research_areas', []) or [])}",
        f"PREFERRED_QUALIFICATIONS: {str(getattr(job, 'preferred_qualifications', '') or '')[:MAX_JOB_TEXT]}",
        f"JOB_DESCRIPTION:\n{str(job.description or '')[:MAX_JOB_TEXT]}",
        f"JOB_REQUIREMENTS:\n{str(job.requirements or '')[:MAX_JOB_TEXT]}",
        *([f"TAILORING_PLAN:\n{tailoring_plan.model_dump_json()}"] if tailoring_plan is not None else []),
    ])
    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    instructions += (
        f" The server-selected resume focus is {classify_job(job)}; use this focus for the "
        "headline, summary, skills, and project selection. For hardware roles prioritize evidenced "
        "FPGA, physical systems integration, embedded interfaces, testing, and debugging over web "
        "applications. Do not claim PCB design, board bring-up, CAD, RF, thermal analysis, or "
        "manufacturing experience unless the verified profile explicitly supports it."
    )
    last_error: Exception | None = None
    for _ in range(2):
        response = client.responses.parse(
            model=settings.openai_resume_model,
            input=[
                {"role": "developer", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            text_format=ModelTailoringOutput,
        )
        if response.output_parsed is None:
            last_error = RuntimeError("OpenAI returned no structured resume content.")
            continue
        try:
            return validate_generated_resume(
                _compose_model_output(
                    response.output_parsed,
                    job,
                    profile,
                    tailoring_plan=tailoring_plan,
                ),
                profile,
                job,
            )
        except ValueError as exc:
            last_error = exc
            user_input += f"\nVALIDATION_FAILURE_TO_CORRECT_ONCE: {exc}"
    raise RuntimeError(f"Model output failed validation: {last_error}")


def generate_structured_content(job: Any, profile: Any) -> TailoredResumeContent:
    if getattr(job, "portfolio_profile_id", None):
        return generate_local_content(job, profile)
    # KOSPIE uses deterministic, evidence-only academic ranking. It remains
    # available even when the global resume provider is configured as OpenAI.
    if getattr(job, "resume_target", "") == "kospie_germany":
        return generate_local_content(job, profile)
    if getattr(job, "application_type", "") == "TALENT_COMMUNITY":
        return generate_local_content(job, profile, project_limit=4)
    tailoring_plan = _scoped_tailoring_plan(job, profile, project_limit=4)
    if settings.resume_generation_provider.strip().lower() == "openai":
        return generate_openai_content(job, profile, tailoring_plan=tailoring_plan)
    return generate_local_content(job, profile, tailoring_plan=tailoring_plan)


def render_latex(content: TailoredResumeContent, profile: Any) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        comment_start_string="/*#",
        comment_end_string="#*/",
    )
    environment.filters["latex"] = latex_escape
    template = environment.get_template("resume.tex.j2")
    return template.render(content=content.model_dump(), profile=_profile_dict(profile))


def _validate_pdf_text(reader: PdfReader) -> str:
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    if any(char in extracted for char in CORRUPT_CHARACTERS):
        raise RuntimeError("Compiled PDF contains corrupt or invisible Unicode characters.")
    if not sanitize_resume_text(extracted):
        raise RuntimeError("Compiled PDF contains no extractable resume text.")
    return extracted


def _compile_latex_artifact(latex_source: str) -> tuple[bytes, int, float]:
    with tempfile.TemporaryDirectory(prefix="resume-") as temp_name:
        temp_dir = Path(temp_name)
        tex_path = temp_dir / "resume.tex"
        tex_path.write_text(latex_source, encoding="utf-8")
        try:
            result = subprocess.run(
                [settings.tectonic_path, "--outdir", str(temp_dir), str(tex_path)],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=settings.tectonic_timeout_seconds,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Tectonic is not installed. Configure TECTONIC_PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Resume compilation timed out.") from exc
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "Unknown compilation error")[-1600:]
            raise RuntimeError(f"LaTeX compilation failed: {error}")
        pdf_path = temp_dir / "resume.pdf"
        if not pdf_path.exists():
            raise RuntimeError("Tectonic did not produce a PDF.")
        pdf_bytes = pdf_path.read_bytes()
        reader = PdfReader(BytesIO(pdf_bytes))
        _validate_pdf_text(reader)
        page_count = len(reader.pages)
        usage = 100.0
        if page_count == 1:
            page = reader.pages[0]
            y_positions: list[float] = []

            def visitor(text: str, _cm: list[float], tm: list[float], _font: Any, _size: float) -> None:
                if text.strip():
                    y_positions.append(float(tm[5]))

            page.extract_text(visitor_text=visitor)
            printable_height = float(page.mediabox.height) - VERTICAL_MARGIN_POINTS
            if y_positions and printable_height:
                usage = min(
                    100.0,
                    max(0.0, (max(y_positions) - min(y_positions) + 12) / printable_height * 100),
                )
        return pdf_bytes, page_count, round(usage, 1)


def _has_sparse_second_page(pdf_bytes: bytes) -> bool:
    """Identify a tiny spill, not a naturally substantial two-page CV."""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        # Test doubles and unexpected PDFs should keep the existing behavior.
        return False
    if len(reader.pages) != 2:
        return False
    second_page_text = sanitize_resume_text(reader.pages[1].extract_text() or "")
    return len(second_page_text.split()) < 45


def compile_latex(latex_source: str, max_pages: int = 1) -> bytes:
    pdf_bytes, page_count, _ = _compile_latex_artifact(latex_source)
    if not 1 <= page_count <= max_pages:
        raise RuntimeError(f"The generated resume must contain 1 to {max_pages} pages.")
    return pdf_bytes


def fit_kospie_resume_to_two_pages(
    content: TailoredResumeContent,
    job: Any,
    verified_profile: Any,
    max_attempts: int = 16,
) -> tuple[TailoredResumeContent, str, bytes, float]:
    """Preserve a naturally strong one- or two-page academic CV; trim only overflow."""
    fitted = deepcopy(content)
    last_pdf = b""
    last_latex = ""
    last_usage = 0.0
    last_page_count = 0
    for _ in range(max_attempts):
        validate_generated_resume(fitted, verified_profile, job)
        last_latex = render_latex(fitted, verified_profile)
        last_pdf, last_page_count, last_usage = _compile_latex_artifact(last_latex)
        if last_page_count == 1:
            fitted.quality_checks.one_page = last_page_count == 1
            fitted.quality_checks.within_two_pages = True
            return fitted, last_latex, last_pdf, last_usage
        if last_page_count == 2 and not _has_sparse_second_page(last_pdf):
            fitted.quality_checks.one_page = False
            fitted.quality_checks.within_two_pages = True
            return fitted, last_latex, last_pdf, last_usage
        if last_page_count == 2:
            # A nearly empty second page is accidental overflow. First reduce
            # lower-priority metadata while preserving the strongest projects.
            if _trim_lowest_priority_skill(fitted):
                continue
            if len(fitted.coursework) > 6:
                fitted.coursework.pop()
                _synchronize_plan_after_layout_adjustment(fitted)
                continue
            if len(fitted.projects) > 4:
                fitted.projects.pop()
                _synchronize_plan_after_layout_adjustment(fitted)
                continue
            fitted.quality_checks.one_page = False
            fitted.quality_checks.within_two_pages = True
            return fitted, last_latex, last_pdf, last_usage
        if len(fitted.projects) > 4:
            fitted.projects.pop()
            _synchronize_plan_after_layout_adjustment(fitted)
            continue
        reduced = False
        for project in reversed(fitted.projects):
            if len(project.bullets) > 2:
                project.bullets = project.bullets[:2]
                reduced = True
                break
        if reduced:
            continue
        if len(fitted.coursework) > 6:
            fitted.coursework.pop()
            _synchronize_plan_after_layout_adjustment(fitted)
            continue
        if _trim_lowest_priority_skill(fitted):
            continue
        if fitted.experience:
            fitted.experience = fitted.experience[:-1]
            _synchronize_plan_after_layout_adjustment(fitted)
            continue
        break
    raise RuntimeError(
        f"KOSPIE resume fitting exceeded the two-page maximum ({last_page_count} pages)."
    )


def _trim_lowest_priority_skill(content: TailoredResumeContent) -> bool:
    if len(content.selected_skills) <= 8:
        return False
    scores = {item.skill: item.score for item in content.job_skill_matches}
    candidates = [
        (scores.get(skill, 0), group, skill)
        for group in content.skill_categories
        if len(group.items) > 2
        for skill in group.items
    ]
    if candidates:
        _, group, skill = min(candidates, key=lambda item: item[0])
        group.items.remove(skill)
    elif len(content.skill_categories) > 2:
        group = min(
            content.skill_categories,
            key=lambda item: sum(scores.get(skill, 0) for skill in item.items),
        )
        if len(content.selected_skills) - len(group.items) < 8:
            return False
        removed = set(group.items)
        content.skill_categories.remove(group)
        content.job_skill_matches = [
            item for item in content.job_skill_matches if item.skill not in removed
        ]
    else:
        return False
    content.selected_skills = [
        skill for group in content.skill_categories for skill in group.items
    ]
    selected = set(content.selected_skills)
    content.job_skill_matches = [
        item for item in content.job_skill_matches if item.skill in selected
    ]
    content.skill_verification.verified = content.selected_skills.copy()
    _synchronize_plan_after_layout_adjustment(content)
    return True


def fit_resume_to_one_page(
    content: TailoredResumeContent,
    job: Any,
    verified_profile: Any,
    max_attempts: int = 12,
) -> tuple[TailoredResumeContent, str, bytes, float]:
    fitted = deepcopy(content)
    last_pdf = b""
    last_latex = ""
    last_usage = 0.0
    last_page_count = 0
    expansion_attempted = False
    is_best_resume = content.target_role == "Best Resume"
    for _ in range(max_attempts):
        validate_generated_resume(fitted, verified_profile, job)
        last_latex = render_latex(fitted, verified_profile)
        last_pdf, last_page_count, last_usage = _compile_latex_artifact(last_latex)
        if (
            content.application_type == "PROFILE_PORTFOLIO"
            and not is_best_resume
            and last_page_count <= 2
            and last_usage <= 95
        ):
            fitted.quality_checks.one_page = last_page_count == 1
            fitted.quality_checks.within_two_pages = True
            fitted.quality_checks.ats_text_clean = True
            return fitted, last_latex, last_pdf, last_usage
        if last_page_count > 1 or last_usage > 95:
            if fitted.research_interests:
                fitted.research_interests = []
                continue
            if is_best_resume and fitted.certifications:
                # Best Resume prioritizes a one-page overview. Remove the
                # lowest-ranked certificate before sacrificing project evidence.
                fitted.certifications.pop()
                _synchronize_plan_after_layout_adjustment(fitted)
                continue
            if _trim_lowest_priority_skill(fitted):
                continue
            if fitted.coursework and fitted.classification != "Talent Community":
                fitted.coursework = []
                _synchronize_plan_after_layout_adjustment(fitted)
                continue
            if fitted.classification == "Talent Community":
                # Keep verified coursework in company resumes. Reclaim space from
                # secondary project detail before reducing courses.
                reduced = False
                for project in reversed(fitted.projects):
                    if len(project.bullets) > 1:
                        project.bullets = project.bullets[:-1]
                        reduced = True
                        break
                if reduced:
                    continue
                if len(fitted.coursework) > 1:
                    fitted.coursework = fitted.coursework[:1]
                    _synchronize_plan_after_layout_adjustment(fitted)
                    continue
            if len(fitted.projects) > 3 and fitted.application_type != "PROFILE_PORTFOLIO":
                # Keep four meaningful projects by shortening secondary detail
                # before discarding the lowest-ranked project.
                reduced = False
                for project in reversed(fitted.projects):
                    if len(project.bullets) > 2:
                        project.bullets = project.bullets[:2]
                        reduced = True
                if reduced:
                    continue
                fitted.projects.pop()
                _synchronize_plan_after_layout_adjustment(fitted)
                expansion_attempted = True
                continue
            reduced = False
            for project in reversed(fitted.projects):
                if len(project.bullets) > 2:
                    project.bullets = project.bullets[:2]
                    reduced = True
                    break
            if reduced:
                continue
            if fitted.classification != "Talent Community":
                fitted.coursework = []
                _synchronize_plan_after_layout_adjustment(fitted)
            words = _words(fitted.summary)
            fitted.summary = " ".join(words[:45]).rstrip(".,;") + "."
            continue
        if last_usage < 80 and not expansion_attempted:
            expansion_attempted = True
            expanded = generate_local_content(job, verified_profile, project_limit=4)
            changed = False
            expanded_by_name = {project.name: project for project in expanded.projects}
            for project in fitted.projects:
                source = expanded_by_name.get(project.name)
                if source and len(project.bullets) < len(source.bullets):
                    project.bullets = source.bullets[:3]
                    changed = True
                    break
            if changed:
                continue
            if (
                len(fitted.projects) < len(expanded.projects)
                and expanded.projects[-1].relevance_score >= 55
                and _fourth_project_adds_value(expanded.projects)
                and _maps_fourth_project_allowed(
                    job, fitted.classification, expanded.projects
                )
            ):
                fitted.projects = expanded.projects
                _synchronize_plan_after_layout_adjustment(fitted)
                changed = True
            if not fitted.coursework and verified_profile.coursework_json and fitted.application_type != "PROFILE_PORTFOLIO":
                courses = _select_courses(
                    job, verified_profile, fitted.classification, limit=2
                )
                if courses:
                    fitted.coursework = [
                        ResumeCourseItem.model_validate(course) for course in courses
                    ]
                    _synchronize_plan_after_layout_adjustment(fitted)
                    changed = True
            if changed:
                continue
        fitted.quality_checks.one_page = True
        fitted.quality_checks.ats_text_clean = True
        return fitted, last_latex, last_pdf, last_usage
    max_pages = 2 if content.application_type == "PROFILE_PORTFOLIO" and not is_best_resume else 1
    if not last_pdf or last_page_count > max_pages:
        raise RuntimeError(f"Resume fitting could not produce a PDF within {max_pages} page(s).")
    fitted.quality_checks.one_page = last_page_count == 1
    fitted.quality_checks.within_two_pages = last_page_count <= 2
    return fitted, last_latex, last_pdf, last_usage


def content_hash(content: TailoredResumeContent, latex_source: str) -> str:
    raw = json.dumps(content.model_dump(), sort_keys=True, ensure_ascii=True) + latex_source
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resume_generation_input_hash(job: Any, profile: Any, resume_target: str) -> str:
    """Identity for deciding whether a saved version is stale, never its title."""
    profile_fields = (
        "education_json", "skills_json", "experience_json", "projects_json",
        "coursework_json", "certifications_json", "languages_json",
        "language_credentials_json", "github_evidence_json", "forbidden_claims_json",
        "headline", "summary", "linkedin_url", "github_url",
    )
    payload = {
        "job_id": getattr(job, "id", None),
        "job_content_hash": job_content_hash(job),
        "resume_target": resume_target,
        "profile": {field: getattr(profile, field, None) for field in profile_fields},
    }
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _log_tailoring_trace(generation_id: int, content: TailoredResumeContent) -> None:
    """Emit a developer-only, evidence-safe explanation of a planned resume."""
    plan = content.tailoring_plan if isinstance(content.tailoring_plan, dict) else {}
    decisions = plan.get("resume_decisions", {}) if plan else {}
    if decisions.get("status") != "PLANNED":
        return
    requirement_evidence = plan.get("requirement_evidence", [])
    matched = [
        item.get("requirement", {}).get("normalized_requirement", "")
        for item in requirement_evidence
        if item.get("match_state") != SkillMatchState.NOT_FOUND.value
    ]
    logger.info(
        "Tailoring plan for resume %s: projects=%s scores=%s skills=%s matched=%s missing=%s",
        generation_id,
        decisions.get("selected_projects", []),
        decisions.get("selected_project_scores", {}),
        decisions.get("selected_skills", []),
        [item for item in matched if item],
        decisions.get("missing_requirements", []),
    )


def generate_resume(job: Any, profile: Any, generation_id: int) -> tuple[TailoredResumeContent, str, bytes]:
    started = time.monotonic()
    try:
        validate_master_profile(profile)
        content = generate_structured_content(job, profile)
        _log_tailoring_trace(generation_id, content)
        if content.application_type == "KOSPIE_PROGRAM":
            content, latex_source, pdf_bytes, utilization = fit_kospie_resume_to_two_pages(
                content, job, profile
            )
        else:
            content, latex_source, pdf_bytes, utilization = fit_resume_to_one_page(
                content, job, profile
            )
        logger.info(
            "Resume generation %s compiled in %.2fs using %s (vertical utilization %.1f%%)",
            generation_id,
            time.monotonic() - started,
            settings.openai_resume_model
            if settings.resume_generation_provider.strip().lower() == "openai"
            else "local",
            utilization,
        )
        return content, latex_source, pdf_bytes
    except Exception:
        logger.exception(
            "Resume generation %s failed after %.2fs",
            generation_id,
            time.monotonic() - started,
        )
        raise
