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
from app.services.resume_skills import (
    build_verified_skill_registry,
    filter_and_verify_skill_categories,
    select_job_skills,
)


logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "resume"
MAX_JOB_TEXT = 40_000
MAX_PROFILE_TEXT = 40_000
VERTICAL_MARGIN_POINTS = 0.58 * 72 * 2

CANONICAL_NAME = "Alex Rivera"
CANONICAL_DEGREE = "B.S. in Computer Engineering"
CANONICAL_STUDENT_TITLE = "Computer Engineering Student"
CANONICAL_INSTITUTION = "Example Institute of Technology"
CANONICAL_GRADUATION = "Expected Graduation: May 2029"
CANONICAL_GPA = "3.70/4.00"
CANONICAL_LOCATION = "Mexico City, Mexico"
CANONICAL_EMAIL = settings.resume_email.strip() or "resume@example.com"
CANONICAL_PHONE = "+52 55 0000 0000"
CANONICAL_LINKEDIN = "https://www.linkedin.com/in/example-candidate/"
CANONICAL_GITHUB = "https://github.com/example-candidate"

INVALID_DEGREE_NAMES = {
    "Computer Science",
    "Software Engineering",
    "Electrical Engineering",
    "Mechanical Engineering",
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
    "Software Engineering",
    "Backend / Data",
    "Embedded / Firmware",
    "FPGA / Digital Design",
    "AI / API Integration",
    "Robotics / Controls",
    "Maps / Routing / Geospatial",
    "Full Stack / Web",
    "Developer Tools / Productivity",
}
VALID_SKILL_CATEGORIES = {
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
}
ACTION_VERBS = {
    "analyzed", "automated", "built", "configured", "created", "debugged",
    "designed", "developed", "implemented", "integrated", "modeled",
    "optimized", "programmed", "simulated", "tested", "validated",
}
PROJECT_PRIORITIES = {
    "Embedded / Firmware": [
        "Embedded Telemetry Gateway",
        "Autonomous Lab Rover",
        "FPGA Signal Processor",
        "Internship Radar - AI Resume Tailoring Platform",
        "Environmental Sensor Dashboard",
        "Market Simulation Engine",
        "Route Optimization Engine",
    ],
    "Software Engineering": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Market Simulation Engine",
        "Route Optimization Engine",
        "Environmental Sensor Dashboard",
        "Autonomous Lab Rover",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
    ],
    "Backend / Data": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Environmental Sensor Dashboard",
        "Market Simulation Engine",
        "Route Optimization Engine",
        "Autonomous Lab Rover",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
    ],
    "FPGA / Digital Design": [
        "FPGA Signal Processor",
        "Embedded Telemetry Gateway",
        "Autonomous Lab Rover",
        "Internship Radar - AI Resume Tailoring Platform",
        "Market Simulation Engine",
        "Route Optimization Engine",
        "Environmental Sensor Dashboard",
    ],
    "AI / API Integration": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Environmental Sensor Dashboard",
        "Market Simulation Engine",
        "Autonomous Lab Rover",
        "Route Optimization Engine",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
    ],
    "Robotics / Controls": [
        "Autonomous Lab Rover",
        "FPGA Signal Processor",
        "Embedded Telemetry Gateway",
        "Environmental Sensor Dashboard",
        "Route Optimization Engine",
        "Market Simulation Engine",
    ],
    "Maps / Routing / Geospatial": [
        "Route Optimization Engine",
        "Environmental Sensor Dashboard",
        "Internship Radar - AI Resume Tailoring Platform",
        "Market Simulation Engine",
        "Autonomous Lab Rover",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
    ],
    "Full Stack / Web": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Environmental Sensor Dashboard",
        "Autonomous Lab Rover",
        "Route Optimization Engine",
        "Market Simulation Engine",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
    ],
    "Developer Tools / Productivity": [
        "Internship Radar - AI Resume Tailoring Platform",
        "Market Simulation Engine",
        "Route Optimization Engine",
        "Environmental Sensor Dashboard",
        "Autonomous Lab Rover",
        "Embedded Telemetry Gateway",
        "FPGA Signal Processor",
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


def _profile_dict(profile: Any) -> dict[str, Any]:
    return {
        key: getattr(profile, key)
        for key in (
            "full_name", "email", "phone", "location", "linkedin_url", "github_url",
            "headline", "summary", "education_json", "skills_json", "experience_json",
            "projects_json", "coursework_json", "certifications_json", "languages_json",
            "forbidden_claims_json",
        )
    }


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
    pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword.lower())}(?![A-Za-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _profile_project_map(profile: Any) -> dict[str, dict[str, Any]]:
    return {
        sanitize_resume_text(item.get("name", "")): item
        for item in profile.projects_json
        if isinstance(item, dict) and sanitize_resume_text(item.get("name", ""))
    }


def validate_master_profile(profile: Any) -> None:
    expected = {
        "full_name": CANONICAL_NAME,
        "email": CANONICAL_EMAIL,
        "phone": CANONICAL_PHONE,
        "location": CANONICAL_LOCATION,
        "linkedin_url": CANONICAL_LINKEDIN,
        "github_url": CANONICAL_GITHUB,
    }
    for field, canonical in expected.items():
        if sanitize_resume_text(getattr(profile, field, "")) != canonical:
            raise ValueError(f"Resume Profile {field} must be canonical: {canonical}")
    if not profile.education_json or not isinstance(profile.education_json[0], dict):
        raise ValueError("Resume Profile must contain canonical education.")
    education = profile.education_json[0]
    education_expected = {
        "degree": CANONICAL_DEGREE,
        "institution": CANONICAL_INSTITUTION,
        "location": CANONICAL_LOCATION,
        "graduation": CANONICAL_GRADUATION,
        "gpa": CANONICAL_GPA,
    }
    for field, canonical in education_expected.items():
        if sanitize_resume_text(education.get(field, "")) != canonical:
            raise ValueError(f"Canonical education field {field} must be {canonical}.")
    for invalid_name in INVALID_DEGREE_NAMES:
        if (
            sanitize_resume_text(profile.headline) == invalid_name
            or sanitize_resume_text(education.get("degree", "")) == invalid_name
        ):
            raise ValueError(f"Inconsistent degree name in master profile: {invalid_name}")
    for field in ("linkedin_url", "github_url"):
        if not _valid_url(getattr(profile, field, "")):
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
    result = select_job_skills(
        job,
        verified_profile,
        content.classification,
        selected_project_names={project.name for project in content.projects},
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


def validate_generated_resume(
    content: TailoredResumeContent,
    verified_profile: Any,
    job: Any,
) -> TailoredResumeContent:
    validate_master_profile(verified_profile)
    payload = json.dumps(content.model_dump(), ensure_ascii=False)
    document_payload = json.dumps(
        content.model_dump(include={
            "headline", "summary", "skill_categories", "education", "experience",
            "projects", "coursework", "certifications", "languages",
        }),
        ensure_ascii=False,
    )
    lowered = document_payload.lower()
    if content.education.degree != CANONICAL_DEGREE:
        raise ValueError("Generated resume contains an inconsistent degree name.")
    if CANONICAL_DEGREE not in payload or CANONICAL_STUDENT_TITLE not in content.headline:
        raise ValueError("Canonical degree and student title must be present.")
    academic_text = f"{content.headline} {content.summary} {content.education.degree}".lower()
    for invalid_name in INVALID_DEGREE_NAMES:
        if (
            content.education.degree == invalid_name
            or f"{invalid_name.lower()} student" in academic_text
        ):
            raise ValueError(f"Generated resume contains inconsistent degree name: {invalid_name}")
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", payload))
    if emails and emails != {CANONICAL_EMAIL}:
        raise ValueError("Generated resume contains a noncanonical email.")

    artificial = _contains_artificial_language(document_payload)
    if artificial:
        raise ValueError(f"Generated resume contains artificial language: {', '.join(artificial)}")
    if re.search(r"\b(\w+)\s+\1\b", lowered):
        raise ValueError("Generated resume contains repeated consecutive words.")

    if content.classification not in VALID_CLASSIFICATIONS:
        raise ValueError("Resume classification is not supported.")
    if content.classification != classify_job(job):
        raise ValueError("Resume classification does not match the job.")
    _ensure_verified_skill_section(content, verified_profile, job)
    summary_words = len(_words(content.summary))
    if not 35 <= summary_words <= 55:
        raise ValueError("Summary must contain between 35 and 55 words.")
    if content.headline.count("|") > 3:
        raise ValueError("Headline may contain at most four elements.")

    verified_registry = build_verified_skill_registry(verified_profile)
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
    if not 2 <= len(content.projects) <= 4:
        raise ValueError("Resume must contain two to four projects.")
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

    if len(content.coursework) > 2:
        raise ValueError("Resume may contain at most two courses.")
    verified_courses = {
        _item_value(item, "name"): item
        for item in verified_profile.coursework_json
        if isinstance(item, dict) and _item_value(item, "name")
    }
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
    title = sanitize_resume_text(getattr(job, "title", "")).lower()
    text = " ".join(
        sanitize_resume_text(value).lower()
        for value in (
            getattr(job, "title", ""), getattr(job, "area", ""),
            getattr(job, "description", ""), getattr(job, "requirements", ""),
            getattr(job, "preferred_qualifications", ""),
        )
    )
    scores = {
        "Embedded / Firmware": sum(text.count(term) for term in (
            "embedded", "firmware", "freertos", "rtos", "microcontroller", "uart",
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
    if "embedded" in title or "firmware" in title:
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


def _headline(classification: str) -> str:
    suffixes = {
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


def _summary(classification: str) -> str:
    summaries = {
        "Embedded / Firmware": (
            "Computer Engineering student with hands-on experience developing "
            "C/C++ firmware, FreeRTOS applications, hardware interfaces, and robotic systems. Built "
            "and debugged software across FRDM-KL25Z, ESP32, Raspberry Pi, and FPGA platforms using "
            "UART, SPI, I2C, PWM, interrupts, Linux, and board-level testing."
        ),
        "Software Engineering": (
            "Computer Engineering student who built C++ matching and graph "
            "applications, Python services, and hardware-connected software. Applies object-oriented "
            "programming, data structures, algorithms, REST APIs, Linux, Git, and testing to implement "
            "modular, maintainable software across multidisciplinary engineering projects."
        ),
        "Backend / Data": (
            "Computer Engineering student with project experience building Python "
            "services, REST APIs, MySQL data pipelines, and live dashboards. Developed software that "
            "connects sensors, databases, and web clients using Flask, SQL, Linux, Git, structured "
            "testing, and object-oriented design."
        ),
        "FPGA / Digital Design": (
            "Computer Engineering student with project experience designing FPGA "
            "controllers, Verilog modules, testbenches, and hardware interfaces. Built digital systems "
            "for robotic control using Intel MAX 10, SystemVerilog, GPIO, PWM, UART, simulation, and "
            "signal-level testing across integrated hardware components."
        ),
        "AI / API Integration": (
            "Computer Engineering student who built Python APIs, database-backed "
            "services, dashboards, and connected embedded applications. Applies Flask, REST APIs, "
            "MySQL, algorithms, Linux, Git, and structured testing to integrate software components "
            "and technical data across multidisciplinary engineering systems."
        ),
        "Robotics / Controls": (
            "Computer Engineering student with project experience building robotic "
            "controllers, embedded communication, sensor interfaces, and motion software. Developed "
            "systems using C/C++, Python, ESP32, FRDM-KL25Z, FPGA, UART, PWM, interrupts, Linux, and "
            "hardware debugging across integrated control platforms."
        ),
        "Maps / Routing / Geospatial": (
            "Computer Engineering student with experience building C++ graph "
            "applications, Python services, and hardware-connected systems. Applies object-oriented "
            "programming, data structures, graph algorithms, path validation, REST APIs, Linux, Git, "
            "and testing to develop modular software for routing, data processing, and multidisciplinary "
            "engineering problems."
        ),
        "Full Stack / Web": (
            "Computer Engineering student with experience building full-stack "
            "applications using Next.js, TypeScript, FastAPI, Python, and PostgreSQL. Applies structured "
            "validation, authenticated routes, REST APIs, relational data modeling, Git, Docker, and "
            "testing to develop maintainable web platforms and reusable software interfaces."
        ),
        "Developer Tools / Productivity": (
            "Computer Engineering student with experience building developer-facing "
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
    priority = PROJECT_PRIORITIES[classification]
    if classification == "Maps / Routing / Geospatial":
        base = 70 - priority.index(name) * 13 if name in priority else 12
    else:
        base = 58 - priority.index(name) * 7 if name in priority else 12
    project_text = json.dumps(item, ensure_ascii=False).lower()
    job_text = sanitize_resume_text(job_requirements).lower()
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
    return min(100.0, max(0.0, score))


def _project_score(item: dict[str, Any], job_text: str, classification: str) -> float:
    return score_project_for_job(item, classification, job_text)


def _project_bullets(item: dict[str, Any]) -> list[str]:
    bullets = _clean_list(item.get("bullets"), limit=3)
    unique: list[str] = []
    seen: set[str] = set()
    for bullet in bullets:
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
    verified_skills = {
        sanitize_resume_text(item).lower()
        for item in profile.skills_json
        if sanitize_resume_text(item)
    }
    for item in profile.projects_json:
        if not isinstance(item, dict):
            continue
        if item.get("is_resume_eligible", True) is not True:
            continue
        technologies = _visible_project_technologies(
            item, job_text, classification, verified_skills
        )
        score = _project_score(item, job_text, classification)
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
            "bullets": (
                _internship_radar_bullets(classification)
                if name == "Internship Radar - AI Resume Tailoring Platform"
                else _project_bullets(item)
            ),
        }))
    scored.sort(key=lambda pair: pair[0], reverse=True)
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
    if fourth.name != "Autonomous Lab Rover":
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
    if classification in {"Embedded / Firmware", "FPGA / Digital Design"}:
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


def _certifications(profile: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": _item_value(item, "name", "title"),
            "issuer": _item_value(item, "issuer", "organization"),
            "date": _item_value(item, "date", "issued"),
            "url": _item_value(item, "url", "credential_url"),
        }
        for item in profile.certifications_json
        if isinstance(item, dict) and _item_value(item, "name", "title")
    ]


def _languages_for_job(job: Any, profile: Any) -> list[str]:
    """Keep proficient languages and add basic languages only when a posting names them."""
    verified = [
        sanitize_resume_text(item)
        for item in profile.languages_json
        if sanitize_resume_text(item)
    ]
    job_text = " ".join(
        sanitize_resume_text(getattr(job, field, ""))
        for field in ("title", "location", "description", "requirements", "preferred_qualifications")
    ).lower()
    selected: list[str] = []
    for language in verified:
        normalized = language.replace("—", "-")
        name, _, proficiency = normalized.partition("-")
        name = name.strip().lower()
        if "basic" not in proficiency.lower():
            selected.append(language)
        elif name and name in job_text:
            selected.append(language)
    return selected


def generate_local_content(
    job: Any,
    profile: Any,
    project_limit: int = 3,
) -> TailoredResumeContent:
    classification = classify_job(job)
    analysis = getattr(job, "analysis", None)
    missing = _clean_list(getattr(analysis, "missing_required_skills", []), limit=8)
    matched = _clean_list(getattr(analysis, "matched_skills", []), limit=12)
    overall_score = getattr(analysis, "overall_score", None)
    selected_projects = _select_projects(job, profile, classification, project_limit)
    skill_result = select_job_skills(
        job,
        profile,
        classification,
        selected_project_names={project["name"] for project in selected_projects},
    )
    content = TailoredResumeContent(
        target_role=sanitize_resume_text(job.title),
        classification=classification,
        headline=_headline(classification),
        summary=_summary(classification),
        skill_categories=skill_result["categories"],
        selected_skills=skill_result["selected_skills"],
        job_skill_matches=skill_result["matches"],
        skill_verification=skill_result["verification"],
        education=_canonical_education(profile),
        experience=[],
        projects=selected_projects,
        coursework=[],
        certifications=_certifications(profile),
        languages=_languages_for_job(job, profile),
        section_order=[
            "summary", "education", "projects", "skills", "coursework",
            "certifications", "languages",
        ],
        match_score=float(overall_score) if overall_score is not None else 0,
        keywords_used=matched,
        keywords_missing=missing,
        unsupported_requirements=missing,
        changes=[{
            "section": "Tailoring",
            "description": f"Classified the vacancy as {classification} and ranked canonical projects.",
            "reason": "Reusable job classification, skill matrix, and project priority rules.",
        }],
        warnings=(
            ["Generated locally from canonical profile data; review before applying."]
            + ([f"Unsupported requirements omitted: {', '.join(missing)}"] if missing else [])
        ),
    )
    return validate_generated_resume(content, profile, job)


def _compose_model_output(
    output: ModelTailoringOutput,
    job: Any,
    profile: Any,
) -> TailoredResumeContent:
    requested_skills = [
        sanitize_resume_text(item)
        for group in output.skill_categories
        for item in group.items
    ]
    skill_result = select_job_skills(
        job,
        profile,
        sanitize_resume_text(output.classification),
        selected_project_names={project.name for project in output.projects},
        model_requested=requested_skills,
    )
    return TailoredResumeContent(
        target_role=sanitize_resume_text(job.title),
        classification=sanitize_resume_text(output.classification),
        headline=sanitize_resume_text(output.headline),
        summary=sanitize_resume_text(output.summary),
        skill_categories=skill_result["categories"],
        selected_skills=skill_result["selected_skills"],
        job_skill_matches=skill_result["matches"],
        skill_verification=skill_result["verification"],
        education=_canonical_education(profile),
        experience=[],
        projects=output.projects,
        coursework=[],
        certifications=_certifications(profile),
        languages=_languages_for_job(job, profile),
        section_order=[
            "summary", "education", "projects", "skills", "coursework",
            "certifications", "languages",
        ],
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


def generate_openai_content(job: Any, profile: Any) -> TailoredResumeContent:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    verified_profile = json.dumps(_profile_dict(profile), ensure_ascii=False, default=str)[:MAX_PROFILE_TEXT]
    instructions = (
        "Return ModelTailoringOutput only. Do not generate personal information, education, "
        "certifications, or experience; the server injects canonical fields. Classify the job as "
        "Software Engineering, Backend / Data, Embedded / Firmware, FPGA / Digital Design, "
        "AI / API Integration, Robotics / Controls, Full Stack / Web, "
        "Developer Tools / Productivity, or Maps / Routing / Geospatial. "
        "Select and rank 8-16 skills using only the exact VERIFIED_PROFILE skill, project, course, "
        "or experience evidence. Group them into 2-4 compact ATS-readable categories. Never add "
        "a technology merely because the employer or job description mentions it; unsupported "
        "requirements belong in unsupported_requirements. Show at most five technologies per project. "
        "Summary must contain 35-55 concrete words and the official phrase 'Computer Engineering "
        "student'. Headline must begin with 'Computer Engineering Student' and contain at most "
        "four pipe-separated elements. Use 2-3 unique "
        "project bullets of 14-28 words beginning with action verbs. Avoid vague language, invented "
        "metrics, unsupported claims, and the supplied forbidden phrases."
    )
    user_input = "\n".join([
        f"VERIFIED_PROFILE:\n{verified_profile}",
        f"ARTIFICIAL_PHRASES:\n{json.dumps(sorted(ARTIFICIAL_PHRASES))}",
        f"FORBIDDEN_CLAIMS:\n{json.dumps(profile.forbidden_claims_json)}",
        f"JOB_TITLE: {job.title}",
        f"COMPANY: {job.company}",
        f"JOB_DESCRIPTION:\n{str(job.description or '')[:MAX_JOB_TEXT]}",
        f"JOB_REQUIREMENTS:\n{str(job.requirements or '')[:MAX_JOB_TEXT]}",
    ])
    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
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
                _compose_model_output(response.output_parsed, job, profile),
                profile,
                job,
            )
        except ValueError as exc:
            last_error = exc
            user_input += f"\nVALIDATION_FAILURE_TO_CORRECT_ONCE: {exc}"
    raise RuntimeError(f"Model output failed validation: {last_error}")


def generate_structured_content(job: Any, profile: Any) -> TailoredResumeContent:
    if settings.resume_generation_provider.strip().lower() == "openai":
        return generate_openai_content(job, profile)
    return generate_local_content(job, profile)


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
    if CANONICAL_DEGREE not in sanitize_resume_text(extracted):
        raise RuntimeError("Compiled PDF does not preserve the canonical degree name.")
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


def compile_latex(latex_source: str) -> bytes:
    pdf_bytes, page_count, _ = _compile_latex_artifact(latex_source)
    if page_count != 1:
        raise RuntimeError("The generated resume is not exactly one page.")
    return pdf_bytes


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
    for _ in range(max_attempts):
        validate_generated_resume(fitted, verified_profile, job)
        last_latex = render_latex(fitted, verified_profile)
        last_pdf, last_page_count, last_usage = _compile_latex_artifact(last_latex)
        if last_page_count > 1 or last_usage > 95:
            if _trim_lowest_priority_skill(fitted):
                continue
            if fitted.coursework:
                fitted.coursework = []
                continue
            if len(fitted.projects) > 3:
                fitted.projects.pop()
                continue
            reduced = False
            for project in reversed(fitted.projects):
                if len(project.bullets) > 2:
                    project.bullets = project.bullets[:2]
                    reduced = True
                    break
            if reduced:
                continue
            fitted.coursework = []
            words = _words(fitted.summary)
            fitted.summary = " ".join(words[:45]).rstrip(".,;") + "."
            continue
        if last_usage < 80:
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
                changed = True
            if not fitted.coursework and verified_profile.coursework_json:
                courses = _select_courses(
                    job, verified_profile, fitted.classification, limit=2
                )
                if courses:
                    fitted.coursework = [
                        ResumeCourseItem.model_validate(course) for course in courses
                    ]
                    changed = True
            if changed:
                continue
        fitted.quality_checks.one_page = True
        fitted.quality_checks.ats_text_clean = True
        return fitted, last_latex, last_pdf, last_usage
    if not last_pdf or last_page_count != 1:
        raise RuntimeError("Resume fitting could not produce exactly one page.")
    fitted.quality_checks.one_page = True
    return fitted, last_latex, last_pdf, last_usage


def content_hash(content: TailoredResumeContent, latex_source: str) -> str:
    raw = json.dumps(content.model_dump(), sort_keys=True, ensure_ascii=True) + latex_source
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_resume(job: Any, profile: Any, generation_id: int) -> tuple[TailoredResumeContent, str, bytes]:
    started = time.monotonic()
    try:
        validate_master_profile(profile)
        content = generate_structured_content(job, profile)
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
