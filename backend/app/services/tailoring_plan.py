"""Evidence-only planning layer for future job-specific resume tailoring.

This module deliberately does not generate text, choose resume sections, or
render documents.  It converts one scoped job and one scoped candidate profile
into an explainable ``TailoringPlan`` that later phases can consume.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from app.services.project_evidence import project_role_view, implemented_claims

from app.services.resume_skills import (
    SKILL_ALIASES,
    SKILL_CATEGORY,
    build_verified_skill_registry,
    canonicalize_skill,
    skill_category,
)


class RequirementImportance(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    CONTEXTUAL = "contextual"


class SkillMatchState(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    ALIAS_MATCH = "ALIAS_MATCH"
    SUPPORTED_SEMANTIC_MATCH = "SUPPORTED_SEMANTIC_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    NOT_FOUND = "NOT_FOUND"


class EvidenceSource(StrEnum):
    PROJECT = "project"
    SKILL = "skill"
    COURSEWORK = "coursework"
    CERTIFICATION = "certification"
    EXPERIENCE = "experience"


class JobRequirement(BaseModel):
    requirement_id: str
    requirement: str
    normalized_requirement: str
    type: Literal["technology", "responsibility", "role"]
    importance: RequirementImportance
    importance_weight: int = Field(ge=1, le=100)
    source_terms: list[str] = Field(default_factory=list)


class CandidateEvidence(BaseModel):
    source: EvidenceSource
    source_name: str
    claim: str
    canonical_skill: str = ""
    verified: bool = True
    evidence_strength: int = Field(ge=0, le=100)
    confidence: Literal["high", "medium", "low"]


class RequirementEvidenceMapping(BaseModel):
    requirement: JobRequirement
    match_state: SkillMatchState
    matched_candidate_evidence: list[CandidateEvidence] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]
    evidence_strength: int = Field(ge=0, le=100)
    explanation: str


class ProjectEvaluation(BaseModel):
    project_name: str
    technical_depth: int = Field(ge=0, le=100)
    ownership: int = Field(ge=0, le=100)
    integration: int = Field(ge=0, le=100)
    complexity: int = Field(ge=0, le=100)
    outcome: int = Field(ge=0, le=100)
    domain_relevance: int = Field(ge=0, le=100)
    job_relevance: int = Field(ge=0, le=100)
    role_evidence_score: int = Field(ge=0, le=100)
    role_evidence_notes: list[str] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)
    selected: bool = False


class ResumeDecisions(BaseModel):
    """Evidence-backed resume decisions; populated by Phase 2."""

    status: Literal["DEFERRED", "PLANNED"] = "DEFERRED"
    selected_projects: list[str] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    selected_certifications: list[str] = Field(default_factory=list)
    selected_experience: list[str] = Field(default_factory=list)
    # The single role used to word the headline and summary. It is derived
    # from the current job title, independently of overlapping evidence
    # categories that may be useful for matching and project evaluation.
    primary_role_category: str = ""
    summary_direction: str = ""
    headline_direction: str = ""
    missing_requirements: list[str] = Field(default_factory=list)
    selected_project_scores: dict[str, float] = Field(default_factory=dict)
    selected_project_reasons: dict[str, list[str]] = Field(default_factory=dict)
    selected_skill_evidence: dict[str, list[CandidateEvidence]] = Field(default_factory=dict)
    selected_skill_categories: list[dict[str, Any]] = Field(default_factory=list)
    editorial_review: dict[str, Any] = Field(default_factory=dict)


class TailoringPlan(BaseModel):
    owner_user_id: str
    job_id: int | None = None
    # Snapshot identity is the job primary key plus the relevant posting
    # content, never a fuzzy title comparison.
    job_content_hash: str = ""
    job_title: str
    company: str
    role_categories: list[str]
    # Stable, machine-readable role categories. Multiple codes may apply to
    # one job; these classify the opportunity, never the candidate's skills.
    role_category_codes: list[str] = Field(default_factory=list)
    normalized_requirements: list[JobRequirement]
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    requirement_evidence: list[RequirementEvidenceMapping]
    project_evaluations: list[ProjectEvaluation]
    resume_decisions: ResumeDecisions


# A semantic relation is intentionally explicit. It is evidence support, not a
# claim that two technologies are equivalent. The candidate must still have a
# verified skill on the right-hand side for a match to be emitted.
SEMANTIC_SUPPORT: dict[str, set[str]] = {
    "API Development": {"REST APIs", "FastAPI", "Flask"},
    "Backend Development": {"REST APIs", "FastAPI", "Flask", "PostgreSQL", "SQLAlchemy"},
    "Embedded Systems": {"Microcontrollers", "FreeRTOS", "UART", "I2C", "SPI", "PWM"},
    "Firmware": {"C", "C++", "FreeRTOS", "Microcontrollers", "Interrupts"},
    "Digital Design": {"FPGA", "Verilog", "SystemVerilog", "Digital Logic"},
}

SECURITY_REQUIREMENTS = {
    "Cybersecurity", "Network Security", "Application Security", "Threat Modeling",
    "Penetration Testing", "SIEM", "SOC", "Incident Response", "Cryptography",
    "Vulnerability Management", "Security Engineering", "Malware Analysis",
}

# These are employer-side technical domains that must remain visible in a
# plan even when the candidate has no verified equivalent.  They are not
# inferred skills and therefore naturally receive NOT_FOUND evidence unless
# the profile explicitly supports them.
EXPLICIT_JOB_TERMS: dict[str, tuple[str, ...]] = {
    "Networking": ("networking", "network protocols", "network programming"),
    "Distributed Systems": ("distributed systems", "distributed system"),
    "C++23": ("c++23", "c++ 23"),
    "Automated Trading Systems": (
        "automated trading systems", "automated trading system", "algorithmic trading",
    ),
}

RESPONSIBILITY_MARKERS = (
    "responsibilities", "responsible for", "you will", "you'll", "design and",
    "develop and", "build and", "implement and", "test and", "integrate and",
    "collaborate with", "support the",
)

ROLE_CATEGORY_SIGNALS: dict[str, tuple[str, ...]] = {
    "Electrical / Validation": ("electrical validation", "electrical testing", "electrical test", "signal integrity", "pcie", "oscilloscope"),
    "Computer Vision / Image Processing": ("computer vision", "image processing", "opencv", "visual perception"),
    "Software Engineering": ("software", "backend", "api", "developer", "programming"),
    "Embedded / Firmware": (
        "embedded", "firmware", "microcontroller", "microcontrollers", "mcu",
        "freertos", "rtos",
    ),
    "FPGA / Digital Design": ("fpga", "verilog", "systemverilog", "rtl", "digital design"),
    "Hardware / Systems": ("hardware", "pcb", "board", "electromechanical", "signal integrity"),
    "Robotics / Controls": ("robot", "robotics", "control", "actuator", "sensor", "motion"),
    "Research / Research Engineering": (
        "research intern", "research internship", "student researcher",
        "research engineering", "research engineer", "industrial research",
    ),
    "Security Consulting": ("security consultant", "security consulting", "security advisory"),
    "Security Engineering": ("security engineering", "security engineer", "application security", "network security"),
    "Cybersecurity": ("cybersecurity", "cyber security", "security", "threat", "vulnerability", "siem"),
    "System Security": ("system security", "systems security", "security consultant", "security engineering"),
}

ROLE_CATEGORY_CODES = {
    "Electrical / Validation": "ELECTRICAL_VALIDATION",
    "Security Consulting": "SECURITY_CONSULTING",
    "Security Engineering": "SECURITY_ENGINEERING",
    "Cybersecurity": "CYBERSECURITY",
    "System Security": "SYSTEM_SECURITY",
    "Software Engineering": "SOFTWARE_ENGINEERING",
    "Embedded / Firmware": "EMBEDDED_FIRMWARE",
    "FPGA / Digital Design": "FPGA_DIGITAL_DESIGN",
    "Hardware / Systems": "HARDWARE_SYSTEMS",
    "Robotics / Controls": "ROBOTICS_CONTROLS",
    "Research / Research Engineering": "RESEARCH_ENGINEERING",
}


def _clean(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _key(value: Any) -> str:
    text = _clean(value).casefold().replace("&", " and ")
    text = re.sub(r"[-_/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#]){re.escape(_key(term))}(?![a-z0-9+#])", _key(text)) is not None


def _value(source: Any, field: str, default: Any = "") -> Any:
    return source.get(field, default) if isinstance(source, dict) else getattr(source, field, default)


def _require_scoped_inputs(job: Any, profile: Any, owner_user_id: str) -> None:
    profile_owner = _clean(_value(profile, "user_id"))
    job_owner = _clean(_value(job, "owner_user_id"))
    if not owner_user_id:
        raise ValueError("TailoringPlan requires an authenticated owner_user_id.")
    if profile_owner != owner_user_id:
        raise ValueError("Resume evidence belongs to a different user.")
    if job_owner and job_owner != owner_user_id:
        raise ValueError("Job belongs to a different user.")


def job_content_hash(job: Any) -> str:
    """Stable fingerprint for the parts of a posting that affect tailoring.

    Source timestamps may change during a refresh without changing the role, so
    they are intentionally excluded.  A changed description, requirements,
    preferred qualifications, requisition, title, or source payload creates a
    new plan snapshot.
    """
    payload = {
        "job_id": _value(job, "id"),
        "external_id": _clean(_value(job, "external_id")),
        "company": _clean(_value(job, "company")),
        "title": _clean(_value(job, "title")),
        "description": _clean(_value(job, "description")),
        "requirements": _clean(_value(job, "requirements")),
        "preferred_qualifications": _clean(_value(job, "preferred_qualifications")),
        "raw_data_hash": _clean(_value(job, "raw_data_hash")),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _job_segments(job: Any) -> dict[RequirementImportance, str]:
    description = _clean(_value(job, "description"))
    required_from_description: list[str] = []
    preferred_from_description: list[str] = []
    contextual: list[str] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|[\r\n]+", description):
        lowered = sentence.casefold()
        if any(marker in lowered for marker in ("required", "must have", "minimum qualification", "basic qualification")):
            required_from_description.append(sentence)
        elif any(marker in lowered for marker in ("preferred", "nice to have", "desired qualification", "bonus")):
            preferred_from_description.append(sentence)
        else:
            contextual.append(sentence)
    return {
        RequirementImportance.REQUIRED: " ".join((_clean(_value(job, "requirements")), *required_from_description)),
        RequirementImportance.PREFERRED: " ".join((_clean(_value(job, "preferred_qualifications")), *preferred_from_description)),
        RequirementImportance.CONTEXTUAL: " ".join((_clean(_value(job, "title")), *contextual)),
    }


def _requirement_catalog(profile: Any) -> set[str]:
    catalog = set(SKILL_ALIASES) | set(SKILL_CATEGORY) | set(SEMANTIC_SUPPORT) | set(SECURITY_REQUIREMENTS)
    for raw in _value(profile, "skills_json", []) or []:
        if _clean(raw):
            catalog.add(canonicalize_skill(raw))
    for project in _value(profile, "projects_json", []) or []:
        if isinstance(project, dict):
            catalog.update(canonicalize_skill(item) for item in project.get("technologies", []) if _clean(item))
    for course in _value(profile, "coursework_json", []) or []:
        if isinstance(course, dict):
            catalog.update(canonicalize_skill(item) for item in course.get("areas", []) if _clean(item))
    for certification in _value(profile, "certifications_json", []) or []:
        if isinstance(certification, dict) and certification.get("verified") is True:
            catalog.update(canonicalize_skill(item) for item in certification.get("skills", []) if _clean(item))
    for experience in _value(profile, "experience_json", []) or []:
        if isinstance(experience, dict):
            for field in ("skills", "technologies"):
                catalog.update(canonicalize_skill(item) for item in experience.get(field, []) if _clean(item))
    for repository in _value(profile, "github_evidence_json", []) or []:
        if isinstance(repository, dict) and str(repository.get("status", "")).upper() == "VERIFIED":
            catalog.update(canonicalize_skill(item) for item in repository.get("technologies", []) if _clean(item))
    return {_clean(item) for item in catalog if _clean(item)}


def _importance_weight(importance: RequirementImportance) -> int:
    return {
        RequirementImportance.REQUIRED: 100,
        RequirementImportance.PREFERRED: 60,
        RequirementImportance.CONTEXTUAL: 30,
    }[importance]


def _extract_requirements(job: Any, profile: Any) -> tuple[list[JobRequirement], list[str]]:
    segments = _job_segments(job)
    catalog = _requirement_catalog(profile)
    candidates: dict[str, tuple[str, RequirementImportance, list[str]]] = {}
    for raw_term in catalog:
        canonical = canonicalize_skill(raw_term)
        for importance in (RequirementImportance.REQUIRED, RequirementImportance.PREFERRED, RequirementImportance.CONTEXTUAL):
            text = segments[importance]
            aliases = {raw_term, canonical, *SKILL_ALIASES.get(canonical, ())}
            matched_aliases = [alias for alias in aliases if _contains_term(text, alias)]
            if not matched_aliases:
                continue
            existing = candidates.get(canonical)
            if existing is None or _importance_weight(importance) > _importance_weight(existing[1]):
                candidates[canonical] = (canonical, importance, list(dict.fromkeys(matched_aliases)))
            elif existing[1] == importance:
                candidates[canonical] = (existing[0], importance, list(dict.fromkeys([*existing[2], *matched_aliases])))
            break

    # Keep explicit technical domains in the job understanding even if they
    # are absent from candidate evidence; omission would incorrectly make the
    # plan look like the employer never requested them.
    for canonical, aliases in EXPLICIT_JOB_TERMS.items():
        for importance in (RequirementImportance.REQUIRED, RequirementImportance.PREFERRED, RequirementImportance.CONTEXTUAL):
            text = segments[importance]
            matched_aliases = [alias for alias in aliases if _contains_term(text, alias)]
            if not matched_aliases:
                continue
            existing = candidates.get(canonical)
            if existing is None or _importance_weight(importance) > _importance_weight(existing[1]):
                candidates[canonical] = (canonical, importance, list(dict.fromkeys(matched_aliases)))
            elif existing[1] == importance:
                candidates[canonical] = (existing[0], importance, list(dict.fromkeys([*existing[2], *matched_aliases])))
            break

    responsibilities: list[str] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|[\r\n]+", _clean(_value(job, "description"))):
        clean_sentence = _clean(sentence)
        if clean_sentence and any(marker in clean_sentence.casefold() for marker in RESPONSIBILITY_MARKERS):
            responsibilities.append(clean_sentence[:300])

    requirements = [
        JobRequirement(
            requirement_id=f"skill:{_key(name).replace(' ', '-')}",
            requirement=name,
            normalized_requirement=canonicalize_skill(name),
            type="technology",
            importance=importance,
            importance_weight=_importance_weight(importance),
            source_terms=source_terms,
        )
        for name, importance, source_terms in candidates.values()
    ]
    for index, responsibility in enumerate(dict.fromkeys(responsibilities)):
        requirements.append(JobRequirement(
            requirement_id=f"responsibility:{index + 1}", requirement=responsibility,
            normalized_requirement=_key(responsibility), type="responsibility",
            importance=RequirementImportance.CONTEXTUAL, importance_weight=40,
            source_terms=[responsibility],
        ))
    requirements.sort(key=lambda item: (-item.importance_weight, item.type, item.normalized_requirement.casefold()))
    return requirements, responsibilities


def _confidence(strength: int, state: SkillMatchState) -> Literal["high", "medium", "low", "none"]:
    if state == SkillMatchState.NOT_FOUND:
        return "none"
    if strength >= 80:
        return "high"
    if strength >= 55:
        return "medium"
    return "low"


def _evidence_from_profile(profile: Any) -> list[CandidateEvidence]:
    evidence: list[CandidateEvidence] = []

    def add(source: EvidenceSource, source_name: str, claim: Any, strength: int) -> None:
        cleaned = _clean(claim)
        if not cleaned:
            return
        evidence.append(CandidateEvidence(
            source=source, source_name=_clean(source_name) or source.value,
            claim=cleaned, canonical_skill=canonicalize_skill(cleaned), verified=True,
            evidence_strength=strength,
            confidence="high" if strength >= 80 else "medium" if strength >= 55 else "low",
        ))

    for skill in _value(profile, "skills_json", []) or []:
        add(EvidenceSource.SKILL, "Verified skill record", skill, 65)
    for project in _value(profile, "projects_json", []) or []:
        if not isinstance(project, dict) or project.get("is_resume_eligible", True) is not True:
            continue
        name = _clean(project.get("name") or project.get("title") or "Verified project")
        for skill in project.get("technologies", []) or []:
            add(EvidenceSource.PROJECT, name, skill, 85)
    # Public repository evidence may corroborate a technology that is visible
    # in source. It is never treated as employment, a deployment, or a
    # completed resume project; it only supplies bounded technical evidence.
    for repository in _value(profile, "github_evidence_json", []) or []:
        if not isinstance(repository, dict) or str(repository.get("status", "")).upper() != "VERIFIED":
            continue
        source_name = f"GitHub repository: {_clean(repository.get('name') or 'verified source') }"
        for skill in repository.get("technologies", []) or []:
            add(EvidenceSource.PROJECT, source_name, skill, 75)
    for course in _value(profile, "coursework_json", []) or []:
        if not isinstance(course, dict):
            continue
        name = _clean(course.get("name") or "Verified course")
        for skill in course.get("areas", []) or []:
            add(EvidenceSource.COURSEWORK, name, skill, 55)
    # Certifications are separate from coursework because a verified course
    # credential is evidence in its own right.  Only explicitly verified,
    # skill-bounded records can support a requirement; no issuer or title is
    # expanded into unproven tooling or professional experience.
    for certification in _value(profile, "certifications_json", []) or []:
        if not isinstance(certification, dict) or certification.get("verified") is not True:
            continue
        name = _clean(certification.get("name") or certification.get("title") or "Verified certification")
        for skill in certification.get("skills", []) or []:
            add(EvidenceSource.CERTIFICATION, name, skill, 60)
    for experience in _value(profile, "experience_json", []) or []:
        if not isinstance(experience, dict):
            continue
        name = _clean(experience.get("organization") or experience.get("title") or "Verified experience")
        for field in ("skills", "technologies"):
            for skill in experience.get(field, []) or []:
                add(EvidenceSource.EXPERIENCE, name, skill, 90)
    return evidence


def _match_requirement(requirement: JobRequirement, evidence: list[CandidateEvidence]) -> RequirementEvidenceMapping:
    if requirement.type != "technology":
        return RequirementEvidenceMapping(
            requirement=requirement, match_state=SkillMatchState.NOT_FOUND,
            confidence="none", evidence_strength=0,
            explanation="Responsibility evidence mapping is deferred to the Phase 2 selection engine.",
        )
    canonical_requirement = canonicalize_skill(requirement.normalized_requirement)
    # ``requirement`` is canonicalized for stable plan IDs.  Preserve the
    # employer's literal term in ``source_terms`` so RESTful APIs -> REST APIs
    # remains an alias match rather than being mislabeled as exact.
    employer_terms = {_key(item) for item in (requirement.source_terms or [requirement.requirement])}
    exact = [item for item in evidence if _key(item.claim) in employer_terms]
    aliases = [item for item in evidence if item.canonical_skill == canonical_requirement and item not in exact]
    semantic = [
        item for item in evidence
        if item.canonical_skill in SEMANTIC_SUPPORT.get(canonical_requirement, set())
    ]
    requirement_tokens = set(_key(canonical_requirement).split())
    partial = [
        item for item in evidence
        if requirement_tokens and len(requirement_tokens & set(_key(item.canonical_skill).split())) >= 2
        and item not in exact and item not in aliases and item not in semantic
    ]
    if exact:
        state, matched = SkillMatchState.EXACT_MATCH, exact
    elif aliases:
        state, matched = SkillMatchState.ALIAS_MATCH, aliases
    elif semantic:
        state, matched = SkillMatchState.SUPPORTED_SEMANTIC_MATCH, semantic
    elif partial:
        state, matched = SkillMatchState.PARTIAL_MATCH, partial
    else:
        state, matched = SkillMatchState.NOT_FOUND, []
    matched = sorted(matched, key=lambda item: item.evidence_strength, reverse=True)
    strength = matched[0].evidence_strength if matched else 0
    if state == SkillMatchState.NOT_FOUND:
        explanation = "No verified candidate evidence supports this requirement."
    else:
        explanation = f"{state.replace('_', ' ').title()} supported by verified {matched[0].source.value} evidence."
    return RequirementEvidenceMapping(
        requirement=requirement, match_state=state, matched_candidate_evidence=matched,
        confidence=_confidence(strength, state), evidence_strength=strength, explanation=explanation,
    )


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if _contains_term(text, term))


def _project_evaluations(
    profile: Any,
    mappings: list[RequirementEvidenceMapping],
    role_categories: list[str],
) -> list[ProjectEvaluation]:
    required_names = {
        item.requirement.normalized_requirement
        for item in mappings if item.requirement.type == "technology"
    }
    results: list[ProjectEvaluation] = []
    for project in _value(profile, "projects_json", []) or []:
        if not isinstance(project, dict) or project.get("is_resume_eligible", True) is not True:
            continue
        name = _clean(project.get("name") or project.get("title"))
        if not name:
            continue
        project = project_role_view(project, _role_evidence_family(role_categories))
        bullets = [_clean(item) for item in project.get("bullets", []) or [] if _clean(item)]
        technologies = [_clean(item) for item in project.get("technologies", []) or [] if _clean(item)]
        text = " ".join([*bullets, *technologies, _clean(project.get("status")), _clean(project.get("project_type"))])
        depth_hits = _count_terms(text, ("algorithm", "architecture", "finite state", "concurrency", "real-time", "debug", "testbench", "simulation", "protocol", "control"))
        ownership_hits = _count_terms(" ".join(bullets), ("designed", "developed", "implemented", "built", "programmed", "integrated"))
        integration_hits = _count_terms(" ".join(bullets), ("integrated", "communication", "interface", "connect", "coordinate", "sensor", "actuator", "database", "api"))
        complexity_hits = _count_terms(text, ("concurrency", "finite state", "uart", "spi", "i2c", "fpga", "database", "authentication", "algorithm", "control"))
        outcome_hits = _count_terms(" ".join(bullets), ("tested", "validated", "deployed", "operating", "measured", "simulated", "completed"))
        project_skills = {canonicalize_skill(item) for item in technologies}
        relevance_hits = len(project_skills & required_names)
        role_evidence_score, role_evidence_notes = _role_evidence_score(role_categories, project)
        notes = [
            f"{len(bullets)} documented implementation bullet(s).",
            f"{len(technologies)} documented technology item(s).",
        ]
        if integration_hits:
            notes.append("Integration score is based on explicit implementation language, not technology count alone.")
        notes.extend(role_evidence_notes)
        results.append(ProjectEvaluation(
            project_name=name,
            technical_depth=min(100, 25 + depth_hits * 9 + min(20, len(bullets) * 6)),
            ownership=min(100, 20 + ownership_hits * 14),
            integration=min(100, 15 + integration_hits * 11),
            complexity=min(100, 20 + complexity_hits * 10),
            outcome=min(100, 15 + outcome_hits * 14),
            domain_relevance=max(
                min(100, 20 + relevance_hits * 20),
                min(100, 15 + role_evidence_score),
            ),
            job_relevance=max(min(100, relevance_hits * 30), role_evidence_score),
            role_evidence_score=role_evidence_score,
            role_evidence_notes=role_evidence_notes,
            evidence_notes=notes,
        ))
    return sorted(results, key=lambda item: item.project_name.casefold())


MATCH_FACTORS = {
    SkillMatchState.EXACT_MATCH: 1.0,
    SkillMatchState.ALIAS_MATCH: 0.94,
    SkillMatchState.SUPPORTED_SEMANTIC_MATCH: 0.70,
    SkillMatchState.PARTIAL_MATCH: 0.45,
    SkillMatchState.NOT_FOUND: 0.0,
}

# These are evidence signals, not project names or skills to claim. A signal
# contributes only when it is present in the candidate's stored project facts.
# The profile chosen here is a role family; projects are still compared against
# the specific job requirements separately in _project_requirement_coverage.
ROLE_EVIDENCE_PROFILES: dict[str, tuple[tuple[str, tuple[str, ...], int], ...]] = {
    "robotics": (
        ("feedback and motion control", ("pid", "encoder", "motor", "actuator", "motion control"), 30),
        ("implemented physical interfaces", ("uart", "pwm", "sensor", "gpio", "fpga"), 25),
        ("system integration", ("integrated", "communication", "telemetry", "interface"), 25),
        ("validation or real-time execution", ("testbench", "simulation", "validated", "real-time", "freertos"), 20),
    ),
    "vision": (
        ("image-processing implementation", ("opencv", "image processing", "computer vision", "hsv"), 45),
        ("perception methods", ("threshold", "segmentation", "detection", "classifies", "brown-spot"), 30),
        ("numerical image workflows", ("numpy", "matplotlib", "image", "camera"), 15),
        ("evaluation evidence", ("evaluated", "measured", "tested", "validated"), 10),
    ),
    "research": (
        ("implemented technical work", ("implemented", "built", "programmed", "developed", "integrated", "adapted"), 20),
        ("experimental or validation evidence", ("testbench", "simulation", "measured", "tested", "validated", "evaluated"), 35),
        ("system integration", ("integrated", "communication", "sensor", "telemetry", "interface"), 25),
        ("technical depth", ("algorithm", "real-time", "freertos", "fpga", "pid", "concurrency"), 20),
    ),
    "security": (
        ("identity or access-control evidence", ("authentication", "auth", "authorization", "access control"), 26),
        ("backend or API evidence", ("api", "fastapi", "flask", "backend", "rest", "database"), 25),
        ("Linux or systems evidence", ("linux", "operating system", "system service", "backend service", "raspberry pi"), 18),
        ("integration evidence", ("integrated", "integration", "interface", "communication", "connect"), 18),
        ("validation or testing evidence", ("validation", "validated", "testing", "tested"), 12),
        ("debugging or reliability evidence", ("debug", "reliability", "fault", "safe"), 12),
    ),
    "software": (
        ("algorithms or data-structure evidence", ("algorithm", "data structure", "graph", "priority queue"), 24),
        ("software architecture evidence", ("architecture", "object-oriented", "modular", "application"), 20),
        ("backend or API evidence", ("api", "fastapi", "flask", "backend", "database"), 20),
        ("testing or debugging evidence", ("testing", "tested", "validation", "debug"), 14),
        ("integration evidence", ("integrated", "integration", "interface"), 12),
    ),
    "embedded": (
        # C/C++ alone is not firmware evidence: small algorithm exercises can
        # use C++ without demonstrating microcontroller implementation.
        ("firmware implementation evidence", ("firmware", "embedded c", "embedded c++", "programmed"), 20),
        ("RTOS or concurrency evidence", ("freertos", "rtos", "task", "queue", "mutex", "semaphore"), 25),
        ("microcontroller or interface evidence", (
            "microcontroller", "esp32", "kl25z", "frdm-kl25z", "uart", "spi", "i2c", "gpio", "pwm", "adc",
            "ble", "bluetooth", "hid", "encoder",
        ), 24),
        ("hardware integration evidence", ("integrated", "hardware/software", "sensor", "actuator", "board"), 18),
        ("debugging or validation evidence", ("debug", "testing", "tested", "validation"), 13),
    ),
    "validation": (
        ("physical interfaces or acquisition", ("hardware", "board", "encoder", "adc", "gpio", "pwm", "sensor", "uart", "i2c", "spi"), 20),
        ("testing, simulation or debugging", ("tested", "testing", "validation", "simulation", "testbench", "waveform", "debug", "drc", "gerber", "pytest"), 30),
        ("timing, feedback or circuits", ("real-time", "sampling", "control", "feedback", "analog", "digital"), 20),
        ("software or test automation", ("python", "c++", "c", "script", "automation", "flask"), 15),
        ("system integration or telemetry", ("integrated", "integration", "interface", "telemetry", "communication"), 15),
    ),
    "fpga": (
        ("RTL or HDL evidence", ("verilog", "systemverilog", "rtl", "finite-state"), 30),
        ("FPGA or digital-design evidence", ("fpga", "digital logic", "intel max", "vga"), 25),
        ("simulation or validation evidence", ("simulation", "testbench", "waveform", "validated", "testing"), 22),
        ("hardware-interface evidence", ("uart", "pwm", "accelerometer", "interface"), 13),
    ),
}


def _role_evidence_family(role_categories: list[str]) -> str:
    # _role_categories puts an explicit title domain first, so incidental
    # technologies in the description do not override the actual role.
    primary_families = {
        "Computer Vision / Image Processing": "vision", "Robotics / Controls": "robotics",
        "FPGA / Digital Design": "fpga", "Embedded / Firmware": "embedded",
        "Electrical / Validation": "validation",
        "Software Engineering": "software", "Research / Research Engineering": "research",
    }
    if role_categories and role_categories[0] in primary_families:
        return primary_families[role_categories[0]]
    if any(category in {"Security Consulting", "Security Engineering", "Cybersecurity", "System Security"} for category in role_categories):
        return "security"
    if "FPGA / Digital Design" in role_categories:
        return "fpga"
    if "Embedded / Firmware" in role_categories:
        return "embedded"
    if "Computer Vision / Image Processing" in role_categories:
        return "vision"
    if "Robotics / Controls" in role_categories:
        return "robotics"
    if "Software Engineering" in role_categories:
        return "software"
    if "Research / Research Engineering" in role_categories:
        return "research"
    return ""


def _project_evidence_text(source: dict[str, Any]) -> str:
    return " ".join([
        _clean(source.get("resume_display_name") or source.get("name") or source.get("title")),
        _clean(source.get("project_type")),
        *[_clean(item) for item in source.get("technologies", []) or []],
        *[_clean(item) for item in implemented_claims(source.get("bullets", []) or [])],
        *[_clean(item) for item in source.get("verified_features", []) or []],
        *[_clean(item) for item in source.get("validation_evidence", []) or []],
    ])


def _role_evidence_score(
    role_categories: list[str],
    source: dict[str, Any],
) -> tuple[int, list[str]]:
    family = _role_evidence_family(role_categories)
    profile = ROLE_EVIDENCE_PROFILES.get(family, ())
    if not profile:
        return 0, []
    text = _project_evidence_text(source)
    score = 0
    notes: list[str] = []
    system_security_matches = 0
    for label, terms, weight in profile:
        if any(_contains_term(text, term) for term in terms):
            score += weight
            notes.append(f"Role evidence: {label}.")
            if family == "security" and label not in {"validation or testing evidence", "debugging or reliability evidence"}:
                system_security_matches += 1
    # A game or generic algorithm can demonstrate real skill for software
    # roles. For security roles it is deliberately discounted only when it
    # lacks systems, API, identity, or integration evidence.
    generic_exercise = any(_contains_term(text, term) for term in ("game", "graph", "algorithm", "data structure"))
    if family == "security" and generic_exercise and not system_security_matches:
        score -= 16
        notes.append("Role evidence: generic algorithm/game evidence lacks a security-system context.")
    return max(0, min(100, score)), notes


def _project_sources(profile: Any) -> dict[str, dict[str, Any]]:
    return {
        _clean(item.get("name") or item.get("title")): item
        for item in (_value(profile, "projects_json", []) or [])
        if isinstance(item, dict)
        and item.get("is_resume_eligible", True) is True
        and _clean(item.get("name") or item.get("title"))
    }


def _project_requirement_coverage(
    project_name: str,
    mappings: list[RequirementEvidenceMapping],
) -> tuple[float, set[str], list[str]]:
    coverage = 0.0
    covered: set[str] = set()
    reasons: list[str] = []
    for mapping in mappings:
        if mapping.requirement.type != "technology" or mapping.match_state == SkillMatchState.NOT_FOUND:
            continue
        evidence = [
            item for item in mapping.matched_candidate_evidence
            if item.source == EvidenceSource.PROJECT and item.source_name == project_name
        ]
        if not evidence:
            continue
        best = max(item.evidence_strength for item in evidence)
        contribution = mapping.requirement.importance_weight * MATCH_FACTORS[mapping.match_state] * (best / 100)
        coverage += contribution
        covered.add(mapping.requirement.normalized_requirement)
        reasons.append(
            f"Demonstrates {mapping.requirement.normalized_requirement} ({mapping.match_state.replace('_', ' ').title()})."
        )
    return coverage, covered, reasons


def _project_quality(evaluation: ProjectEvaluation) -> float:
    return (
        evaluation.technical_depth * .22
        + evaluation.ownership * .13
        + evaluation.integration * .15
        + evaluation.complexity * .15
        + evaluation.outcome * .10
        + evaluation.domain_relevance * .10
        + evaluation.job_relevance * .15
    )


def _demonstrated_capabilities(source: dict[str, Any]) -> set[str]:
    """Compare contributions, without counting planned features as evidence."""
    text = " ".join([
        *[_clean(item) for item in source.get("technologies", [])],
        *[_clean(item) for item in source.get("verified_features", [])],
        *[_clean(item) for item in implemented_claims(source.get("bullets", []))],
    ])
    signals = {
        "feedback control": ("pid", "encoder", "feedback"),
        "real-time execution": ("freertos", "real-time", "concurrency"),
        "physical interfaces": ("uart", "spi", "i2c", "pwm", "gpio"),
        "analog acquisition": ("adc", "dac", "analog reference"),
        "digital design": ("fpga", "verilog", "rtl", "digital logic"),
        "multi-axis robotics": ("cartesian", "homing", "two-axis", "two axis"),
        "immersive interaction": ("webxr", "meta quest", "vr", "headset"),
        "remote integration": ("mqtt", "websocket", "ble", "bluetooth", "telemetry"),
        "physical sensing": ("sensor", "ldr", "air quality", "accelerometer"),
        "image processing": ("opencv", "hsv", "image processing", "segmentation"),
        "backend services": ("fastapi", "rest api", "backend"),
        "persistent data": ("database", "postgresql", "sql", "firebase"),
        "identity and security": ("authentication", "authorization", "access control"),
        "algorithms": ("algorithm", "graph", "data structure", "matching engine"),
        "validation": ("testbench", "simulation", "tested", "validated", "measured", "drc", "gerber", "pytest"),
        "circuit design": ("kicad", "pcb", "power distribution", "schematic"),
    }
    return {label for label, terms in signals.items() if any(_contains_term(text, term) for term in terms)}


def _select_projects_from_plan(
    plan: TailoringPlan,
    profile: Any,
    *,
    limit: int,
) -> tuple[list[str], dict[str, float], dict[str, list[str]], dict[str, Any]]:
    """Choose a complementary set from plan evidence, never role project lists."""
    sources = _project_sources(profile)
    required_total = sum(
        item.requirement.importance_weight for item in plan.requirement_evidence
        if item.requirement.type == "technology" and item.match_state != SkillMatchState.NOT_FOUND
    ) or 1
    candidates: list[dict[str, Any]] = []
    for evaluation in plan.project_evaluations:
        source = sources.get(evaluation.project_name)
        if source is None:
            continue
        source = project_role_view(source, _role_evidence_family(plan.role_categories))
        coverage, covered, reasons = _project_requirement_coverage(evaluation.project_name, plan.requirement_evidence)
        coverage_score = min(100.0, 100.0 * coverage / required_total)
        role_evidence = evaluation.role_evidence_score
        quality = _project_quality(evaluation)
        project_type = _key(source.get("project_type"))
        if "laboratory practice" in project_type and quality < 55:
            continue
        # Requirements and role-specific evidence dominate. Technical quality
        # remains useful for tie-breaking, but complexity alone cannot outrank
        # a project that proves the job's systems context.
        score = coverage_score * .50 + role_evidence * .30 + quality * .20
        # For validation, operating physical systems provide a different kind
        # of evidence from pre-fabrication design files. Reward documented
        # acquisition/control, without pretending either is professional work.
        if _role_evidence_family(plan.role_categories) == "validation" and _key(source.get("status")) == "functional prototype":
            capabilities = _demonstrated_capabilities(source)
            if "physical sensing" in capabilities:
                score += 5
            elif {"real-time execution", "feedback control"} <= capabilities:
                score += 4
        # Judge demonstrated maturity, never candidate-maintained priority
        # labels or project names. Direct domain evidence can still make a
        # focused exercise useful (for example, image processing for vision).
        maturity_penalty = 0
        if any(term in project_type for term in ("focused technical exercise", "laboratory practice")):
            maturity_penalty += 6 if role_evidence >= 60 else 16
        if _key(source.get("status")) in {"in development", "planned", "concept"}:
            maturity_penalty += 14
        score = max(0.0, score - maturity_penalty)
        candidates.append({
            "name": evaluation.project_name,
            "score": score,
            "covered": covered,
            "technologies": {canonicalize_skill(item) for item in source.get("technologies", []) if _clean(item)},
            "capabilities": _demonstrated_capabilities(source),
            "repository": _clean(source.get("repository_url") or source.get("github_url")).rstrip("/").casefold(),
            "exercise": any(term in project_type for term in ("exercise", "practice")),
            "role_evidence": role_evidence,
            "reasons": [
                *reasons,
                *evaluation.role_evidence_notes,
                f"Requirement coverage {round(coverage_score):.0f}/100; role evidence {round(role_evidence):.0f}/100; technical quality {round(quality):.0f}/100.",
                *([f"Demonstrated maturity adjustment: -{maturity_penalty} points."] if maturity_penalty else []),
            ],
        })
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()
    all_candidates = list(candidates)
    family = _role_evidence_family(plan.role_categories)
    relevant_capabilities = {
        "robotics": {"feedback control", "real-time execution", "physical interfaces", "digital design", "multi-axis robotics", "immersive interaction", "remote integration", "physical sensing", "validation"},
        "embedded": {"feedback control", "real-time execution", "physical interfaces", "analog acquisition", "remote integration", "physical sensing", "validation"},
        "fpga": {"digital design", "physical interfaces", "validation"},
        "validation": {"digital design", "physical interfaces", "validation", "analog acquisition", "feedback control", "real-time execution", "physical sensing", "remote integration", "circuit design"},
        "vision": {"image processing", "physical sensing", "algorithms", "validation"},
        "software": {"backend services", "persistent data", "identity and security", "algorithms", "validation"},
        "security": {"backend services", "persistent data", "identity and security", "remote integration", "validation"},
    }.get(family, set().union(*(item["capabilities"] for item in candidates)))

    def marginal_value(item: dict[str, Any]) -> tuple[float, set[str], float]:
        prior_capabilities = set().union(*(prior["capabilities"] for prior in selected))
        novel = (item["capabilities"] - prior_capabilities) & relevant_capabilities
        new_requirements = item["covered"] - covered
        redundancy = 0.0
        for prior in selected:
            union = item["capabilities"] | prior["capabilities"]
            similarity = len(item["capabilities"] & prior["capabilities"]) / max(1, len(union))
            redundancy = max(redundancy, similarity * 14)
            if item["exercise"] and not prior["exercise"] and not new_requirements:
                redundancy = max(redundancy, 12)
            # A preliminary exercise must add a requested capability to earn
            # space beside the complete system from the same repository.
            if (item["exercise"] and not prior["exercise"] and item["repository"]
                    and item["repository"] == prior["repository"] and not new_requirements):
                redundancy = max(redundancy, 30)
        # Variety only helps when the added capability actually fits the role.
        # An unrelated web project must not win a research CV just by adding SQL.
        novelty_bonus = len(novel) * 4 if item["role_evidence"] >= 40 or item["covered"] else 0
        value = item["score"] + len(new_requirements) * coverage_diversity_bonus + novelty_bonus - redundancy
        return value, novel, redundancy
    # Embedded resumes should gain diversity from systems evidence, not select
    # an unrelated algorithm exercise just because it adds one generic keyword.
    coverage_diversity_bonus = 4 if _role_evidence_family(plan.role_categories) == "embedded" else 11
    while candidates and len(selected) < min(4, max(2, limit)):
        def adjusted(item: dict[str, Any]) -> tuple[float, float, str]:
            return (marginal_value(item)[0], item["score"], item["name"])

        best = max(candidates, key=adjusted)
        value, novel, redundancy = marginal_value(best)
        if len(selected) >= 2 and value < 20 and not (best["covered"] - covered):
            break
        best["reasons"].append(
            f"Portfolio review: adds {', '.join(sorted(novel)) or 'supporting evidence'}; redundancy adjustment -{redundancy:.1f}."
        )
        selected.append(best)
        covered.update(best["covered"])
        candidates.remove(best)
    selected.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    review = {
        "method": "job_evidence_and_portfolio_review_v1",
        "role_family": family or "general",
        "selected_projects": [item["name"] for item in selected],
        "rejected_projects": [
            {"name": item["name"], "reason": "Lower relevance or complementary value than the selected portfolio.",
             "base_score": round(item["score"], 2), "marginal_score": round(marginal_value(item)[0], 2)}
            for item in all_candidates if item not in selected
        ],
        "context_warning": (
            "Broad research opportunity: tailor the final CV to the chosen lab and research domain."
            if family == "research" else
            "Limited job requirements: this selection relies on the role domain; review it against the full posting."
            if not plan.required_skills and not plan.preferred_skills else ""
        ),
    }
    return (
        [item["name"] for item in selected],
        {item["name"]: round(float(item["score"]), 2) for item in selected},
        {item["name"]: item["reasons"] for item in selected},
        review,
    )


def _plan_skill_group(skill: str) -> str:
    if skill in {"Oscilloscope", "Multimeter", "Logic Analyzer"}:
        return "Lab & Test Equipment"
    if skill in {"PID Control", "UART", "SPI", "I2C", "Bluetooth Low Energy", "MQTT", "WebSocket", "Real-Time Telemetry"}:
        return "Control & Communication"
    if skill in {"KiCad", "PCB", "STM32F401"}:
        return "Embedded & Systems" if skill == "STM32F401" else "Hardware & Digital Design"
    return {
        "Languages": "Programming",
        "Embedded / Systems": "Embedded & Systems",
        "Hardware": "Hardware & Digital Design",
        "Backend / Web": "Software",
        "Development": "Software", "Tools": "Software",
        "Debug & Validation": "Software",
    }.get(skill_category(skill), "Software")


def _skill_categories_from_plan(ranked):
    # Keep even a single lab instrument in its own correctly named category.
    # Do not merge hardware instruments into an unrelated web/software row.
    by_category = {}
    for _score, skill in ranked:
        by_category.setdefault(_plan_skill_group(skill), []).append(skill)
    groups = [{"name": name, "items": list(dict.fromkeys(items))[:8]}
              for name, items in by_category.items()]
    if len(groups) == 1 and len(groups[0]["items"]) >= 4:
        items = groups[0]["items"]
        midpoint = len(items) // 2
        groups = [{"name": groups[0]["name"], "items": items[:midpoint]},
                  {"name": "Technical", "items": items[midpoint:]}]
    return [skill for group in groups for skill in group["items"]], groups


def _select_skills_from_plan(
    plan: TailoringPlan,
    profile: Any,
    selected_projects: list[str],
    project_scores: dict[str, float],
) -> tuple[list[str], list[dict[str, Any]], dict[str, list[CandidateEvidence]]]:
    registry = build_verified_skill_registry(profile)
    ranked: dict[str, float] = {}
    evidence_by_skill: dict[str, list[CandidateEvidence]] = {}

    def add(skill: str, score: float, evidence: list[CandidateEvidence]) -> None:
        canonical = canonicalize_skill(skill)
        if canonical not in registry:
            return
        ranked[canonical] = max(ranked.get(canonical, 0.0), score)
        if evidence:
            existing = evidence_by_skill.setdefault(canonical, [])
            for item in evidence:
                if item not in existing:
                    existing.append(item)

    for mapping in plan.requirement_evidence:
        if mapping.requirement.type != "technology" or mapping.match_state == SkillMatchState.NOT_FOUND:
            continue
        weight = mapping.requirement.importance_weight * MATCH_FACTORS[mapping.match_state]
        for item in mapping.matched_candidate_evidence:
            add(item.canonical_skill, weight + item.evidence_strength, [item])

    project_sources = _project_sources(profile)
    for name in selected_projects:
        source = project_sources.get(name, {})
        score = project_scores.get(name, 0.0)
        for raw_skill in source.get("technologies", []) or []:
            canonical = canonicalize_skill(raw_skill)
            matching_evidence = [
                item for mapping in plan.requirement_evidence
                for item in mapping.matched_candidate_evidence
                if item.source == EvidenceSource.PROJECT
                and item.source_name == name
                and item.canonical_skill == canonical
            ]
            add(canonical, 20 + score + (35 if matching_evidence else 0), matching_evidence)

    target_count = min(20 if _role_evidence_family(plan.role_categories) == "validation" else 14, len(registry))
    ordered = sorted(((score, skill) for skill, score in ranked.items()), key=lambda item: (-item[0], item[1].casefold()))
    # Only evidence from the selected portfolio can fill remaining ATS-readable
    # skill slots. No role-priority list is consulted here.
    if len(ordered) < min(8, target_count):
        for name in selected_projects:
            for raw_skill in project_sources.get(name, {}).get("technologies", []) or []:
                canonical = canonicalize_skill(raw_skill)
                if canonical in registry and canonical not in ranked:
                    ranked[canonical] = 10 + project_scores.get(name, 0.0)
        ordered = sorted(((score, skill) for skill, score in ranked.items()), key=lambda item: (-item[0], item[1].casefold()))
    # Cover the selected portfolio instead of filling every slot from the
    # highest-scoring project's technology list. Explicit job matches lead.
    shortlist: list[str] = []
    redundancy_groups = ({"FPGA", "FPGA Design"}, {"Digital Logic", "Digital Design"},
                         {"Debugging", "Software Debugging"}, {"Concurrent Programming", "Multithreaded Programming"})

    def include(skill: str) -> None:
        if skill not in ranked or skill in shortlist or len(shortlist) >= target_count:
            return
        if any(skill in group and any(existing in group for existing in shortlist) for group in redundancy_groups):
            return
        shortlist.append(skill)

    for _score, skill in ordered:
        if skill in evidence_by_skill:
            include(skill)
    project_skills = [
        list(dict.fromkeys(canonicalize_skill(item) for item in project_sources.get(name, {}).get("technologies", [])))
        for name in selected_projects
    ]
    for index in range(max((len(items) for items in project_skills), default=0)):
        for items in project_skills:
            if index < len(items):
                include(items[index])
    for _score, skill in ordered:
        include(skill)
    selected, categories = _skill_categories_from_plan([(ranked[skill], skill) for skill in shortlist])
    return selected, categories, evidence_by_skill


def _select_supporting_sources(
    plan: TailoringPlan,
    source: EvidenceSource,
    limit: int = 2,
) -> list[str]:
    selected: list[str] = []
    for mapping in plan.requirement_evidence:
        if mapping.match_state == SkillMatchState.NOT_FOUND:
            continue
        for evidence in mapping.matched_candidate_evidence:
            if evidence.source == source and evidence.source_name not in selected:
                selected.append(evidence.source_name)
                if len(selected) >= limit:
                    return selected
    return selected


def select_relevant_coursework(plan, profile, limit=5):
    family = _role_evidence_family(plan.role_categories)
    domains = {
        "validation": ("electronic", "electrical", "signal", "chip", "programmable logic"),
        "fpga": ("programmable logic", "chip", "digital", "electronic"),
        "embedded": ("chip", "electronic", "iot", "internet of things", "signal"),
        "robotics": ("control", "signal", "electronic", "chip"),
        "software": ("programming", "data structures", "algorithms", "python", "web data"),
        "research": ("control", "signal", "chip", "programming"),
    }.get(family, ())
    direct = _select_supporting_sources(plan, EvidenceSource.COURSEWORK, limit=limit)
    ranked = []
    for course in _value(profile, "coursework_json", []) or []:
        if not isinstance(course, dict):
            continue
        name = _clean(course.get("name"))
        score = 4 * (name in direct) + sum(term in _key(name) for term in domains)
        if score and name:
            ranked.append((score, name))
    return [name for score, name in sorted(ranked, key=lambda x: (-x[0], x[1]))[:limit]]


def _select_supporting_certifications(plan: TailoringPlan, limit: int = 2) -> list[str]:
    """Choose credentials by requirement coverage, not profile insertion order.

    A certificate appears only when its own verified evidence maps to the job.
    Importance, match quality, and evidence strength determine the ordering so
    a data-focused credential wins a data role without a title-based rule.
    """
    scores: dict[str, float] = {}
    for mapping in plan.requirement_evidence:
        if mapping.match_state == SkillMatchState.NOT_FOUND:
            continue
        contribution = mapping.requirement.importance_weight * MATCH_FACTORS[mapping.match_state]
        for evidence in mapping.matched_candidate_evidence:
            if evidence.source != EvidenceSource.CERTIFICATION:
                continue
            scores[evidence.source_name] = scores.get(evidence.source_name, 0.0) + (
                contribution * evidence.evidence_strength / 100
            )
    return [
        name for name, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit]
    ]


def decide_resume_content(
    plan: TailoringPlan,
    profile: Any,
    *,
    project_limit: int = 4,
) -> TailoringPlan:
    """Populate Phase 2 decisions using only evidence already contained in a plan."""
    _require_scoped_inputs(type("ScopedJob", (), {"owner_user_id": plan.owner_user_id})(), profile, plan.owner_user_id)
    projects, scores, reasons, review = _select_projects_from_plan(plan, profile, limit=project_limit)
    skills, categories, skill_evidence = _select_skills_from_plan(plan, profile, projects, scores)
    missing = [
        mapping.requirement.normalized_requirement
        for mapping in plan.requirement_evidence
        if mapping.requirement.type == "technology" and mapping.match_state == SkillMatchState.NOT_FOUND
    ]
    role = _primary_resume_role_category(plan)
    covered = [
        mapping.requirement.normalized_requirement
        for mapping in plan.requirement_evidence
        if mapping.requirement.type == "technology" and mapping.match_state != SkillMatchState.NOT_FOUND
    ]
    plan.resume_decisions = ResumeDecisions(
        status="PLANNED",
        selected_projects=projects,
        selected_skills=skills,
        selected_coursework=select_relevant_coursework(plan, profile),
        selected_certifications=_select_supporting_certifications(plan),
        selected_experience=_select_supporting_sources(plan, EvidenceSource.EXPERIENCE),
        primary_role_category=role,
        summary_direction=(
            f"Explain fit for {role} through {', '.join(projects[:2]) or 'documented projects'} "
            f"and evidenced {', '.join(skills[:4])}; foreground coverage of {', '.join(covered[:4]) or 'the role requirements'}."
        ),
        headline_direction="|".join([role, *skills[:2]]),
        missing_requirements=missing,
        selected_project_scores=scores,
        selected_project_reasons=reasons,
        editorial_review=review,
        selected_skill_evidence=skill_evidence,
        selected_skill_categories=categories,
    )
    return plan


def _primary_resume_role_category(plan: TailoringPlan) -> str:
    """Choose wording direction from the current job title, not incidental JD terms.

    A software posting can mention secure coding or security reviews without
    becoming a cybersecurity role. The full overlapping category list remains
    available to the evidence layer; only headline/summary wording uses this
    title-led primary role.
    """
    title = _key(plan.job_title)
    title_signals = (
        ("Electrical / Validation", ("electrical validation", "electrical testing", "electrical test")),
        ("Security Consulting", ("security consultant", "security consulting", "security advisory")),
        ("Security Engineering", ("security engineering", "security engineer", "application security", "network security")),
        ("Cybersecurity", ("cybersecurity", "cyber security")),
        ("System Security", ("system security", "systems security")),
        ("FPGA / Digital Design", ("fpga", "verilog", "rtl", "digital design")),
        ("Embedded / Firmware", (
            "embedded", "firmware", "microcontroller", "microcontrollers", "mcu",
            "freertos", "rtos",
        )),
        ("Hardware / Systems", ("hardware", "electromechanical", "board design", "systems integration")),
        ("Robotics / Controls", ("robotics", "robot", "controls", "control systems")),
        ("Software Engineering", ("software", "software engineer", "sde", "developer")),
    )
    for category, signals in title_signals:
        if category in plan.role_categories and any(signal in title for signal in signals):
            return category
    return plan.role_categories[0] if plan.role_categories else "Engineering"


def is_electrical_validation_role(job: Any) -> bool:
    title = _key(_value(job, "title"))
    return any(term in title for term in ("electrical validation", "electrical testing", "electrical test")) and not any(_contains_term(title, term) for term in ("fpga", "rtl", "verilog"))


def _role_categories(job: Any) -> list[str]:
    # `area` is structured source metadata and must participate in role
    # classification. Manually added jobs often have terse titles (e.g. MCU
    # NPI) while their normalized area carries the decisive embedded signal.
    text = " ".join(_clean(_value(job, field)) for field in (
        "title", "area", "description", "requirements", "preferred_qualifications",
    ))
    normalized = _key(text)
    # A consulting-security title describes overlapping security work. Keep
    # software as a secondary context when present, but never let it erase the
    # security role that drives the resume direction.
    if "security consultant" in normalized or "security consulting" in normalized:
        security = [
            "Security Consulting", "Security Engineering", "Cybersecurity", "System Security",
        ]
        non_security = [
            category for category, terms in ROLE_CATEGORY_SIGNALS.items()
            if category not in security and any(_contains_term(text, term) for term in terms)
        ]
        return [*security, *non_security]
    categories = [
        category for category, terms in ROLE_CATEGORY_SIGNALS.items()
        if any(_contains_term(text, term) for term in terms)
    ]
    if is_electrical_validation_role(job):
        return ["Electrical / Validation", *(category for category in categories if category != "Electrical / Validation")]
    if _value(job, "resume_target") == "robotics_research" and not categories:
        categories = ["Research / Research Engineering"]
    security_categories = [
        category for category in ("Security Engineering", "Cybersecurity", "System Security")
        if category in categories
    ]
    non_security = [category for category in categories if category not in security_categories]
    ordered = [*security_categories, *non_security]
    title = _clean(_value(job, "title"))
    for category in (
        "Security Consulting", "Security Engineering", "Cybersecurity", "System Security",
        "FPGA / Digital Design", "Embedded / Firmware", "Computer Vision / Image Processing",
        "Robotics / Controls", "Software Engineering", "Research / Research Engineering",
    ):
        if category in ordered and any(_contains_term(title, term) for term in ROLE_CATEGORY_SIGNALS[category]):
            return [category, *(item for item in ordered if item != category)]
    fallback_order = (
        "Security Consulting", "Security Engineering", "Cybersecurity", "System Security",
        "FPGA / Digital Design", "Embedded / Firmware", "Computer Vision / Image Processing",
        "Robotics / Controls", "Software Engineering", "Research / Research Engineering",
    )
    ordered.sort(key=lambda item: fallback_order.index(item) if item in fallback_order else len(fallback_order))
    return ordered or ["General Engineering"]


def build_tailoring_plan(job: Any, profile: Any, *, owner_user_id: str) -> TailoringPlan:
    """Create an evidence-only plan for one user-owned job and resume profile."""
    _require_scoped_inputs(job, profile, owner_user_id)
    requirements, responsibilities = _extract_requirements(job, profile)
    evidence = _evidence_from_profile(profile)
    mappings = [_match_requirement(requirement, evidence) for requirement in requirements]
    missing = [
        mapping.requirement.normalized_requirement
        for mapping in mappings
        if mapping.requirement.type == "technology" and mapping.match_state == SkillMatchState.NOT_FOUND
    ]
    role_categories = _role_categories(job)
    return TailoringPlan(
        owner_user_id=owner_user_id,
        job_id=_value(job, "id") or None,
        job_content_hash=job_content_hash(job),
        job_title=_clean(_value(job, "title")), company=_clean(_value(job, "company")),
        role_categories=role_categories,
        role_category_codes=[ROLE_CATEGORY_CODES.get(category, _key(category).upper().replace(" ", "_")) for category in role_categories],
        normalized_requirements=requirements,
        required_skills=[
            item.normalized_requirement for item in requirements
            if item.type == "technology" and item.importance == RequirementImportance.REQUIRED
        ],
        preferred_skills=[
            item.normalized_requirement for item in requirements
            if item.type == "technology" and item.importance == RequirementImportance.PREFERRED
        ],
        responsibilities=responsibilities,
        requirement_evidence=mappings,
        project_evaluations=_project_evaluations(profile, mappings, role_categories),
        resume_decisions=ResumeDecisions(missing_requirements=missing),
    )
