from __future__ import annotations

import json
import re
from itertools import combinations
from types import SimpleNamespace
from typing import Any

from app.schemas.api import ResumeCourseItem, TailoredResumeContent
from app.services.resume_generation import (
    _canonical_education,
    _clean_list,
    _item_value,
    _project_bullets,
    _valid_url,
    sanitize_resume_text,
    validate_generated_resume,
)
from app.services.language_evidence import (
    canonical_language_credentials,
    verified_german_certificate,
    verified_ielts,
)
from app.services.resume_skills import build_verified_skill_registry, select_job_skills


DEFAULT_UNIVERSITIES = [
    "Karlsruhe Institute of Technology (KIT)",
    "TU Braunschweig",
    "Ulm University",
]
DEFAULT_INTERESTS = ["Robotics", "Embedded Systems", "Control", "Digital Systems"]
KOSPIE_CV_PROJECT_ORDER = (
    "MATT Web-Controlled Writing Robot",
    "Intel MAX 10 Robotic Arm Controller",
    "FreeRTOS Event-Driven System",
    "SkiliAir Air Quality Monitoring System",
    "Internship Radar - AI Resume Tailoring Platform",
)
KOSPIE_SKILL_GROUPS = (
    (
        "Embedded Systems",
        ("FreeRTOS", "Microcontrollers", "Robotics", "Hardware/Software Integration"),
    ),
    ("Programming", ("Python", "C", "C++", "Verilog", "SystemVerilog")),
    ("Digital Systems & Hardware", ("FPGA", "Intel MAX 10", "UART", "PWM")),
)
KOSPIE_COURSE_NAMES = (
    "Python Data Structures",
    "Using Python to Access Web Data",
    "Programming for Everybody (Getting Started with Python)",
)
UNIVERSITY_CONTEXT = {
    "Karlsruhe Institute of Technology (KIT)": [
        "Robotics", "Automation", "Control", "Embedded Systems", "Autonomous Systems",
    ],
    "TU Braunschweig": [
        "Robotics", "Robot Systems", "Autonomous Systems", "Control",
        "Machine Learning for Robotics",
    ],
    "Ulm University": [
        "Embedded Systems", "Real-Time Systems", "Robotics", "Computer Architecture",
        "Autonomous Systems",
    ],
}
LOW_PRIORITY_SIGNALS = (
    "generic web", "simple crud", "basic react", "landing page", "tutorial",
    "small class exercise",
)
PROJECT_DOMAINS = {
    "Robotics": (
        "robot", "robotics", "actuator", "manipulation", "computer vision",
    ),
    "Embedded Systems": (
        "embedded", "freertos", "microcontroller", "gpio", "adc",
        "interrupt", "esp32", "kl25z", "raspberry pi", "i2c", "spi", "uart",
    ),
    "FPGA / Digital Systems": (
        "fpga", "verilog", "systemverilog", "rtl", "digital logic", "testbench",
    ),
    "Software Engineering": (
        "software", "full-stack", "backend", "frontend", "fastapi", "next.js",
        "database", "postgresql", "sqlalchemy", "api", "architecture", "latex",
        "pdf", "openai", "ai-assisted", "authentication", "versioning",
        "order book", "priority queue", "graph algorithm", "object-oriented",
    ),
    "Control Systems": (
        "control", "feedback", "encoder", "pid", "pwm", "motor", "actuation",
    ),
}
PRACTICAL_SIGNALS = (
    "built", "designed", "developed", "implemented", "integrated", "programmed",
    "tested", "validated", "simulated", "deployed", "tracks", "generates",
    "processed", "calculated", "computed", "measured",
)
DEPTH_EVIDENCE = {
    "algorithms and data structures": (
        "algorithm", "price-time priority", "priority queue", "order book",
        "matching engine", "graph traversal", "path validation", "ranking",
    ),
    "concurrency and real-time behavior": (
        "freertos", "task coordination", "concurrent", "multithreaded",
        "mutex", "semaphore", "real-time behavior",
    ),
    "digital hardware design": (
        "rtl", "verilog", "systemverilog", "finite-state machine", "fpga",
        "testbench", "waveform analysis",
    ),
    "system architecture": (
        "full-stack platform", "authenticated backend", "frontend workflow",
        "modular prototype", "database-backed", "version history",
        "hardware/software integration",
    ),
    "data and state modeling": (
        "database", "postgresql", "mysql", "sqlalchemy", "order processing",
        "game state", "file-based input",
    ),
    "hardware timing": (
        "interrupt", "timing", "100 ms", "real-time", "pwm control",
    ),
    "verification and debugging": (
        "tested", "validated", "simulated", "testbench", "waveform",
        "debugging", "safe-stop",
    ),
    "sensing and measurement": (
        "sensor data", "encoder", "measurement", "characterization", "pm2.5",
        "pm10", "accelerometer",
    ),
    "communications": (
        "uart communication", "serial", "rest api", "i2c", "wireless command",
    ),
    "control and coordination": (
        "motor control", "actuator coordination", "control loop", "pwm",
    ),
}
DEPTH_WEIGHTS = {
    "algorithms and data structures": 20,
    "concurrency and real-time behavior": 20,
    "digital hardware design": 20,
    "system architecture": 20,
    "data and state modeling": 12,
    "hardware timing": 12,
    "verification and debugging": 10,
    "sensing and measurement": 8,
    "communications": 8,
    "control and coordination": 10,
}
SUBSYSTEM_EVIDENCE = {
    "embedded controller": (
        "esp32", "frdm-kl25z", "microcontroller", "raspberry pi", "intel max 10",
    ),
    "digital logic": ("fpga", "rtl", "verilog", "systemverilog"),
    "communications": ("uart", "i2c", "spi", "serial", "wireless"),
    "sensing": ("sensor", "encoder", "accelerometer", "adc", "pm2.5", "pm10"),
    "actuation": ("motor", "actuator", "pwm", "buzzer", "ventilation"),
    "concurrency": ("freertos", "mutex", "semaphore", "task coordination"),
    "backend/API": ("backend", "fastapi", "flask", "rest api"),
    "database/storage": ("database", "postgresql", "mysql", "sqlalchemy", "file-based"),
    "frontend/UI": ("frontend", "next.js", "chart.js", "dashboard", "lcd", "vga", "web-operated"),
    "document pipeline": ("latex", "pdf", "resume generation"),
    "authentication": ("authentication", "authenticated", "auth.js"),
    "algorithms": ("algorithm", "matching engine", "order book", "priority queue", "graph"),
    "computer vision": ("computer vision", "opencv", "camera"),
}
DISTINCTIVE_CAPABILITIES = {
    "integrated robotics prototype": (
        "writing robot", "web-operated", "actuator coordination", "computer-vision interface",
    ),
    "real-time concurrency": ("freertos", "mutex", "semaphore", "task coordination"),
    "FPGA and RTL design": ("fpga", "rtl", "verilog", "systemverilog"),
    "full-stack engineering platform": (
        "full-stack platform", "authenticated backend", "postgresql", "latex and pdf",
    ),
    "sensor-to-cloud monitoring": ("air-quality monitor", "pm2.5", "flask rest api", "mysql logging"),
    "algorithmic matching engine": ("limit order book", "price-time priority", "matching engine"),
    "control measurement": ("motor and encoder characterization", "calculate rpm", "angular position"),
    "graph algorithms": ("graph game", "graph traversal", "path validation"),
}
SCOPE_COMPLETE_MARKERS = (
    "platform", "prototype", "controller", "monitor", "matching engine",
    "order book", "working system", "web-operated", "live measurements",
)
SCOPE_FOCUSED_MARKERS = (
    "characterization", "technical exercise", "focused practice", "graph game",
)
SCOPE_LAB_MARKERS = (
    "small lab", "laboratory practice", "classroom exercise", "tutorial",
    "led exercise", "basic implementation",
)
COURSE_SIGNALS = (
    "control", "embedded", "signal", "digital", "electronic", "instrumentation",
    "algorithm", "computer architecture", "robot", "fpga", "communication",
    "real-time", "computer vision", "data structures",
)
def kospie_language_evidence(profile: Any) -> tuple[list[str], list[dict[str, Any]]]:
    languages: list[str] = []
    statuses: list[dict[str, Any]] = []
    credentials = canonical_language_credentials(profile)
    spanish = next(
        (item for item in credentials if item["language"].casefold() == "spanish"),
        None,
    )
    spanish_verified = bool(
        spanish
        and spanish["verified"] is True
        and spanish["proficiency"].casefold() == "native"
    )
    if spanish_verified:
        languages.append("Spanish - Native")
    statuses.append({
        "language": "Spanish", "status": "VERIFIED" if spanish_verified else "NOT VERIFIED",
        "evidence": "Native" if spanish_verified else "No verified profile evidence",
    })

    ielts = verified_ielts(profile)
    if ielts and ielts["score"]:
        languages.append(f"English - IELTS Academic {ielts['score']}")
        try:
            met = float(ielts["score"]) >= 6.0
        except ValueError:
            met = False
        statuses.append({
            "language": "English", "status": "VERIFIED", "exam": "IELTS Academic",
            "score": ielts["score"], "minimum": "6.0", "requirement": "MET" if met else "NOT MET",
        })
    else:
        statuses.append({
            "language": "English", "status": "NOT VERIFIED", "minimum": "IELTS Academic 6.0",
            "requirement": "NOT YET VERIFIED",
        })

    german = verified_german_certificate(profile)
    if german:
        level = german["score"] or german["proficiency"]
        languages.append(f"German - {level} ({german['certificate']})")
        requirement = "MET" if re.search(r"\b(?:A2|B[12]|C[12])\b", level, re.I) else "REVIEW"
        statuses.append({
            "language": "German", "status": "VERIFIED", "exam": german["certificate"],
            "score": level, "minimum": "A2", "requirement": requirement,
            "eligibility_evidence": f"{german['certificate']} {level}".strip(),
        })
    else:
        current_german = next(
            (
                item
                for item in credentials
                if item["language"].casefold() == "german"
                and item["verified"] is True
                and item["proficiency"]
            ),
            None,
        )
        if current_german:
            german_level = current_german["proficiency"]
            if german_level.casefold() == "basic":
                german_level = "Basic proficiency"
            languages.append(f"German - {german_level}")
        statuses.append({
            "language": "German",
            "status": "PROFILE VERIFIED" if current_german else "NOT VERIFIED",
            "evidence": (
                f"{current_german['proficiency']} (self-reported current proficiency)"
                if current_german
                else "No verified profile evidence"
            ),
            "minimum": "Official A2 certificate",
            "requirement": "NOT YET VERIFIED",
            "eligibility_evidence": (
                f"Current profile level: {current_german['proficiency']}; "
                "no official A2 certificate verified."
                if current_german
                else "No official A2 certificate verified."
            ),
            "action_required": "Obtain an accepted official German A2 certificate.",
        })
    return languages, statuses


def _context_terms(config: Any) -> list[str]:
    terms = list(getattr(config, "primary_interests_json", []) or [])
    for university in getattr(config, "selected_universities_json", []) or []:
        terms.extend(UNIVERSITY_CONTEXT.get(university, []))
    return list(dict.fromkeys(sanitize_resume_text(item) for item in terms if sanitize_resume_text(item)))


def project_engineering_domains(item: dict[str, Any]) -> list[str]:
    text = json.dumps(item, ensure_ascii=False).lower()
    return [
        domain
        for domain, signals in PROJECT_DOMAINS.items()
        if any(signal in text for signal in signals)
    ]


def _matched_evidence(text: str, groups: dict[str, tuple[str, ...]]) -> list[str]:
    return [
        label
        for label, signals in groups.items()
        if any(signal in text for signal in signals)
    ]


def _project_scope_type(
    item: dict[str, Any],
    text: str,
    subsystem_count: int,
) -> str:
    explicit = _item_value(item, "project_type", "scope_type").casefold()
    if explicit in {"complete project", "complete", "system"}:
        return "complete_project"
    if explicit in {"focused technical exercise", "focused", "technical practice"}:
        return "focused_technical_exercise"
    if explicit in {"laboratory practice", "lab", "classroom exercise"}:
        return "laboratory_practice"
    if any(marker in text for marker in SCOPE_LAB_MARKERS):
        return "laboratory_practice"
    if any(marker in text for marker in SCOPE_FOCUSED_MARKERS):
        return "focused_technical_exercise"
    if subsystem_count >= 3 and any(marker in text for marker in SCOPE_COMPLETE_MARKERS):
        return "complete_project"
    return "focused_technical_exercise"


def _technical_assessment(score: float, evidence: list[str]) -> str:
    detail = ", ".join(evidence[:4]) or "limited implementation evidence"
    if score >= 75 and len(evidence) >= 2:
        return f"Technical strength: strong technical depth supported by {detail}."
    if score >= 55:
        return f"Technical strength: moderate depth supported by {detail}."
    return f"Technical strength: limited depth; evidence shows {detail}."


def _scope_assessment(scope_type: str) -> str:
    return {
        "complete_project": "Scope: complete multi-component project.",
        "focused_technical_exercise": "Scope: focused technical exercise, not a complete system.",
        "laboratory_practice": "Scope: laboratory or classroom practice.",
    }[scope_type]


def kospie_project_assessment(
    item: dict[str, Any],
    context_terms: list[str],
) -> dict[str, Any]:
    """Apply the evidence-weighted project rubric used by KOSPIE resumes."""

    text = json.dumps(item, ensure_ascii=False).casefold()
    bullets = _project_bullets(item)
    domains = project_engineering_domains(item)
    depth_evidence = _matched_evidence(text, DEPTH_EVIDENCE)
    subsystems = _matched_evidence(text, SUBSYSTEM_EVIDENCE)
    capabilities = _matched_evidence(text, DISTINCTIVE_CAPABILITIES)
    scope_type = _project_scope_type(item, text, len(subsystems))

    domain_relevance = {
        "Robotics": 91.0,
        "Embedded Systems": 88.0,
        "FPGA / Digital Systems": 88.0,
        "Control Systems": 86.0,
        "Software Engineering": 64.0,
    }
    relevance = max((domain_relevance[domain] for domain in domains), default=35.0)
    context_matches = {
        term.casefold() for term in context_terms if term.casefold() in text
    }
    relevance = min(100.0, relevance + min(9.0, len(context_matches) * 3.0))

    technical_depth = min(
        100.0,
        18.0 + sum(DEPTH_WEIGHTS[label] for label in depth_evidence),
    )
    scope = {
        "complete_project": 90.0,
        "focused_technical_exercise": 56.0,
        "laboratory_practice": 28.0,
    }[scope_type]
    if len(bullets) >= 3:
        scope = min(100.0, scope + 5.0)
    if "near completion" in text or "complete" in text:
        scope = min(100.0, scope + 4.0)

    integration_scale = {0: 15.0, 1: 30.0, 2: 50.0, 3: 68.0, 4: 82.0}
    system_integration = (
        92.0 if len(subsystems) >= 5 else integration_scale[len(subsystems)]
    )
    integration_is_explicit = any(
        verb in " ".join(bullets).casefold()
        for verb in ("integrated", "connects", "coordinates", "across", "exposes")
    )
    if not integration_is_explicit:
        system_integration = min(system_integration, 55.0)
    if scope_type == "focused_technical_exercise":
        system_integration = min(system_integration, 65.0)
    if scope_type == "laboratory_practice":
        system_integration = min(system_integration, 45.0)

    implementation_text = " ".join(bullets).casefold()
    ownership_verbs = {
        verb
        for verb in PRACTICAL_SIGNALS
        if re.search(rf"\b{re.escape(verb)}\w*\b", implementation_text)
    }
    ownership = min(100.0, 35.0 + len(ownership_verbs) * 15.0)

    outcome_markers = {
        marker
        for marker in (
            "prototype", "operating", "live", "deployed", "validated", "tested",
            "display", "calculate", "measurement", "generated", "working",
        )
        if marker in text
    }
    outcome = {
        "complete_project": 68.0,
        "focused_technical_exercise": 43.0,
        "laboratory_practice": 28.0,
    }[scope_type]
    outcome = min(100.0, outcome + len(outcome_markers) * 6.0)
    differentiation = min(
        95.0,
        42.0 + len(capabilities) * 18.0 + max(0, len(domains) - 1) * 3.0,
    )

    generic_penalty = 0.0
    generic_markers = [signal for signal in LOW_PRIORITY_SIGNALS if signal in text]
    if generic_markers:
        generic_penalty = min(22.0, 10.0 + len(generic_markers) * 3.0)
    classroom_penalty = 0.0
    if scope_type == "laboratory_practice":
        classroom_penalty = 8.0 if technical_depth >= 75 else 20.0
    elif scope_type == "focused_technical_exercise" and any(
        marker in text for marker in ("characterization", "classroom exercise", "small lab")
    ):
        classroom_penalty = 8.0

    weighted_score = (
        relevance * 0.25
        + technical_depth * 0.20
        + scope * 0.15
        + system_integration * 0.15
        + ownership * 0.10
        + outcome * 0.10
        + differentiation * 0.05
    )
    score = min(100.0, max(0.0, weighted_score - generic_penalty - classroom_penalty))
    resume_value = round(
        (technical_depth + scope + system_integration + ownership + outcome) / 5.0,
        1,
    )
    return {
        "name": _item_value(item, "name", "title"),
        "score": round(score, 1),
        "domains": domains,
        "project_type": scope_type,
        "depth_evidence": depth_evidence,
        "subsystems": subsystems,
        "capabilities": capabilities,
        "technical_assessment": _technical_assessment(technical_depth, depth_evidence),
        "scope_assessment": _scope_assessment(scope_type),
        "components": {
            "relevance": round(relevance, 1),
            "technical_depth": round(technical_depth, 1),
            "project_scope": round(scope, 1),
            "system_integration": round(system_integration, 1),
            "ownership": round(ownership, 1),
            "outcome_completeness": round(outcome, 1),
            "differentiation": round(differentiation, 1),
            "resume_value": resume_value,
            "generic_penalty": round(generic_penalty, 1),
            "classroom_exercise_penalty": round(classroom_penalty, 1),
        },
    }


def score_kospie_project(item: dict[str, Any], context_terms: list[str]) -> float:
    return float(kospie_project_assessment(item, context_terms)["score"])


def rank_kospie_projects(
    profile: Any,
    context_terms: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    assessed: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for index, item in enumerate(profile.projects_json or []):
        if not isinstance(item, dict) or item.get("is_resume_eligible", True) is not True:
            continue
        if not _item_value(item, "name", "title") or len(_project_bullets(item)) < 2:
            continue
        assessed.append((index, item, kospie_project_assessment(item, context_terms)))

    def portfolio_value(entries: tuple[tuple[int, dict[str, Any], dict[str, Any]], ...]) -> float:
        score = sum(entry[2]["score"] for entry in entries)
        domains = {domain for entry in entries for domain in entry[2]["domains"]}
        capabilities = {
            capability for entry in entries for capability in entry[2]["capabilities"]
        }
        score += len(domains) * 2.0 + len(capabilities) * 3.5
        for left, right in combinations(entries, 2):
            left_domains = set(left[2]["domains"])
            right_domains = set(right[2]["domains"])
            left_capabilities = set(left[2]["capabilities"])
            right_capabilities = set(right[2]["capabilities"])
            overlap = left_domains & right_domains
            union = left_domains | right_domains
            capability_overlap = left_capabilities & right_capabilities
            if union and (capability_overlap or not left_capabilities or not right_capabilities):
                score -= 3.0 * len(overlap) / len(union)
            score -= 8.0 * len(capability_overlap)
            if (
                left[2]["project_type"] != "complete_project"
                and right[2]["project_type"] != "complete_project"
                and overlap
            ):
                score -= 4.0
        return score

    desired_count = min(4, len(assessed), limit)
    fifth_candidates = [entry for entry in assessed if entry[2]["score"] >= 58]
    if limit >= 5 and len(fifth_candidates) >= 5:
        desired_count = 5
    pool = fifth_candidates if desired_count == 5 else assessed
    selected_tuple = max(
        combinations(pool, desired_count),
        key=lambda group: (portfolio_value(group), tuple(-entry[0] for entry in group)),
        default=(),
    )
    selected_ids = {entry[0] for entry in selected_tuple}
    selected_assessments = [entry[2] for entry in selected_tuple]
    capability_counts = {
        capability: sum(
            capability in assessment["capabilities"]
            for assessment in selected_assessments
        )
        for capability in DISTINCTIVE_CAPABILITIES
    }
    selected_capabilities = {
        capability
        for assessment in selected_assessments
        for capability in assessment["capabilities"]
    }
    minimum_selected_score = min(
        (assessment["score"] for assessment in selected_assessments),
        default=0.0,
    )
    ranking = sorted(assessed, key=lambda entry: (-entry[2]["score"], entry[0]))
    return [
        {
            **assessment,
            "rank": rank,
            "selected": index in selected_ids,
            "reasons": [
                (
                    "Selected because its evidence-weighted value and complementary contribution "
                    "strengthen the complete portfolio."
                    if index in selected_ids
                    else (
                        "Rejected because stronger alternatives provide greater scope and interview value."
                        if assessment["project_type"] != "complete_project"
                        and assessment["score"] < minimum_selected_score
                        else (
                            "Rejected because higher-value selected projects already cover its main capabilities."
                            if assessment["capabilities"]
                            and set(assessment["capabilities"]) <= selected_capabilities
                            else "Rejected because its total evidence and portfolio contribution are weaker than the selected combination."
                        )
                    )
                ),
                assessment["technical_assessment"],
                assessment["scope_assessment"],
                (
                    "Integration: explicit evidence supports multi-component system integration across "
                    + ", ".join(assessment["subsystems"][:5])
                    + "."
                    if assessment["project_type"] == "complete_project"
                    and assessment["components"]["system_integration"] >= 75
                    and len(assessment["subsystems"]) >= 4
                    else (
                        "Integration: evidence supports a focused integration chain, not a broad multi-component system."
                        if assessment["components"]["system_integration"] >= 50
                        else "Integration: limited subsystem integration is evidenced."
                    )
                ),
                (
                    "Unique value: "
                    + ", ".join(
                        capability
                        for capability in assessment["capabilities"]
                        if capability_counts.get(capability, 0) == 1
                    )
                    + "."
                    if index in selected_ids and any(
                        capability_counts.get(capability, 0) == 1
                        for capability in assessment["capabilities"]
                    )
                    else (
                        "Unique value: adds " + ", ".join(assessment["capabilities"]) + "."
                        if assessment["capabilities"]
                        else "Unique value: reinforces existing portfolio capabilities rather than adding a distinct one."
                    )
                ),
            ],
        }
        for rank, (index, _item, assessment) in enumerate(ranking, start=1)
    ]


def _select_kospie_projects(profile: Any, context_terms: list[str], limit: int = 5) -> list[dict[str, Any]]:
    verified_skills = {sanitize_resume_text(item).lower() for item in profile.skills_json or []}
    source_by_name = {
        _item_value(item, "name", "title"): item
        for item in profile.projects_json or []
        if isinstance(item, dict)
    }
    ranked = rank_kospie_projects(profile, context_terms, limit=limit)
    selected: list[dict[str, Any]] = []
    for assessment in ranked:
        if not assessment["selected"]:
            continue
        item = source_by_name[assessment["name"]]
        bullets = _project_bullets(item)
        technologies = [
            sanitize_resume_text(value) for value in item.get("technologies", [])
            if sanitize_resume_text(value).lower() in verified_skills
        ][:5]
        repository = _item_value(item, "repository_url", "github_url", "url") or None
        selected.append({
            "name": _item_value(item, "name", "title"), "technologies": technologies,
            "status": _item_value(item, "status"), "dates": _item_value(item, "dates", "date"),
            "github_url": repository if item.get("is_public", True) and _valid_url(repository) else None,
            "live_url": None, "relevance_score": assessment["score"], "bullets": bullets,
        })
    preferred_order = {
        name: index for index, name in enumerate(KOSPIE_CV_PROJECT_ORDER)
    }
    selected.sort(key=lambda item: preferred_order.get(item["name"], len(preferred_order)))
    return selected


def _select_kospie_skills(
    job: Any,
    profile: Any,
    projects: list[dict[str, Any]],
) -> dict[str, Any]:
    registry = build_verified_skill_registry(profile)
    categories = [
        {
            "name": name,
            "items": [skill for skill in requested if skill in registry],
        }
        for name, requested in KOSPIE_SKILL_GROUPS
    ]
    categories = [group for group in categories if group["items"]]
    selected_skills = [skill for group in categories for skill in group["items"]]
    category_by_skill = {
        skill: group["name"]
        for group in categories
        for skill in group["items"]
    }
    scored = select_job_skills(
        job,
        profile,
        "KOSPIE / Germany Engineering",
        selected_project_names={item["name"] for item in projects},
        model_requested=selected_skills,
        limit=16,
    )
    match_by_skill = {item["skill"]: item for item in scored["matches"]}
    matches = []
    for skill in selected_skills:
        match = dict(match_by_skill.get(skill, {
            "skill": skill,
            "match_type": "contextual",
            "score": 0,
            "reason": "Verified supporting skill",
            "evidence": registry[skill]["evidence"],
            "job_occurrences": 0,
        }))
        match["category"] = category_by_skill[skill]
        matches.append(match)
    return {
        "categories": categories,
        "selected_skills": selected_skills,
        "matches": matches,
        "verification": {
            "all_verified": True,
            "verified": selected_skills,
            "removed": [],
            "registry_size": len(registry),
        },
    }


def _course_sources(profile: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for raw in profile.coursework_json or []:
        if isinstance(raw, dict) and _item_value(raw, "name"):
            sources.append(raw)
        elif isinstance(raw, str) and sanitize_resume_text(raw):
            sources.append({"name": sanitize_resume_text(raw), "institution": ""})
    education = profile.education_json[0] if profile.education_json and isinstance(profile.education_json[0], dict) else {}
    for raw in education.get("coursework", []) or []:
        if isinstance(raw, str) and sanitize_resume_text(raw):
            sources.append({"name": sanitize_resume_text(raw), "institution": ""})
    unique: dict[str, dict[str, Any]] = {}
    for item in sources:
        unique.setdefault(_item_value(item, "name").casefold(), item)
    return list(unique.values())


def _select_kospie_courses(profile: Any) -> list[dict[str, Any]]:
    sources = {
        _item_value(raw, "name"): raw
        for raw in _course_sources(profile)
    }
    return [
        {
            "name": name,
            "institution": _item_value(sources[name], "institution"),
            "issued": _item_value(sources[name], "issued"),
            "areas": [
                sanitize_resume_text(value)
                for value in sources[name].get("areas", [])
            ][:4],
            "priority": _item_value(sources[name], "priority") or "normal",
        }
        for name in KOSPIE_COURSE_NAMES
        if name in sources
    ]


def _experience(profile: Any) -> list[dict[str, Any]]:
    result = []
    for raw in profile.experience_json or []:
        if not isinstance(raw, dict):
            continue
        title = _item_value(raw, "title", "role")
        organization = _item_value(raw, "organization", "company")
        bullets = _clean_list(raw.get("bullets", raw.get("highlights", [])), limit=3)
        if title and organization and bullets:
            result.append({
                "title": title, "organization": organization,
                "location": _item_value(raw, "location"), "dates": _item_value(raw, "dates", "date"),
                "bullets": bullets,
            })
    return result[:2]


def build_kospie_job(config: Any, profile: Any, user_profile: Any | None = None) -> Any:
    context = _context_terms(config)
    languages, statuses = kospie_language_evidence(profile)
    additional: list[str] = []
    if user_profile and getattr(user_profile, "citizenship_country", "").casefold() == "mexico" and getattr(user_profile, "citizenship_status", "") == "CONFIRMED":
        additional.append("Mexican citizen")
    if user_profile and getattr(user_profile, "willing_to_relocate", False):
        additional.append("Available for international mobility")
    return SimpleNamespace(
        title="KOSPIE 2027-2028 Engineering CV", company="DAAD + Tecnológico de Monterrey",
        area="International Academic + Professional Program",
        description=(
            "Intensive German course, academic semester at a German university, and professional "
            f"internship in Germany. Engineering context: {', '.join(context)}."
        ),
        requirements="Academic performance, engineering coursework, IELTS Academic 6.0, German A2 certificate.",
        preferred_qualifications="Robotics, embedded systems, control, digital systems, practical engineering projects.",
        resume_target="kospie_germany", application_type="KOSPIE_PROGRAM", analysis=None,
        selected_universities=list(config.selected_universities_json), kospie_context=context,
        kospie_resume_languages=languages, kospie_language_status=statuses,
        kospie_additional_information=additional,
    )


def _eligibility(profile: Any, user_profile: Any | None, statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    education = profile.education_json[0] if profile.education_json and isinstance(profile.education_json[0], dict) else {}
    english = next(item for item in statuses if item["language"] == "English")
    german = next(item for item in statuses if item["language"] == "German")
    mexican = bool(user_profile and getattr(user_profile, "citizenship_country", "").casefold() == "mexico" and getattr(user_profile, "citizenship_status", "") == "CONFIRMED")
    return [
        {"requirement": "GPA requirement", "status": "REVIEW", "evidence": _item_value(education, "gpa") or "Not verified", "note": "No GPA conversion was performed."},
        {"requirement": "Credit requirement", "status": "NOT YET VERIFIED", "evidence": "No verified credit total is stored."},
        {"requirement": "English certificate", "status": english.get("requirement", "NOT YET VERIFIED"), "evidence": f"IELTS Academic {english.get('score', '')}".strip()},
        {"requirement": "German certificate (A2 minimum)", "status": german.get("requirement", "NOT YET VERIFIED"), "evidence": german.get("eligibility_evidence", german.get("score", "No official certificate verified")), "action_required": german.get("action_required", "")},
        {"requirement": "Mexican citizenship", "status": "MET" if mexican else "NOT YET VERIFIED", "evidence": "Mexico" if mexican else "Confirm in Profile"},
        {"requirement": "Academic standing", "status": "NOT YET VERIFIED", "evidence": "Official standing documentation is not stored."},
    ]


def generate_kospie_content(job: Any, profile: Any) -> TailoredResumeContent:
    context = list(getattr(job, "kospie_context", []) or [])
    projects = _select_kospie_projects(profile, context, limit=5)
    skills = _select_kospie_skills(job, profile, projects)
    courses = _select_kospie_courses(profile)
    languages = list(getattr(job, "kospie_resume_languages", []) or [])
    language_status = list(getattr(job, "kospie_language_status", []) or [])
    why = [
        "Prioritized robotics, embedded systems, control, and physical engineering projects for the selected German universities.",
        "Kept Education and the original GPA scale prominent for an academic selection committee.",
        "Included only verified engineering skills and coursework from the candidate profile.",
    ]
    if any("IELTS Academic" in item for item in languages):
        english_evidence = next(item for item in languages if item.startswith("English - "))
        why.append(f"Included {english_evidence.removeprefix('English - ')} as verified English evidence.")
    if any(item.startswith("German - ") for item in languages) and not any(
        item.get("language") == "German" and item.get("requirement") in {"MET", "REVIEW"}
        for item in language_status
    ):
        german_evidence = next(item for item in languages if item.startswith("German - "))
        why.append(
            f"Included {german_evidence.removeprefix('German - ')} as the verified current German "
            "profile level; the official A2 certificate requirement remains unverified."
        )
    elif not any(item.startswith("German") for item in languages):
        why.append("German proficiency was excluded because no official German certificate is verified.")
    content = TailoredResumeContent(
        application_type="KOSPIE_PROGRAM", target_role="KOSPIE 2027-2028 Engineering CV",
        classification="KOSPIE / Germany Engineering",
        headline=(
            "Robotics and Digital Systems Engineering Student | "
            "Embedded Systems | Robotics | Software"
        ),
        summary="", skill_categories=skills["categories"], selected_skills=skills["selected_skills"],
        job_skill_matches=skills["matches"], skill_verification=skills["verification"],
        education=_canonical_education(profile), experience=_experience(profile), projects=projects,
        coursework=[ResumeCourseItem.model_validate(item) for item in courses], certifications=[],
        languages=languages, research_interests=[], opportunity_research_areas=[],
        additional_information=list(getattr(job, "kospie_additional_information", []) or []),
        language_verification=language_status, program_eligibility=[], why_this_version=why,
        section_order=[
            "education", "skills", "projects", "languages",
            "additional_information", "coursework",
        ],
        match_score=round(sum(item["relevance_score"] for item in projects) / max(1, len(projects)), 1),
        keywords_used=[item for item in context if item in build_verified_skill_registry(profile)],
        keywords_missing=[], unsupported_requirements=[],
        changes=[
            {"section": "Education", "description": "Placed verified education and GPA first.", "reason": "KOSPIE is an academic and engineering program."},
            {"section": "Projects", "description": "Ranked projects by engineering depth and selected-university relevance.", "reason": "University context affects ranking only and never creates facts."},
            {"section": "Languages", "description": "Used verified candidate language evidence while keeping certificate requirements separate.", "reason": "German Basic is a current profile level, while German A2 remains an eligibility gap until officially certified."},
            {"section": "Courses", "description": "Placed verified additional courses after Additional Information.", "reason": "These certificates complement the degree instead of replacing representative university coursework."},
        ],
        warnings=["German A2 remains an eligibility requirement; no official German certificate is currently verified."],
    )
    return validate_generated_resume(content, profile, job)


def analyze_kospie_profile(profile: Any, user_profile: Any | None, config: Any) -> dict[str, Any]:
    job = build_kospie_job(config, profile, user_profile)
    content = generate_kospie_content(job, profile)
    project_ranking = rank_kospie_projects(profile, list(job.kospie_context), limit=5)
    education = profile.education_json[0]
    academic = [
        f"{_item_value(education, 'degree')} at {_item_value(education, 'institution')}",
    ]
    if _item_value(education, "gpa"):
        academic.append(f"Verified GPA: {_item_value(education, 'gpa')} (original scale retained)")
    if content.coursework:
        academic.append(f"{len(content.coursework)} verified courses selected for engineering relevance")
    eligibility = _eligibility(profile, user_profile, content.language_verification)
    content.program_eligibility = eligibility
    strong_courses = [item.model_dump() for item in content.coursework if any(term in item.name.lower() for term in COURSE_SIGNALS)]
    relevant_courses = [item.model_dump() for item in content.coursework if item.model_dump() not in strong_courses]
    return {
        "academic_strengths": academic,
        "technical_strengths": content.selected_skills,
        "recommended_projects": [
            {
                "name": item["name"],
                "match": round(item["score"]),
                "why": "; ".join(item["reasons"]),
                "reasons": item["reasons"],
                "domains": item["domains"],
                "selected": item["selected"],
                "rank": item["rank"],
                "project_type": item["project_type"],
                "depth_evidence": item["depth_evidence"],
                "subsystems": item["subsystems"],
                "capabilities": item["capabilities"],
                "components": item["components"],
            }
            for item in project_ranking
        ],
        "recommended_skills": content.selected_skills,
        "recommended_coursework": {"strong": strong_courses, "relevant": relevant_courses},
        "language_status": content.language_verification, "eligibility": eligibility,
        "selected_universities": list(config.selected_universities_json),
        "primary_interests": list(config.primary_interests_json),
    }
