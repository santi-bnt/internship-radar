from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.dedupe import value
from app.services.classification import detect_recycled_posting
from app.services.eligibility import (
    EligibilityDecision,
    evaluate_work_eligibility,
    extract_job_eligibility_signals,
    remote_eligibility_bonus,
)
from app.services.education_eligibility import (
    evaluate_degree_eligibility,
    extract_degree_requirements,
)
from app.services.special_program_eligibility import (
    evaluate_special_program_eligibility,
    extract_special_program_signals,
)
from app.services.normalization import clean_text, normalized_token
from app.services.resume_skills import build_verified_skill_registry, canonicalize_skill, _occurrences


SKILL_ALIASES = {
    "c": (" c ", "embedded c", "c programming"),
    "c++": ("c++", "cpp"),
    "python": ("python",),
    "java": ("java",),
    "javascript": ("javascript", "typescript", "node.js", "react"),
    "linux": ("linux", "unix"),
    "git": ("git", "version control"),
    "embedded systems": ("embedded", "microcontroller", "mcu", "bare metal"),
    "firmware": ("firmware", "rtos", "device driver"),
    "fpga": ("fpga", "field programmable"),
    "verilog": ("verilog", "systemverilog", "rtl"),
    "digital design": ("digital design", "asic", "logic design"),
    "robotics": ("robotics", "robot", "ros"),
    "controls": ("controls", "control systems", "pid"),
    "computer vision": ("computer vision", "opencv", "image processing"),
    "electronics": ("electronics", "pcb", "oscilloscope", "schematic"),
    "testing": ("testing", "validation", "verification", "test automation"),
    "sql": ("sql", "database"),
    "cloud": ("aws", "azure", "gcp", "cloud"),
}

ROLE_GROUPS = {
    "Software / SDE": ("software", "sde", "backend", "full stack", "developer", "programming"),
    "Firmware / Embedded": ("firmware", "embedded", "microcontroller", "rtos", "device driver"),
    "FPGA / RTL / Digital Design": ("fpga", "rtl", "verilog", "asic", "digital design"),
    "Hardware Test / Validation": ("hardware test", "validation", "verification", "electronics test"),
    "Robotics / Controls": ("robotics", "controls", "autonomy", "mechatronics", "computer vision"),
}

HARD_BLOCKERS = (
    (r"\b(u\s*s|united states)\s+citizen(ship)?\s+(is\s+)?required\b|\bmust be (a )?u\s*s citizen\b", "U.S. citizenship is explicitly required."),
    (r"\b(active|current|ability to obtain)\s+(security )?clearance\b|\bsecurity clearance (is )?required\b", "A security clearance is required."),
    (r"\b(canadian citizen|canada citizen|permanent resident of canada|canadian permanent resident)\b.*\brequired\b", "Canadian citizenship or permanent residence is required."),
    (r"\b(intern conversion only|returning interns? only|previous internship with us required)\b", "The role is restricted to previous interns or conversion candidates."),
)

UNIVERSITY_BLOCKER_REASON = (
    "Requires enrollment at a university in a specific country or institution. "
    "The user studies at Tecnológico de Monterrey in Mexico."
)

# These patterns are deliberately limited to explicit country, institution, or
# approved-program restrictions. Generic accredited/recognized-university
# language must remain eligible.
UNIVERSITY_RESTRICTION_PATTERNS = (
    r"\b(?:enrolled|studying|attend|attending)\b.{0,45}\b(?:u s|us|united states|canadian|canada)\b.{0,25}\b(?:university|universities|college|institution)\b",
    r"\b(?:university|universities|college|institution)\b.{0,30}\b(?:located|based)\b.{0,15}\b(?:u s|us|united states|canada)\b",
    r"\b(?:university|universities|college|institution)\s+in\s+(?:the\s+)?(?:u s|us|united states|canada)\b",
    r"\b(?:open|available)\s+only\s+to\s+students\s+studying\s+in\s+(?:the\s+)?(?:u s|us|united states|canada)\b",
    r"\b(?:u s|us|united states|canadian|canada)\s+(?:based\s+)?(?:university|universities|college|institution)\b",
    r"\b(?:uiuc|georgia tech|mit)\s+students?\s+only\b",
    r"\bstudents?\s+from\s+(?:participating|approved)\s+(?:u s|us|united states|canadian|canada)?\s*(?:university|universities|institutions?)\s+only\b",
    r"\b(?:company s|company|employer s|employer)\s+approved\s+co\s*op\s+(?:university\s+)?program\b",
    r"\bmust\s+be\s+enrolled\s+in\s+(?:the\s+)?(?:company s|company|employer s|employer)\s+approved\s+co\s*op\b",
)

SENIOR_PATTERN = re.compile(r"\b(senior|staff|principal|manager|lead|director)\b", re.IGNORECASE)
INTERNSHIP_PATTERN = re.compile(r"\b(intern(ship)?|co-?op|student)\b", re.IGNORECASE)


@dataclass
class AnalysisResult:
    technical_score: float
    academic_score: float
    eligibility_score: float
    level_score: float
    logistics_score: float
    freshness_score: float
    overall_score: float
    effective_score: float
    remote_eligibility_bonus: float
    degree_level_match: str
    degree_field_match: str
    degree_completion_match: str
    graduation_window_match: str
    student_status_match: str
    education_eligibility_status: str
    education_eligibility_reason: str
    special_program_eligibility_status: str
    special_program_eligibility_reason: str
    recommendation: str
    eligibility_status: str
    recommended_resume_type: str
    matched_skills: list[str]
    missing_required_skills: list[str]
    positive_reasons: list[str]
    risk_flags: list[str]
    blocker_reasons: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _combine_gate_states(*states: str) -> str:
    order = {
        "ELIGIBLE": 0,
        "UNKNOWN": 1,
        "LIKELY_INELIGIBLE": 2,
        "NOT_ELIGIBLE": 3,
    }
    return max(states, key=lambda state: order.get(state, 1))


def _profile_skills(profile: Any) -> set[str]:
    return set(build_verified_skill_registry(profile))


def _has_profile_skill(skill: str, aliases: tuple[str, ...], skills: set[str]) -> bool:
    return canonicalize_skill(skill).casefold() in {item.casefold() for item in skills}


def _skill_matches(job: Any, profile: Any) -> tuple[list[str], list[str], list[str], float]:
    required = value(job, "requirements", "") or ""
    preferred = value(job, "preferred_qualifications", "") or ""
    body = (
        " ".join(
            [
                value(job, "title", "") or "",
                value(job, "description", "") or "",
                value(job, "requirements", "") or "",
                value(job, "preferred_qualifications", "") or "",
            ]
        )
    )
    profile_skills = _profile_skills(profile)
    matched: list[str] = []
    missing_required: list[str] = []
    missing_preferred: list[str] = []
    points = 18.0

    for skill, aliases in SKILL_ALIASES.items():
        appears = _occurrences(skill, body) > 0
        if not appears:
            continue
        has_skill = _has_profile_skill(skill, aliases, profile_skills)
        is_required = _occurrences(skill, required) > 0
        is_preferred = _occurrences(skill, preferred) > 0
        if has_skill:
            matched.append(skill)
            points += 11 if is_required else 7 if is_preferred else 6
        elif is_required:
            missing_required.append(skill)
            points -= 9
        elif is_preferred:
            missing_preferred.append(skill)
            points -= 2

    title_and_body = normalized_token(f"{value(job, 'title', '')} {value(job, 'description', '')}")
    if any(keyword in title_and_body for terms in ROLE_GROUPS.values() for keyword in terms):
        points += 12
    if INTERNSHIP_PATTERN.search(value(job, "title", "")):
        points += 7
    return sorted(set(matched)), sorted(set(missing_required)), sorted(set(missing_preferred)), max(0, min(100, points))


def recommend_resume(job: Any) -> str:
    text = normalized_token(f"{value(job, 'title', '')} {value(job, 'description', '')}")
    for resume_type, terms in ROLE_GROUPS.items():
        if any(term in text for term in terms):
            return resume_type
    return "General Engineering"


def university_eligibility(text: str) -> tuple[str, str | None]:
    """Evaluate university restrictions independently from work authorization."""
    normalized = normalized_token(text)
    if any(re.search(pattern, normalized) for pattern in UNIVERSITY_RESTRICTION_PATTERNS):
        return "Not Eligible", UNIVERSITY_BLOCKER_REASON
    return "Eligible", None


def _freshness(job: Any) -> float:
    now = datetime.now(timezone.utc)
    expires_at = value(job, "expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            return 0

    posted_at = value(job, "official_posted_at") or value(job, "source_posted_at") or value(job, "posted_at")
    if not posted_at:
        score = 60
    else:
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        if posted_at:
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            days = max(0, (now - posted_at).days)
            if days <= 7:
                score = 100
            elif days <= 21:
                score = 85
            elif days <= 45:
                score = 65
            elif days <= 90:
                score = 40
            else:
                score = 20
        else:
            score = 60

    first_seen = value(job, "first_seen_at")
    if isinstance(first_seen, str):
        try:
            first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        except ValueError:
            first_seen = None
    if isinstance(first_seen, datetime):
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if now - first_seen <= timedelta(days=7):
            score = max(score, 75)

    last_verified = value(job, "last_verified_at")
    if isinstance(last_verified, str):
        try:
            last_verified = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
        except ValueError:
            last_verified = None
    if isinstance(last_verified, datetime):
        if last_verified.tzinfo is None:
            last_verified = last_verified.replace(tzinfo=timezone.utc)
        if value(job, "official_status") == "open" and now - last_verified <= timedelta(days=1):
            score = min(100, score + 10)

    recycled, _ = detect_recycled_posting(job, now)
    if recycled or bool(value(job, "recycled_posting", False)):
        score -= 40
    if value(job, "verification_status") in {"unverified", "verification_failed"}:
        score -= 15
    return max(0, min(100, score))


def analyze_job(job: Any, profile: Any, verified_profile: Any | None = None) -> AnalysisResult:
    title = clean_text(value(job, "title", ""))
    country = clean_text(value(job, "country", ""))
    location = clean_text(value(job, "location", ""))
    remote_type = clean_text(value(job, "remote_type", ""))
    duration = clean_text(value(job, "duration", ""))
    full_text = normalized_token(
        " ".join(
            [
                title,
                value(job, "description", "") or "",
                value(job, "requirements", "") or "",
                value(job, "preferred_qualifications", "") or "",
            ]
        )
    )
    signals = extract_job_eligibility_signals(job)
    eligibility_decision = evaluate_work_eligibility(signals, profile)
    degree_requirements = extract_degree_requirements(job)
    education_decision = evaluate_degree_eligibility(degree_requirements, profile)
    special_program_signals = extract_special_program_signals(job)
    special_program_decision = evaluate_special_program_eligibility(
        special_program_signals,
        profile,
    )
    matched, missing_required, missing_preferred, technical = _skill_matches(job, verified_profile or profile)
    blockers = [reason for pattern, reason in HARD_BLOCKERS if re.search(pattern, full_text, re.IGNORECASE)]
    university_status, university_blocker = university_eligibility(full_text)
    if university_blocker:
        blockers.append(university_blocker)
    risks: list[str] = []
    positives: list[str] = []
    official_status = value(job, "official_status", "unknown") or "unknown"
    verification_status = value(job, "verification_status", "unverified") or "unverified"
    if (
        value(job, "verification_method", "") == "community_discovery"
        and verification_status in {"unverified", "verification_failed"}
    ):
        eligibility_decision = EligibilityDecision(
            state="UNKNOWN",
            score=55.0,
            reasons=[],
            risks=[
                "Community discovery metadata is not authoritative; official employer verification is required."
            ],
        )

    gate_state = _combine_gate_states(
        eligibility_decision.state,
        education_decision.state,
        special_program_decision.state,
    )

    if eligibility_decision.state == "NOT_ELIGIBLE":
        blockers.extend(eligibility_decision.reasons)
    elif eligibility_decision.state == "LIKELY_INELIGIBLE":
        risks.extend(eligibility_decision.reasons)
    else:
        positives.extend(eligibility_decision.reasons)
    risks.extend(eligibility_decision.risks)
    blockers.extend(education_decision.blockers)
    risks.extend(education_decision.risks)
    positives.extend(education_decision.positives)
    blockers.extend(special_program_decision.blockers)
    risks.extend(special_program_decision.risks)
    positives.extend(special_program_decision.positives)

    is_senior = bool(SENIOR_PATTERN.search(title))
    is_internship = bool(INTERNSHIP_PATTERN.search(title)) or "internship" in normalized_token(
        value(job, "employment_type", "")
    )
    level_score = 100 if is_internship and not is_senior else 20 if is_senior else 55
    if is_senior:
        risks.append("The title indicates a senior, lead, staff, principal, or management level.")
    elif is_internship:
        positives.append("The role level is aligned with an internship or co-op search.")

    academic_score = education_decision.score
    if "new grad" in full_text and "full time" in full_text:
        blockers.append("This is an incompatible new-grad full-time role, not an internship.")
    if "previous professional experience" in full_text and re.search(r"\b([3-9]|\d{2,})\+?\s+years\b", full_text):
        blockers.append("The role requires too much mandatory professional experience.")

    country_text = normalized_token(f"{country} {location}")
    is_us = any(term in country_text for term in ("united states", "usa", "u s", "california", "texas", "washington"))
    is_canada = any(term in country_text for term in ("canada", "ontario", "toronto", "vancouver", "waterloo"))
    is_mexico = "mexico" in country_text
    is_remote = "remote" in normalized_token(f"{remote_type} {location}")

    eligibility_score = min(
        eligibility_decision.score,
        education_decision.score,
        special_program_decision.score,
    )
    if "export control" in full_text or "itar" in full_text:
        risks.append("Export-control language may restrict eligibility and needs manual review.")
        eligibility_score -= 25
    if re.search(r"\b(8|12|16)[ -]month\b", normalized_token(duration + " " + full_text)):
        risks.append("The co-op duration may conflict with the candidate's academic calendar.")
        eligibility_score -= 18
    if (
        ("formal co op program" in full_text or "registered co op" in full_text)
        and university_status == "Eligible"
    ):
        risks.append("Formal co-op enrollment may be required.")
        eligibility_score -= 15
    if blockers and gate_state != "LIKELY_INELIGIBLE":
        eligibility_score = 0

    if signals.physical_work_country_required == "Mexico":
        logistics_score = 100
        positives.append("The location is in the highest-priority market: Mexico.")
    elif is_remote:
        logistics_score = 100 if signals.can_work_from_mexico == "YES" else 55
        if signals.can_work_from_mexico == "YES":
            positives.append("The role explicitly allows remote work from Mexico.")
        elif signals.can_work_from_mexico == "UNKNOWN":
            risks.append("Remote location restrictions are unclear; work from Mexico is not confirmed.")
        else:
            risks.append("The remote-work geography does not include Mexico.")
    elif is_us:
        logistics_score = 60
    elif is_canada:
        logistics_score = 52
        risks.append("Canadian work permit or sponsorship is not confirmed for this role.")
    else:
        logistics_score = 62
    if is_canada and signals.can_work_from_mexico != "YES" and not any(
        "Canadian work permit" in risk for risk in risks
    ):
        risks.append("Canadian work permit or sponsorship is not confirmed for this role.")

    freshness_score = _freshness(job)
    recycled, recycled_reason = detect_recycled_posting(job)
    if recycled:
        risks.append(recycled_reason or "The posting may have been recycled.")
    if freshness_score >= 85:
        if official_status == "open" and verification_status == "verified":
            positives.append("Verified recently on the official company site.")
        else:
            positives.append("The posting was discovered recently.")
    elif freshness_score <= 40:
        risks.append("The posting is old and may no longer be actively reviewed.")
    if official_status == "open" and verification_status == "verified":
        positives.append("Official application is still accepting submissions.")
    elif verification_status in {"unverified", "verification_failed"}:
        risks.append("External listing could not be confirmed on an official company page.")

    if matched:
        positives.append(f"Matches {len(matched)} relevant skill{'s' if len(matched) != 1 else ''}: {', '.join(matched[:6])}.")
    if missing_required:
        risks.append(f"Missing required signals: {', '.join(missing_required)}.")
    if missing_preferred:
        risks.append(f"Preferred-only gaps carry a small penalty: {', '.join(missing_preferred)}.")

    company_priority_bonus = float(value(job, "company_priority_bonus", 0) or 0)
    if bool(value(job, "is_target_company", False)) and company_priority_bonus:
        positives.append(
            f"Target-company and official-source signals add a moderate {company_priority_bonus:.0f}-point priority bonus."
        )
    base_score = round(
        technical * 0.45
        + academic_score * 0.20
        + eligibility_score * 0.15
        + level_score * 0.10
        + logistics_score * 0.05
        + freshness_score * 0.05
        + min(6.0, company_priority_bonus * 0.25),
        1,
    )
    remote_bonus = remote_eligibility_bonus(
        signals,
        gate_state,
        bool(value(job, "relocation_required", False)),
    )
    overall = min(100.0, round(base_score + remote_bonus, 1))
    if blockers or gate_state == "NOT_ELIGIBLE":
        overall = min(5.0, overall)
    elif gate_state == "LIKELY_INELIGIBLE":
        overall = min(25.0, overall)
    elif gate_state == "UNKNOWN":
        overall = min(79.0, overall)

    expires_at = value(job, "expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    deadline_passed = bool(expires_at and expires_at < datetime.now(timezone.utc))

    if not bool(value(job, "is_active", True)) or official_status in {"closed", "expired", "unavailable"} or deadline_passed:
        recommendation = "Closed"
        eligibility_status = gate_state
    elif blockers:
        recommendation = "Not Eligible"
        eligibility_status = "NOT_ELIGIBLE"
    elif gate_state == "NOT_ELIGIBLE":
        recommendation = "Not Eligible"
        eligibility_status = "NOT_ELIGIBLE"
    elif gate_state == "LIKELY_INELIGIBLE":
        recommendation = "Review"
        eligibility_status = "LIKELY_INELIGIBLE"
    elif gate_state == "UNKNOWN":
        # An unresolved sponsorship/work-authorisation fact on a US role is a
        # specific application blocker: it requires verification before Apply
        # Today. Other unknowns (for example community-source metadata) keep
        # the established Review outcome.
        unresolved_us_authorization = (
            eligibility_decision.state == "UNKNOWN"
            and bool(value(job, "job_requires_work_in_us", False))
            and signals.sponsorship_status == "UNKNOWN"
        )
        recommendation = "Needs Verification" if unresolved_us_authorization else "Review"
        eligibility_status = "UNKNOWN"
    elif official_status != "open" or verification_status != "verified":
        recommendation = "Needs Verification"
        eligibility_status = gate_state
    elif is_senior:
        recommendation = "Low Match"
        eligibility_status = gate_state
    elif technical < 35:
        recommendation = "Low Match"
        eligibility_status = gate_state
    elif risks:
        recommendation = "Review"
        eligibility_status = gate_state
    elif overall >= 70 and freshness_score >= 50:
        recommendation = "Apply Today"
        eligibility_status = gate_state
    else:
        recommendation = "Review"
        eligibility_status = gate_state

    explanation_parts = [
        f"Technical {round(technical)} based on required, preferred, and contextual skill matches.",
        f"Eligibility {gate_state} ({round(eligibility_score)}) after work-authorization, education, and special-program hard gates.",
        f"Education {education_decision.state}: {education_decision.reason}",
        f"Special program {special_program_decision.state}: {special_program_decision.reason}",
        f"Sponsorship {signals.sponsorship_status}; remote scope {signals.remote_scope}; can work from Mexico {signals.can_work_from_mexico}.",
        f"Official status {official_status}; verification {verification_status}.",
        f"Company priority bonus {company_priority_bonus:.0f}, capped to a moderate scoring effect.",
        "Base score uses the configured 45/20/15/10/5/5 weighting.",
        f"Effective score {overall} after the {remote_bonus:.0f}-point eligible-remote/logistics bonus.",
    ]
    return AnalysisResult(
        technical_score=round(technical, 1),
        academic_score=round(academic_score, 1),
        eligibility_score=round(eligibility_score, 1),
        level_score=round(level_score, 1),
        logistics_score=round(logistics_score, 1),
        freshness_score=round(freshness_score, 1),
        overall_score=overall,
        effective_score=overall,
        remote_eligibility_bonus=remote_bonus,
        degree_level_match=education_decision.degree_level_match,
        degree_field_match=education_decision.degree_field_match,
        degree_completion_match=education_decision.degree_completion_match,
        graduation_window_match=education_decision.graduation_window_match,
        student_status_match=education_decision.student_status_match,
        education_eligibility_status=education_decision.state,
        education_eligibility_reason=education_decision.reason,
        special_program_eligibility_status=special_program_decision.state,
        special_program_eligibility_reason=special_program_decision.reason,
        recommendation=recommendation,
        eligibility_status=eligibility_status,
        recommended_resume_type=recommend_resume(job),
        matched_skills=matched,
        missing_required_skills=missing_required,
        positive_reasons=positives,
        risk_flags=risks,
        blocker_reasons=sorted(set(blockers)),
        explanation=" ".join(explanation_parts),
    )
