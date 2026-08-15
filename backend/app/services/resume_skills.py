from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any


SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "C++": ("c++", "c plus plus", "cpp", "c/c++"),
    "PostgreSQL": ("postgresql", "postgres", "postgres sql"),
    "REST APIs": ("rest apis", "rest api", "restful api", "restful apis"),
    "TypeScript": ("typescript", "type script"),
    "JavaScript": ("javascript", "java script"),
    "Next.js": ("next.js", "nextjs", "next js"),
    "FastAPI": ("fastapi", "fast api"),
    "MySQL": ("mysql", "my sql"),
    "FreeRTOS": ("freertos", "free rtos", "rtos"),
    "Multithreaded Programming": (
        "multithreaded programming", "multi-threaded programming",
        "multithreading", "multi threading", "threading",
    ),
    "Concurrent Programming": (
        "concurrent programming", "concurrency", "concurrent systems",
    ),
    "Hardware/Software Integration": (
        "hardware/software integration", "hardware software integration",
        "hardware-software integration", "hw/sw integration",
    ),
    "Object-Oriented Programming": (
        "object-oriented programming", "object oriented programming", "oop",
    ),
    "Data Structures": ("data structures", "data structure"),
    "Microcontrollers": ("microcontrollers", "microcontroller", "mcu", "mcus"),
    "Raspberry Pi": ("raspberry pi", "raspberrypi"),
    "FRDM-KL25Z": ("frdm-kl25z", "frdm kl25z", "kl25z"),
    "Intel MAX 10": ("intel max 10", "max 10", "de10-lite", "de10 lite"),
    "FPGA": ("fpga", "fpgas"),
    "FPGA Design": ("fpga design", "fpga development"),
    "Digital Logic": ("digital logic", "logic design"),
    "Hardware Debugging": ("hardware debugging", "board-level debugging"),
    "Software Debugging": ("software debugging", "debugging software"),
    "Software Validation": (
        "software validation", "software verification", "system validation",
    ),
    "Full-Stack Development": (
        "full-stack development", "full stack development", "fullstack development",
    ),
    "Backend Development": ("backend development", "back-end development"),
}

SKILL_CATEGORY: dict[str, str] = {
    **{name: "Languages" for name in (
        "C", "C++", "Python", "TypeScript", "JavaScript", "Java", "SQL", "Verilog",
        "SystemVerilog",
    )},
    **{name: "Embedded / Systems" for name in (
        "FreeRTOS", "Embedded Systems", "Firmware", "Linux", "Microcontrollers",
        "FRDM-KL25Z", "ESP32", "Raspberry Pi", "Interrupts", "Mutexes",
        "Semaphores", "Queues", "Tasks", "ISRs", "Timers", "Concurrent Programming",
        "Multithreaded Programming", "Hardware/Software Integration", "File I/O",
        "Robotics", "Controls", "ROS", "Computer Vision", "OpenCV",
    )},
    **{name: "Backend / Web" for name in (
        "REST APIs", "FastAPI", "Flask", "Next.js", "PostgreSQL", "MySQL",
        "SQLAlchemy", "Pydantic", "OpenAI API", "Firebase", "Backend Development",
        "Full-Stack Development", "Auth.js",
    )},
    **{name: "Hardware" for name in (
        "FPGA", "FPGA Design", "Intel MAX 10", "Digital Logic", "Digital Design",
        "UART", "SPI", "I2C", "GPIO", "ADC", "PWM", "Electronics", "PCB",
    )},
    **{name: "Development" for name in (
        "Object-Oriented Programming", "Data Structures", "Algorithms",
        "Graph Algorithms", "Path Validation", "API Development",
    )},
    **{name: "Debug & Validation" for name in (
        "Hardware Debugging", "Software Debugging", "Software Validation", "Testing",
        "Debugging", "Oscilloscope", "Logic Analyzer",
    )},
    **{name: "Tools" for name in (
        "Git", "GitHub", "Docker", "VS Code", "MCUXpresso", "PlatformIO",
        "Jinja2", "LaTeX", "Tectonic", "Cloud",
    )},
}

ROLE_SKILL_PRIORITIES: dict[str, tuple[str, ...]] = {
    "Embedded / Firmware": (
        "C", "C++", "FreeRTOS", "Embedded Systems", "Linux", "Microcontrollers",
        "UART", "GPIO", "ADC", "PWM", "Interrupts", "Hardware Debugging",
        "Software Debugging", "Software Validation", "Concurrent Programming",
        "Multithreaded Programming", "Git",
    ),
    "Software Engineering": (
        "C++", "Python", "Data Structures", "Algorithms",
        "Object-Oriented Programming", "Git", "Linux", "REST APIs",
        "Software Debugging", "Software Validation", "Docker", "C",
    ),
    "Backend / Data": (
        "Python", "FastAPI", "Flask", "PostgreSQL", "SQL", "REST APIs",
        "Docker", "Git", "Linux", "SQLAlchemy", "Data Structures",
        "Object-Oriented Programming", "Backend Development",
    ),
    "FPGA / Digital Design": (
        "Verilog", "SystemVerilog", "FPGA", "FPGA Design", "Digital Logic",
        "Intel MAX 10", "GPIO", "PWM", "UART", "C", "Testing", "Git",
    ),
    "Robotics / Controls": (
        "C", "C++", "Python", "Embedded Systems", "Microcontrollers", "FreeRTOS",
        "UART", "PWM", "Raspberry Pi", "Hardware/Software Integration", "Robotics",
        "Controls", "Linux", "Git",
    ),
    "Full Stack / Web": (
        "TypeScript", "Next.js", "Python", "FastAPI", "PostgreSQL", "REST APIs",
        "Docker", "Git", "JavaScript", "SQLAlchemy", "Full-Stack Development",
    ),
    "AI / API Integration": (
        "Python", "REST APIs", "FastAPI", "Pydantic", "OpenAI API", "PostgreSQL",
        "Docker", "Git", "Linux", "Data Structures", "Algorithms",
    ),
    "Developer Tools / Productivity": (
        "Python", "TypeScript", "FastAPI", "Pydantic", "Jinja2", "Docker", "Git",
        "PostgreSQL", "REST APIs", "Software Validation",
    ),
    "Maps / Routing / Geospatial": (
        "C++", "Python", "Data Structures", "Algorithms", "Graph Algorithms",
        "Path Validation", "Object-Oriented Programming", "REST APIs", "Linux", "Git",
    ),
}

IGNORED_EVIDENCE_LABELS = {
    "api", "apis", "backend", "cloud", "software engineering", "web data",
    "python fundamentals",
}


def _clean(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _key(value: Any) -> str:
    text = _clean(value).lower().replace("&", " and ")
    text = re.sub(r"[-_/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


ALIAS_TO_CANONICAL = {
    _key(alias): canonical
    for canonical, aliases in SKILL_ALIASES.items()
    for alias in (canonical, *aliases)
}


def canonicalize_skill(value: Any) -> str:
    cleaned = _clean(value)
    return ALIAS_TO_CANONICAL.get(_key(cleaned), cleaned)


def skill_category(skill: str) -> str:
    if skill in SKILL_CATEGORY:
        return SKILL_CATEGORY[skill]
    lowered = skill.lower()
    if any(term in lowered for term in ("debug", "test", "validat", "oscilloscope")):
        return "Debug & Validation"
    if any(term in lowered for term in ("api", "sql", "backend", "web", "database")):
        return "Backend / Web"
    if any(term in lowered for term in ("fpga", "hardware", "gpio", "uart", "pwm")):
        return "Hardware"
    return "Tools"


def build_verified_skill_registry(profile: Any) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    def add(raw_skill: Any, evidence: str, evidence_type: str) -> None:
        skill = canonicalize_skill(raw_skill)
        if not skill or _key(skill) in IGNORED_EVIDENCE_LABELS:
            return
        item = registry.setdefault(skill, {
            "skill": skill,
            "category": skill_category(skill),
            "evidence": [],
            "evidence_types": [],
        })
        if evidence not in item["evidence"]:
            item["evidence"].append(evidence)
        if evidence_type not in item["evidence_types"]:
            item["evidence_types"].append(evidence_type)

    for skill in getattr(profile, "skills_json", []) or []:
        add(skill, "Verified skill record", "profile")

    for project in getattr(profile, "projects_json", []) or []:
        if not isinstance(project, dict) or project.get("is_resume_eligible", True) is not True:
            continue
        name = _clean(project.get("name") or project.get("title") or "Verified project")
        for skill in project.get("technologies", []) or []:
            add(skill, f"Project: {name}", "project")

    for course in getattr(profile, "coursework_json", []) or []:
        if not isinstance(course, dict):
            continue
        name = _clean(course.get("name") or "Verified course")
        for skill in course.get("areas", []) or []:
            add(skill, f"Course: {name}", "course")

    for experience in getattr(profile, "experience_json", []) or []:
        if not isinstance(experience, dict):
            continue
        name = _clean(experience.get("organization") or experience.get("title") or "Experience")
        for field in ("skills", "technologies"):
            for skill in experience.get(field, []) or []:
                add(skill, f"Experience: {name}", "experience")
    return registry


def grouped_verified_skill_registry(profile: Any) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in build_verified_skill_registry(profile).values():
        grouped.setdefault(item["category"], []).append(item)
    order = [
        "Languages", "Embedded / Systems", "Backend / Web", "Hardware",
        "Development", "Debug & Validation", "Tools",
    ]
    return [
        {
            "name": name,
            "items": sorted(grouped[name], key=lambda value: value["skill"].lower()),
        }
        for name in order
        if grouped.get(name)
    ]


def _aliases_for(skill: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((skill, *SKILL_ALIASES.get(skill, ()))))


def _occurrences(skill: str, text: str) -> int:
    lowered = unicodedata.normalize("NFKC", text).lower()
    total = 0
    for alias in _aliases_for(skill):
        # '+' and '#' are token characters for language names. Without them in
        # the boundaries, a C requirement would incorrectly match C++ or C#.
        pattern = rf"(?<![a-z0-9+#]){re.escape(alias.lower())}(?![a-z0-9+#])"
        total += len(re.findall(pattern, lowered))
    return total


def _description_segments(description: str) -> tuple[str, str, str]:
    required: list[str] = []
    preferred: list[str] = []
    contextual: list[str] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|[\r\n]+", description):
        lowered = sentence.lower()
        if any(term in lowered for term in (
            "required", "requirement", "must have", "must be", "minimum qualification",
            "basic qualification",
        )):
            required.append(sentence)
        elif any(term in lowered for term in (
            "preferred", "nice to have", "bonus", "plus", "desired qualification",
        )):
            preferred.append(sentence)
        else:
            contextual.append(sentence)
    return " ".join(required), " ".join(preferred), " ".join(contextual)


def _display_category(skill: str, classification: str) -> str:
    base = skill_category(skill)
    if classification == "Embedded / Firmware":
        return {
            "Languages": "Languages", "Embedded / Systems": "Systems",
            "Hardware": "Hardware", "Debug & Validation": "Debug & Validation",
        }.get(base, "Development")
    if classification == "FPGA / Digital Design":
        return {
            "Languages": "Languages", "Hardware": "Hardware",
            "Embedded / Systems": "Hardware", "Debug & Validation": "Tools",
        }.get(base, "Tools")
    if classification == "Backend / Data":
        return {
            "Languages": "Languages", "Backend / Web": "Backend",
            "Development": "Development", "Debug & Validation": "Development",
        }.get(base, "Tools")
    if classification == "Software Engineering":
        return {
            "Languages": "Languages", "Development": "Development",
            "Debug & Validation": "Development",
            "Embedded / Systems": "Systems", "Hardware": "Systems",
            "Backend / Web": "Development", "Tools": "Tools",
        }.get(base, "Tools")
    if classification == "Full Stack / Web":
        return {
            "Languages": "Languages", "Backend / Web": "Backend / Web",
            "Development": "Development", "Debug & Validation": "Development",
        }.get(base, "Tools")
    if classification == "Robotics / Controls":
        return {
            "Languages": "Languages", "Embedded / Systems": "Systems",
            "Hardware": "Hardware",
        }.get(base, "Tools")
    return {
        "Languages": "Languages", "Development": "Development",
        "Debug & Validation": "Development", "Embedded / Systems": "Tools",
        "Hardware": "Tools",
    }.get(base, "Tools")


def select_job_skills(
    job: Any,
    profile: Any,
    classification: str,
    selected_project_names: set[str] | None = None,
    model_requested: list[str] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    registry = build_verified_skill_registry(profile)
    required_field = _clean(getattr(job, "requirements", ""))
    preferred_field = _clean(getattr(job, "preferred_qualifications", ""))
    description = _clean(getattr(job, "description", ""))
    desc_required, desc_preferred, desc_contextual = _description_segments(description)
    required_text = f"{required_field} {desc_required}"
    preferred_text = f"{preferred_field} {desc_preferred}"
    contextual_text = " ".join((
        _clean(getattr(job, "title", "")), desc_contextual,
    ))
    all_job_text = " ".join((required_text, preferred_text, contextual_text))
    priorities = ROLE_SKILL_PRIORITIES.get(classification, ())
    priority_index = {skill: index for index, skill in enumerate(priorities)}
    requested = {
        canonicalize_skill(skill) for skill in (model_requested or [])
        if canonicalize_skill(skill) in registry
    }
    selected_projects = selected_project_names or set()
    ranked: list[dict[str, Any]] = []

    for skill, item in registry.items():
        required_hits = _occurrences(skill, required_text)
        preferred_hits = _occurrences(skill, preferred_text)
        contextual_hits = _occurrences(skill, contextual_text)
        total_hits = _occurrences(skill, all_job_text)
        project_evidence = [
            evidence for evidence in item["evidence"]
            if evidence.startswith("Project:")
        ]
        selected_project_evidence = [
            evidence for evidence in project_evidence
            if evidence.removeprefix("Project: ") in selected_projects
        ]
        score = 0
        reasons: list[str] = []
        match_type = "contextual"
        if required_hits:
            score += 30
            match_type = "required"
            reasons.append("Direct job requirement")
        elif preferred_hits:
            score += 22
            match_type = "preferred"
            reasons.append("Preferred qualification")
        elif contextual_hits:
            score += 14
            reasons.append("Appears in the job description")
        if total_hits > 1:
            score += 18
            reasons.append("Repeated job keyword")
        if selected_project_evidence:
            score += 15
            reasons.append("Demonstrated in a selected project")
        if len(project_evidence) > 1:
            score += 12
            reasons.append("Demonstrated across multiple projects")
        if skill in priority_index:
            score += 8
            reasons.append(f"Relevant to {classification}")
        if "course" in item["evidence_types"]:
            score += 5
            reasons.append("Supported by verified coursework")
        if skill in requested:
            score += 3
        if not total_hits and skill not in priority_index:
            score -= 15
        ranked.append({
            "skill": skill,
            "category": _display_category(skill, classification),
            "match_type": match_type,
            "score": score,
            "reason": "; ".join(dict.fromkeys(reasons)) or "Verified supporting skill",
            "evidence": item["evidence"],
            "job_occurrences": total_hits,
        })

    ranked.sort(key=lambda item: (
        -item["score"],
        priority_index.get(item["skill"], 999),
        item["skill"].lower(),
    ))
    target_count = min(16, max(8, limit), len(ranked))
    chosen = ranked[:target_count]

    # Avoid redundant aliases and near-identical variants in the final compact list.
    redundancy_groups = (
        {"FPGA", "FPGA Design"},
        {"Digital Logic", "Digital Design"},
        {"Debugging", "Software Debugging"},
        {"Concurrent Programming", "Multithreaded Programming"},
    )
    deduplicated: list[dict[str, Any]] = []
    for candidate in ranked:
        if any(candidate["skill"] in group and any(
            existing["skill"] in group for existing in deduplicated
        ) for group in redundancy_groups):
            continue
        deduplicated.append(candidate)
        if len(deduplicated) >= target_count:
            break
    chosen = deduplicated

    category_counts = Counter(item["category"] for item in chosen)
    # Keep categories substantial: add the best verified companion for a singleton,
    # or remove the low-value singleton when no companion exists.
    for category, count in list(category_counts.items()):
        if count != 1:
            continue
        alternatives = [
            item for item in ranked
            if item not in chosen and item["category"] == category
        ]
        if alternatives and len(chosen) < target_count:
            chosen.append(alternatives[0])
        elif alternatives:
            removable = [
                item for item in chosen
                if item["category"] != category
                and category_counts[item["category"]] > 2
            ]
            if removable:
                chosen.remove(min(removable, key=lambda item: item["score"]))
                chosen.append(alternatives[0])
            elif len(chosen) > 8 and len(category_counts) > 2:
                chosen = [item for item in chosen if item["category"] != category]
        elif len(chosen) > 8 and len(category_counts) > 2:
            chosen = [item for item in chosen if item["category"] != category]
        category_counts = Counter(item["category"] for item in chosen)

    chosen.sort(key=lambda item: (
        -item["score"], priority_index.get(item["skill"], 999), item["skill"].lower()
    ))
    groups: dict[str, list[str]] = {}
    for item in chosen:
        groups.setdefault(item["category"], []).append(item["skill"])
    category_order = []
    for item in chosen:
        if item["category"] not in category_order:
            category_order.append(item["category"])
    categories = [
        {"name": category, "items": groups[category]}
        for category in category_order[:4]
    ]
    selected_skills = [skill for group in categories for skill in group["items"]]
    match_by_skill = {item["skill"]: item for item in chosen}
    chosen = [match_by_skill[skill] for skill in selected_skills]
    return {
        "categories": categories,
        "selected_skills": selected_skills,
        "matches": chosen,
        "verification": {
            "all_verified": True,
            "verified": [item["skill"] for item in chosen],
            "removed": [],
            "registry_size": len(registry),
        },
    }


def filter_and_verify_skill_categories(
    categories: list[Any],
    profile: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = build_verified_skill_registry(profile)
    verified: list[str] = []
    removed: list[str] = []
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_group in categories:
        group_mapping = raw_group if isinstance(raw_group, dict) else {}
        name = _clean(getattr(raw_group, "name", None) or group_mapping.get("name", ""))
        raw_items = getattr(raw_group, "items", None)
        if raw_items is None:
            raw_items = group_mapping.get("items", [])
        items: list[str] = []
        for raw_skill in raw_items or []:
            skill = canonicalize_skill(raw_skill)
            if skill not in registry:
                removed.append(_clean(raw_skill))
                continue
            if skill in seen:
                continue
            seen.add(skill)
            verified.append(skill)
            items.append(skill)
        if items:
            groups.append({"name": name or "Technical", "items": items})
    return groups, {
        "all_verified": not removed,
        "verified": verified,
        "removed": removed,
        "registry_size": len(registry),
    }
