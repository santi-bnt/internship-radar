from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from app.services.dedupe import value
from app.services.normalization import clean_text, normalized_token


COMPLETED_REQUIRED = "COMPLETED_REQUIRED"
IN_PROGRESS_ALLOWED = "IN_PROGRESS_ALLOWED"
COMPLETED_OR_IN_PROGRESS = "COMPLETED_OR_IN_PROGRESS"
UNKNOWN = "UNKNOWN"

EDUCATION_BLOCKER_REASON = (
    "Position requires a completed Bachelor's degree or higher. Candidate is "
    "currently pursuing the degree and has not yet graduated."
)

DEGREE_LEVEL_ORDER = {"BACHELORS": 1, "MASTERS": 2, "PHD": 3}
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

FIELD_ALIASES = {
    "ROBOTICS": ("robotics", "robotic engineering"),
    "MECHATRONICS": ("mechatronics", "mechatronic engineering"),
    "EMBEDDED_SYSTEMS": ("embedded systems", "embedded engineering"),
    "ELECTRICAL_ENGINEERING": ("electrical engineering", "electrical engineer"),
    "COMPUTER_ENGINEERING": ("computer engineering", "computer engineer"),
    "COMPUTER_SCIENCE": ("computer science",),
    "SOFTWARE_ENGINEERING": ("software engineering",),
    "ELECTRONICS": ("electronics", "electronic engineering"),
    "NANOTECHNOLOGY": ("nanotechnology",),
    "MECHANICAL_ENGINEERING": ("mechanical engineering",),
    "ACCOUNTING": ("accounting",),
    "FINANCE": ("finance",),
    "BUSINESS": ("business administration", "business"),
    "MARKETING": ("marketing",),
    "BIOLOGY": ("biology", "biological sciences"),
    "CHEMISTRY": ("chemistry",),
    "NURSING": ("nursing",),
    "LAW": ("law degree", "juris doctor"),
}

CURRENT_STUDENT_PATTERNS = (
    r"\bcurrently pursuing\b",
    r"\bcurrently enrolled\b",
    r"\benrolled in (?:a |an )?.{0,35}\bprogram\b",
    r"\bworking toward(?:s)?\b",
    r"\bstudent pursuing\b",
    r"\bmust remain enrolled\b",
    r"\breturn to (?:the )?university\b",
    r"\bexpected graduation\b",
    r"\bbachelor s candidate\b",
    r"\bdegree in progress\b",
)

COMPLETED_PATTERNS = (
    r"\bmust have (?:a |an )?(?:bachelor|master|phd|doctorate|degree)\b",
    r"\b(?:bachelor|master|phd|doctorate|degree).{0,35}\brequired\b",
    r"\brequires? (?:a |an )?(?:completed )?(?:bachelor|master|phd|doctorate|degree)\b",
    r"\bminimum (?:of )?(?:a |an )?(?:bachelor|master|phd|doctorate|degree)\b",
    r"\bmust hold (?:a |an )?(?:bachelor|master|phd|doctorate|degree)\b",
    r"\bcompleted (?:a |an )?(?:bachelor|master|phd|doctorate|degree)\b",
    r"\b(?:bachelor|master|phd|doctorate) s? degree or higher\b",
    r"\bbs ms phd required\b",
    r"\bdegree must be completed (?:prior to|before)\b",
    r"\b(?:minimum|required) qualifications?.{0,80}\b(?:bachelor|master|phd|doctorate)\b",
)

GENERIC_DEGREE_PATTERN = re.compile(
    r"\b(bachelor|bachelors|bachelor s|bs|b s|master|masters|master s|ms|m s|"
    r"phd|ph d|doctorate|degree)\b"
)


@dataclass(frozen=True)
class DegreeRequirements:
    minimum_degree_level: str = UNKNOWN
    accepted_degree_levels: tuple[str, ...] = ()
    degree_completion_required: str = UNKNOWN
    currently_enrolled_allowed: str = UNKNOWN
    graduation_before_start_required: str = UNKNOWN
    accepted_degree_fields: tuple[str, ...] = ()
    student_status_required: str = UNKNOWN
    required_graduation_start: date | None = None
    required_graduation_end: date | None = None
    degree_requirement_evidence: str = ""
    field_requirement: str = UNKNOWN
    graduation_window_required: bool = False
    has_degree_language: bool = False

    def persisted(self) -> dict[str, Any]:
        data = asdict(self)
        data["accepted_degree_levels"] = list(self.accepted_degree_levels)
        data["accepted_degree_fields"] = list(self.accepted_degree_fields)
        for transient in (
            "field_requirement",
            "graduation_window_required",
            "has_degree_language",
        ):
            data.pop(transient)
        return data


@dataclass(frozen=True)
class EducationDecision:
    state: str
    score: float
    degree_level_match: str
    degree_field_match: str
    degree_completion_match: str
    graduation_window_match: str
    student_status_match: str
    reason: str
    blockers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    positives: tuple[str, ...] = ()


def _posting_text(job: Any) -> tuple[str, str, str]:
    title = clean_text(value(job, "title", "") or "")
    required = clean_text(
        " ".join(
            part
            for part in (
                value(job, "description", "") or "",
                value(job, "requirements", "") or "",
            )
            if part
        )
    )
    preferred = clean_text(value(job, "preferred_qualifications", "") or "")
    return normalized_token(title), normalized_token(required), normalized_token(preferred)


def _education_context(raw: str) -> str:
    """Keep degree clauses without treating nearby skill lists as degree fields."""
    cleaned = clean_text(raw)
    segments = re.split(r"(?:[.!?;]|\r?\n|\s+[|]\s+)", cleaned)
    selected = []
    for segment in segments:
        normalized = normalized_token(segment)
        if (
            GENERIC_DEGREE_PATTERN.search(normalized)
            or re.search(r"\b(?:field of study|academic discipline|education in)\b", normalized)
            or any(re.search(pattern, normalized) for pattern in CURRENT_STUDENT_PATTERNS)
        ):
            selected.append(normalized)
    return " ".join(selected)


def _degree_levels(text: str) -> tuple[str, ...]:
    levels: set[str] = set()
    if re.search(r"\b(?:bachelor|bachelors|bachelor s|bs|b s)\b", text):
        levels.add("BACHELORS")
    if re.search(r"\b(?:master|masters|master s|ms|m s)\b", text):
        levels.add("MASTERS")
    if re.search(r"\b(?:phd|ph d|doctorate|doctoral)\b", text):
        levels.add("PHD")
    return tuple(sorted(levels, key=lambda item: DEGREE_LEVEL_ORDER[item]))


def _degree_fields(text: str) -> tuple[str, ...]:
    fields = {
        canonical
        for canonical, aliases in FIELD_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases)
    }
    if re.search(r"\b(?:engineering|technical) (?:discipline|field)\b", text):
        fields.add("ENGINEERING")
    return tuple(sorted(fields))


def _is_preferred_context(text: str) -> bool:
    return bool(re.search(r"\b(?:preferred|ideally|nice to have|a plus|bonus)\b", text))


def _has_related_field_language(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:related|similar|relevant|closely related|equivalent) "
            r"(?:engineering )?(?:field|discipline|degree|area)\b",
            text,
        )
    )


def _month_date(month_name: str, year: str, *, end: bool) -> date:
    month = MONTHS[month_name.lower()]
    day = calendar.monthrange(int(year), month)[1] if end else 1
    return date(int(year), month, day)


def _graduation_window(text: str) -> tuple[date | None, date | None, bool]:
    month_names = "|".join(MONTHS)
    between = re.search(
        rf"\b(?:graduat(?:e|ion|ing)|degree completion).{{0,25}}\bbetween\s+"
        rf"({month_names})\s+(20\d{{2}})\s+(?:and|to|through|-)\s+"
        rf"({month_names})\s+(20\d{{2}})\b",
        text,
    )
    if between:
        required = not _is_preferred_context(text[max(0, between.start() - 80):between.end() + 40])
        return (
            _month_date(between.group(1), between.group(2), end=False),
            _month_date(between.group(3), between.group(4), end=True),
            required,
        )

    by = re.search(
        rf"\b(?:must|required to|should)\s+(?:have )?graduat(?:e|ed)\s+by\s+"
        rf"({month_names})\s+(20\d{{2}})\b",
        text,
    )
    if not by:
        by = re.search(
            rf"\bgraduation date.{{0,20}}\b(?:by|no later than)\s+"
            rf"({month_names})\s+(20\d{{2}})\b",
            text,
        )
    if by:
        required = not _is_preferred_context(text[max(0, by.start() - 80):by.end() + 40])
        return None, _month_date(by.group(1), by.group(2), end=True), required
    return None, None, False


def extract_degree_requirements(job: Any) -> DegreeRequirements:
    title, required, preferred = _posting_text(job)
    combined = " ".join(part for part in (title, required, preferred) if part)
    required_levels = _degree_levels(required)
    preferred_levels = _degree_levels(preferred)
    accepted_levels = required_levels or preferred_levels
    minimum_level = accepted_levels[0] if accepted_levels else UNKNOWN

    current_student_allowed = any(re.search(pattern, combined) for pattern in CURRENT_STUDENT_PATTERNS)
    completed_or_progress = bool(
        re.search(
            r"\b(?:completed|hold(?:s|ing)?).{0,45}\b(?:or|and or)\b.{0,45}"
            r"\b(?:currently pursuing|enrolled|in progress)\b",
            combined,
        )
    )
    completion_evidence = any(re.search(pattern, required) for pattern in COMPLETED_PATTERNS)
    # Current-student language is explicit permission and overrides generic degree
    # wording, including in internship/co-op postings.
    if completed_or_progress:
        completion = COMPLETED_OR_IN_PROGRESS
    elif current_student_allowed:
        completion = IN_PROGRESS_ALLOWED
    elif completion_evidence:
        completion = COMPLETED_REQUIRED
    else:
        completion = UNKNOWN

    # Technology names such as "embedded systems" are often skills, not
    # fields of study. Only classify them as education fields when the same
    # section actually contains degree/education language.
    required_context = _education_context(
        " ".join(
            part
            for part in (
                value(job, "description", "") or "",
                value(job, "requirements", "") or "",
            )
            if part
        )
    )
    preferred_context = _education_context(value(job, "preferred_qualifications", "") or "")
    required_fields = _degree_fields(required_context)
    preferred_fields = _degree_fields(preferred_context)
    accepted_fields = required_fields or preferred_fields
    if required_fields:
        field_requirement = "REQUIRED" if (
            completion_evidence
            or re.search(r"\b(?:required|must|minimum qualification|qualifications?)\b", required)
        ) else UNKNOWN
    elif preferred_fields:
        field_requirement = "PREFERRED"
    else:
        field_requirement = UNKNOWN

    graduation_start, graduation_end, graduation_required = _graduation_window(combined)
    graduation_before_start = (
        "YES"
        if re.search(
            r"\b(?:degree|graduation).{0,35}\b(?:completed|graduate).{0,25}"
            r"\b(?:before|prior to) (?:employment|start|start date)\b|"
            r"\b(?:completed|graduate).{0,25}\b(?:before|prior to) (?:employment|start|start date)\b",
            required,
        )
        else UNKNOWN
    )
    student_required = (
        "REQUIRED"
        if any(re.search(pattern, required) for pattern in CURRENT_STUDENT_PATTERNS)
        else UNKNOWN
    )

    evidence_parts: list[str] = []
    for raw in (
        value(job, "requirements", "") or "",
        value(job, "description", "") or "",
        value(job, "preferred_qualifications", "") or "",
    ):
        cleaned = clean_text(raw)
        if GENERIC_DEGREE_PATTERN.search(normalized_token(cleaned)):
            evidence_parts.append(cleaned[:500])
    evidence = " | ".join(dict.fromkeys(evidence_parts))[:1500]

    return DegreeRequirements(
        minimum_degree_level=minimum_level,
        accepted_degree_levels=accepted_levels,
        degree_completion_required=completion,
        currently_enrolled_allowed="YES" if current_student_allowed else UNKNOWN,
        graduation_before_start_required=graduation_before_start,
        accepted_degree_fields=accepted_fields,
        student_status_required=student_required,
        required_graduation_start=graduation_start,
        required_graduation_end=graduation_end,
        degree_requirement_evidence=evidence,
        field_requirement=field_requirement,
        graduation_window_required=graduation_required,
        has_degree_language=bool(GENERIC_DEGREE_PATTERN.search(combined)),
    )


def apply_job_education_requirements(job: Any) -> DegreeRequirements:
    requirements = extract_degree_requirements(job)
    for key, item in requirements.persisted().items():
        setattr(job, key, item)
    return requirements


def _as_date(raw: Any, fallback_year: Any = None) -> date | None:
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str) and raw:
        try:
            if re.fullmatch(r"\d{4}-\d{2}", raw):
                year, month = raw.split("-")
                return _month_date(calendar.month_name[int(month)].lower(), year, end=True)
            return date.fromisoformat(raw[:10])
        except (ValueError, IndexError):
            return None
    if fallback_year:
        try:
            return date(int(fallback_year), 6, 30)
        except (TypeError, ValueError):
            return None
    return None


def _field_match(requirements: DegreeRequirements, profile: Any) -> str:
    if not requirements.accepted_degree_fields:
        return UNKNOWN
    user_field = normalized_token(value(profile, "degree_field", "") or value(profile, "degree", ""))
    accepted = set(requirements.accepted_degree_fields)
    if "ROBOTICS" in accepted and "robot" in user_field:
        return "MATCH"
    if "MECHATRONICS" in accepted and ("robot" in user_field or "mechatronic" in user_field):
        return "MATCH"
    if "ENGINEERING" in accepted and "engineering" in user_field:
        return "MATCH"

    job_text = normalized_token(requirements.degree_requirement_evidence)
    related_allowed = _has_related_field_language(job_text)
    if related_allowed and accepted.intersection(
        {
            "EMBEDDED_SYSTEMS",
            "ELECTRICAL_ENGINEERING",
            "COMPUTER_ENGINEERING",
            "ELECTRONICS",
            "MECHANICAL_ENGINEERING",
            "ENGINEERING",
            "ROBOTICS",
            "MECHATRONICS",
        }
    ):
        return "MATCH"
    return "NO_MATCH"


def evaluate_degree_eligibility(
    requirements: DegreeRequirements,
    profile: Any,
) -> EducationDecision:
    status = str(value(profile, "degree_status", "IN_PROGRESS") or UNKNOWN).upper()
    current_level = str(value(profile, "degree_level_current", "BACHELORS") or UNKNOWN).upper()
    expected = _as_date(
        value(profile, "expected_graduation_date") or value(profile, "graduation_date"),
        value(profile, "graduation_year"),
    )
    blockers: list[str] = []
    risks: list[str] = []
    positives: list[str] = []

    if requirements.accepted_degree_levels:
        level_match = "MATCH" if current_level in requirements.accepted_degree_levels else "NO_MATCH"
        if level_match == "NO_MATCH":
            levels = "/".join(level.title() for level in requirements.accepted_degree_levels)
            blockers.append(
                f"Position is limited to {levels} candidates; candidate is pursuing a Bachelor's degree."
            )
        else:
            positives.append("The candidate's current degree level is accepted.")
    else:
        level_match = UNKNOWN

    field_match = _field_match(requirements, profile)
    if field_match == "MATCH":
        positives.append("The degree field matches the role's accepted field of study.")
    elif field_match == "NO_MATCH" and requirements.field_requirement == "REQUIRED":
        blockers.append("Candidate's degree field is outside the position's mandatory field-of-study list.")
    elif field_match == "NO_MATCH":
        risks.append("The listed field of study does not clearly match, but the wording is not mandatory.")

    completion = requirements.degree_completion_required
    if completion == COMPLETED_REQUIRED:
        if status == "COMPLETED":
            completion_match = "MATCH"
            positives.append("The completed-degree requirement is met.")
        elif status == "EXPECTED_BEFORE_START" and requirements.graduation_before_start_required == "YES":
            completion_match = "MATCH"
            positives.append("The degree is expected to be completed before the position starts.")
        elif status == "IN_PROGRESS":
            completion_match = "NO_MATCH"
            blockers.append(EDUCATION_BLOCKER_REASON)
        else:
            completion_match = UNKNOWN
            risks.append("A completed degree is required, but completion status cannot be confirmed.")
    elif completion in {IN_PROGRESS_ALLOWED, COMPLETED_OR_IN_PROGRESS}:
        completion_match = "MATCH" if status in {"IN_PROGRESS", "COMPLETED", "EXPECTED_BEFORE_START"} else UNKNOWN
        if completion_match == "MATCH":
            positives.append("The posting explicitly accepts a degree in progress.")
    else:
        completion_match = UNKNOWN
        if requirements.has_degree_language:
            risks.append("Degree completion wording is ambiguous and requires review.")

    if requirements.required_graduation_start or requirements.required_graduation_end:
        if not expected:
            graduation_match = UNKNOWN
            risks.append("The posting has a graduation window, but the candidate date is unknown.")
        else:
            after_start = not requirements.required_graduation_start or expected >= requirements.required_graduation_start
            before_end = not requirements.required_graduation_end or expected <= requirements.required_graduation_end
            graduation_match = "MATCH" if after_start and before_end else "NO_MATCH"
            if graduation_match == "NO_MATCH" and requirements.graduation_window_required:
                blockers.append(
                    "Candidate's expected graduation in June 2028 is outside the mandatory graduation window."
                )
            elif graduation_match == "NO_MATCH":
                risks.append("The expected graduation date is outside a preferred graduation window.")
            else:
                positives.append("The expected graduation date is inside the required window.")
    elif requirements.graduation_before_start_required == "YES":
        graduation_match = "MATCH" if status in {"COMPLETED", "EXPECTED_BEFORE_START"} else "NO_MATCH"
        if graduation_match == "NO_MATCH":
            blockers.append("The degree must be completed before the position starts.")
    else:
        graduation_match = UNKNOWN

    if requirements.student_status_required == "REQUIRED":
        student_match = "MATCH" if status in {"IN_PROGRESS", "EXPECTED_BEFORE_START"} else "NO_MATCH"
        if student_match == "NO_MATCH":
            blockers.append("The position requires current student enrollment.")
        else:
            positives.append("The current-student requirement is met.")
    else:
        student_match = UNKNOWN

    blockers = list(dict.fromkeys(blockers))
    risks = list(dict.fromkeys(risks))
    positives = list(dict.fromkeys(positives))
    if blockers:
        state = "NOT_ELIGIBLE"
        score = 0.0
        reason = blockers[0]
    elif requirements.has_degree_language and completion == UNKNOWN:
        state = "UNKNOWN"
        score = 55.0
        reason = "The posting mentions a degree but does not clearly state whether it must already be completed."
    elif risks:
        state = "UNKNOWN"
        score = 55.0
        reason = risks[0]
    else:
        state = "ELIGIBLE"
        score = 95.0
        reason = positives[0] if positives else "No mandatory education conflict was found."

    return EducationDecision(
        state=state,
        score=score,
        degree_level_match=level_match,
        degree_field_match=field_match,
        degree_completion_match=completion_match,
        graduation_window_match=graduation_match,
        student_status_match=student_match,
        reason=reason,
        blockers=tuple(blockers),
        risks=tuple(risks),
        positives=tuple(positives),
    )
