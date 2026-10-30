from __future__ import annotations

from itertools import combinations
import re
from types import SimpleNamespace
from typing import Any

from app.schemas.api import TailoredResumeContent
from app.services.kospie import kospie_project_assessment, project_engineering_domains
from app.services.language_evidence import resume_language_lines
from app.services.resume_generation import (
    _canonical_education, _item_value, _project_bullets, _valid_url,
    sanitize_resume_text, validate_generated_resume,
)
from app.services.resume_skills import select_job_skills


STUDIO_PROFILES = {
    "embedded": {
        "label": "Embedded / Firmware", "target": "embedded_firmware",
        "classification": "Embedded / Firmware",
        "description": "Firmware, real-time concurrency, microcontrollers and hardware interfaces.",
        "context": "Embedded firmware FreeRTOS microcontrollers UART PWM interrupts hardware integration",
    },
    "software": {
        "label": "Software Engineering", "target": "software_engineering",
        "classification": "Software Engineering",
        "description": "Algorithms, data structures, application architecture and backend systems.",
        "context": "Software C++ Python algorithms data structures backend REST APIs database full-stack",
    },
    "fpga": {
        "label": "FPGA / Digital Design", "target": "electrical_validation",
        "classification": "FPGA / Digital Design",
        "description": "RTL, digital design, hardware timing and simulation.",
        "context": "FPGA Verilog SystemVerilog RTL Intel MAX 10 digital logic UART PWM simulation",
    },
    "robotics": {
        "label": "Robotics / Controls", "target": "robotics_research",
        "classification": "Robotics Research",
        "description": "Physical prototypes, sensing, actuation and hardware/software integration.",
        "context": "Robotics controls sensors actuators embedded systems hardware/software integration",
    },
    "general": {
        "label": "General — Strongest Projects", "target": "software_engineering",
        "classification": "Software Engineering",
        "description": "Your strongest complementary projects, without favoring one technical role.",
        "context": "Engineering software embedded robotics FPGA system integration",
    },
}
WEIGHTS = {
    "relevance": .25, "technical_depth": .20, "project_scope": .15,
    "system_integration": .15, "ownership": .10, "outcome_completeness": .10,
    "differentiation": .05,
}


def studio_config(profile_id: str) -> dict[str, str]:
    if profile_id not in STUDIO_PROFILES:
        raise ValueError("Unknown resume profile. Choose embedded, software, fpga, robotics or general.")
    return STUDIO_PROFILES[profile_id]


def _relevance(profile_id: str, assessment: dict[str, Any]) -> float:
    capabilities = set(assessment["capabilities"])
    domains = set(assessment["domains"])
    if profile_id == "general":
        return 70.0  # Neutral relevance: quality and portfolio contribution decide.
    if profile_id == "software":
        if capabilities & {"full-stack engineering platform", "algorithmic matching engine", "graph algorithms"}:
            return 98.0
        return 88.0 if "sensor-to-cloud monitoring" in capabilities else 55.0
    if profile_id == "fpga":
        return 100.0 if "FPGA and RTL design" in capabilities else (62.0 if "Embedded Systems" in domains else 35.0)
    if profile_id == "robotics":
        return 100.0 if "Robotics" in domains else (80.0 if "Control Systems" in domains else 45.0)
    if "real-time concurrency" in capabilities:
        return 100.0
    return 92.0 if "Embedded Systems" in domains else 45.0


def rank_studio_projects(profile: Any, profile_id: str, limit: int = 4) -> list[dict[str, Any]]:
    studio_config(profile_id)
    assessed = []
    for index, item in enumerate(profile.projects_json or []):
        if not isinstance(item, dict) or item.get("is_resume_eligible", True) is not True:
            continue
        name = _item_value(item, "name", "title")
        bullets = _project_bullets(item)
        if not name or len(bullets) < 2:
            continue
        # Implementation evidence, not the technology list, proves depth and integration.
        evidence = {"name": "", "bullets": bullets}
        for key in ("project_type", "scope_type", "status"):
            if key in item:
                evidence[key] = item[key]
        assessment = kospie_project_assessment(evidence, [])
        assessment["name"] = name
        assessment["domains"] = project_engineering_domains(item)
        components = assessment["components"]
        components["relevance"] = _relevance(profile_id, assessment)
        if "hardware timing" in assessment["depth_evidence"] and not set(assessment["domains"]) & {"Embedded Systems", "FPGA / Digital Systems"}:
            assessment["depth_evidence"].remove("hardware timing")
            components["technical_depth"] = max(18.0, components["technical_depth"] - 12.0)
        implementation = " ".join(bullets).casefold()
        if re.search(r"\b(integrat\w*|connect\w*|coordinat\w*|expos\w*|through)\b", implementation):
            count = len(assessment["subsystems"])
            integration = (15, 30, 50, 68, 82, 92)[min(count, 5)]
            if assessment["project_type"] != "complete_project":
                integration = min(integration, 65 if assessment["project_type"] == "focused_technical_exercise" else 45)
            components["system_integration"] = float(integration)
        assessment["score"] = round(max(0.0, sum(components[k] * w for k, w in WEIGHTS.items()) - components["generic_penalty"] - components["classroom_exercise_penalty"]), 1)
        components["resume_value"] = round(sum(components[key] for key in (
            "technical_depth", "project_scope", "system_integration", "ownership", "outcome_completeness",
        )) / 5, 1)
        if assessment["project_type"] == "complete_project" and components["system_integration"] < 68:
            assessment["scope_assessment"] = "Scope: complete project; multi-component integration is not established by the stored evidence."
        assessment["source_index"] = index
        assessed.append(assessment)
    assessed.sort(key=lambda item: (-item["score"], item["source_index"]))
    pool = [item for item in assessed if item["score"] >= 40][:20]
    count = min(limit, len(pool))

    def value(group: tuple[dict[str, Any], ...]) -> float:
        capabilities = {cap for item in group for cap in item["capabilities"]}
        score = sum(item["score"] for item in group) + 5 * len(capabilities)
        for left, right in combinations(group, 2):
            score -= 9 * len(set(left["capabilities"]) & set(right["capabilities"]))
            if left["project_type"] != "complete_project" and right["project_type"] != "complete_project" and set(left["domains"]) & set(right["domains"]):
                score -= 5
        return score

    selected = max(combinations(pool, count), key=value, default=())
    selected_ids = {item["source_index"] for item in selected}
    for rank, item in enumerate(assessed, 1):
        item["rank"] = rank
        item["selected"] = item["source_index"] in selected_ids
        depth = ", ".join(item["depth_evidence"]) or "limited implementation detail"
        integration = ", ".join(item["subsystems"]) or "no documented subsystem chain"
        unique = ", ".join(item["capabilities"]) or "supporting technical practice"
        item["reasons"] = [
            ("Selected: its evidence-weighted quality and complementary capabilities strengthen this portfolio." if item["selected"] else "Not selected: alternatives provide a stronger total portfolio for this profile."),
            f"Technical depth: {components['technical_depth']}/100; implementation evidence: {depth}.",
            item["scope_assessment"],
            f"Integration: {components['system_integration']}/100; documented components: {integration}. Listing components alone does not establish a complete integrated system.",
            f"Portfolio contribution: {unique}.",
        ]
    return assessed


def build_studio_job(profile_id: str) -> Any:
    config = studio_config(profile_id)
    return SimpleNamespace(
        title=f"{config['label']} CV", company="Personal portfolio", area=config["label"],
        description=config["context"], requirements="", preferred_qualifications="",
        analysis=None, application_type="PROFILE_PORTFOLIO", resume_target=config["target"],
        portfolio_profile_id=profile_id,
    )


def generate_studio_content(
    job: Any,
    profile: Any,
    *,
    minimum_projects: int = 2,
    project_limit: int = 4,
) -> TailoredResumeContent:
    profile_id = job.portfolio_profile_id
    config = studio_config(profile_id)
    ranking = rank_studio_projects(profile, profile_id, limit=project_limit)
    chosen = [item for item in ranking if item["selected"]]
    if len(chosen) < minimum_projects:
        raise ValueError("Add at least two substantial, resume-eligible projects with two implementation bullets each.")
    projects = []
    for assessment in chosen:
        source = profile.projects_json[assessment["source_index"]]
        repository = _item_value(source, "repository_url", "github_url", "url") or None
        live = _item_value(source, "live_url") or None
        projects.append({
            "name": assessment["name"], "bullets": _project_bullets(source),
            "technologies": [sanitize_resume_text(x) for x in source.get("technologies", [])][:5],
            "github_url": repository if source.get("is_public", True) and _valid_url(repository) else None,
            "live_url": live if _valid_url(live) else None,
            "status": _item_value(source, "status"), "dates": _item_value(source, "dates", "date"),
            "relevance_score": assessment["score"],
        })
    skills = select_job_skills(job, profile, config["classification"], selected_project_names={x["name"] for x in projects})
    title = sanitize_resume_text(profile.headline)
    skill_text = ", ".join(skills["selected_skills"][:3])
    capabilities = list(dict.fromkeys(cap for item in chosen for cap in item["capabilities"]))
    focus = ", ".join(capabilities[:2]) or "technical systems"
    domains = list(dict.fromkeys(domain for item in chosen for domain in item["domains"]))
    domain_text = ", ".join(domains[:3]) or "technical system development"
    summary = (
        f"{title} with project experience in {focus}. Applies {skill_text} to practical "
        f"engineering work. Portfolio spans {domain_text}, combining complementary "
        "technical capabilities with hands-on implementation experience across distinct projects."
    )
    # Headlines and summaries never introduce a technology missing from the registry.
    content = TailoredResumeContent(
        target_role=job.title, classification=config["classification"], application_type="PROFILE_PORTFOLIO",
        headline=" | ".join([title, *skills["selected_skills"][:3]]), summary=summary,
        education=_canonical_education(profile), projects=projects,
        skill_categories=skills["categories"], selected_skills=skills["selected_skills"],
        job_skill_matches=skills["matches"], skill_verification=skills["verification"],
        languages=resume_language_lines(profile),
        section_order=["summary", "education", "skills", "projects", "languages"],
        match_score=round(sum(x["score"] for x in chosen) / len(chosen), 1),
        why_this_version=[f"Profile: {config['label']}", "Projects evaluated using the 25/20/15/15/10/10/5 evidence rubric.", "The combination rewards distinct capabilities and penalizes redundant classroom exercises."],
        changes=[{"section": "Projects", "description": "Selected an evidence-weighted, complementary project portfolio.", "reason": "Real technical value, not keyword count."}],
    )
    return validate_generated_resume(content, profile, job, minimum_projects=minimum_projects)


def analyze_studio_profile(profile: Any, profile_id: str) -> dict[str, Any]:
    config = studio_config(profile_id)
    ranking = rank_studio_projects(profile, profile_id)
    selected = [item for item in ranking if item["selected"]]
    content = generate_studio_content(build_studio_job(profile_id), profile) if len(selected) >= 2 else None
    return {
        "profile_id": profile_id, "label": config["label"], "description": config["description"],
        "summary": content.summary if content else "Add at least two evidenced projects before generating this CV.",
        "headline": content.headline if content else profile.headline,
        "can_generate": content is not None, "projects": ranking,
        "selected_skills": content.selected_skills if content else [],
        "weights": WEIGHTS,
        "notice": "Scores assess stored project descriptions; they are not independently verified code audits or a match to a specific job.",
    }
