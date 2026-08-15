from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.services.dedupe import value
from app.services.normalization import clean_text, normalized_token


NONE = "NONE"
VETERANS = "VETERANS"
ACTIVE_DUTY_MILITARY = "ACTIVE_DUTY_MILITARY"
TRANSITIONING_SERVICE_MEMBERS = "TRANSITIONING_SERVICE_MEMBERS"
MILITARY_SPOUSES = "MILITARY_SPOUSES"
PEOPLE_WITH_DISABILITIES = "PEOPLE_WITH_DISABILITIES"
RETURN_TO_WORK_PROGRAM = "RETURN_TO_WORK_PROGRAM"
FORMER_EMPLOYEES = "FORMER_EMPLOYEES"
SPECIFIC_ACADEMIC_COHORT = "SPECIFIC_ACADEMIC_COHORT"
OTHER_RESTRICTED_GROUP = "OTHER_RESTRICTED_GROUP"

SPECIAL_PROGRAM_TYPES = {
    VETERANS,
    ACTIVE_DUTY_MILITARY,
    TRANSITIONING_SERVICE_MEMBERS,
    MILITARY_SPOUSES,
    PEOPLE_WITH_DISABILITIES,
    RETURN_TO_WORK_PROGRAM,
    FORMER_EMPLOYEES,
    SPECIFIC_ACADEMIC_COHORT,
    OTHER_RESTRICTED_GROUP,
}

GROUP_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (MILITARY_SPOUSES, "MILITARY_SPOUSE", r"\b(?:active duty )?military spouses?\b"),
    (
        TRANSITIONING_SERVICE_MEMBERS,
        "TRANSITIONING_SERVICE_MEMBER",
        r"\btransitioning (?:service members?|military personnel|veterans?)\b",
    ),
    (
        ACTIVE_DUTY_MILITARY,
        "ACTIVE_DUTY",
        r"\b(?:active duty|currently serving) (?:service members?|military(?: personnel)?)\b",
    ),
    (VETERANS, "VETERAN", r"\b(?:u s )?veterans?\b"),
    (
        PEOPLE_WITH_DISABILITIES,
        "DISABILITY",
        r"\b(?:(?:people|person|persons|individuals|students|applicants|candidates) with (?:a )?"
        r"disabilit(?:y|ies)|disabled (?:students|applicants|candidates)|neurodivergent "
        r"(?:students|applicants|candidates))\b",
    ),
    (
        RETURN_TO_WORK_PROGRAM,
        "RETURNING_PROFESSIONAL",
        r"\b(?:returnship|return to work program|returning professionals?|career re entry)\b",
    ),
    (
        FORMER_EMPLOYEES,
        "FORMER_EMPLOYEE",
        r"\b(?:former employees?|company alumni|previous employees?)\b",
    ),
    (
        SPECIFIC_ACADEMIC_COHORT,
        "HIGH_SCHOOL_STUDENT",
        r"\b(?:high school students?|secondary school students?)\b",
    ),
    (
        SPECIFIC_ACADEMIC_COHORT,
        "GRADUATE_STUDENT",
        r"\b(?:graduate students?|master s or phd students?|doctoral students?)\b",
    ),
    (
        SPECIFIC_ACADEMIC_COHORT,
        "POSTDOCTORAL",
        r"\b(?:postdoctoral|post doctorate|postdoc) (?:students?|fellows?|researchers?|candidates?)\b",
    ),
    (
        OTHER_RESTRICTED_GROUP,
        "WOMEN",
        r"\b(?:women|female students?|women in (?:technology|engineering|stem))\b",
    ),
    (
        OTHER_RESTRICTED_GROUP,
        "INDIGENOUS",
        r"\b(?:indigenous|first nations|native american|aboriginal) "
        r"(?:students?|applicants?|candidates?|people|peoples)\b",
    ),
    (
        OTHER_RESTRICTED_GROUP,
        "APPRENTICESHIP_COHORT",
        r"\b(?:approved|registered|participating|designated) (?:company )?"
        r"apprenticeship (?:program|cohort|participants?)\b",
    ),
)

TITLE_PROGRAM_PATTERNS: tuple[tuple[str, str], ...] = (
    (VETERANS, r"\b(?:oracle )?veteran(?:s)? (?:internship|talent|fellowship) program\b"),
    (ACTIVE_DUTY_MILITARY, r"\bmilitary (?:internship|fellowship|talent) program\b"),
    (ACTIVE_DUTY_MILITARY, r"\bskillbridge\b"),
    (
        PEOPLE_WITH_DISABILITIES,
        r"\b(?:disability|neurodiversity) (?:internship|hiring|talent) program\b",
    ),
    (RETURN_TO_WORK_PROGRAM, r"\b(?:returnship|return to work|career re entry)\b"),
)

EEO_PATTERNS = (
    r"\bequal opportunity (?:employer|employment)\b",
    r"\b(?:all )?qualified applicants.{0,120}\breceive consideration\b",
    r"\b(?:we )?(?:do not|does not) discriminate\b",
    r"\bwithout regard to\b",
    r"\bprotected veteran status\b",
    r"\bencouraged to apply\b",
    r"\bdiversity and inclusion\b",
)
PREFERENCE_PATTERNS = (
    r"\bpreferred\b",
    r"\bpreference (?:is )?(?:given|provided)\b",
    r"\bplus\b",
)
OPEN_TO_ALL_PATTERNS = (
    r"\bopen to all (?:applicants|candidates|students)\b",
    r"\bnot limited to\b",
    r"\b(?:veteran|military|disability) status (?:is )?not required\b",
)
RESTRICTION_CUES = (
    r"\bonly\b",
    r"\bmust (?:be|have|identify|qualify|meet)\b",
    r"\brequired\b",
    r"\brestricted to\b",
    r"\blimited to\b",
    r"\bexclusively for\b",
    r"\bintended for\b",
    r"\bdesigned for\b",
    r"\bspecifically for\b",
    r"\b(?:internship|program|fellowship|role) (?:is )?(?:open )?for\b",
    r"\bavailable to\b",
    r"\beligible (?:applicants|candidates|participants|students)\b",
    r"\bto be eligible\b",
    r"\bprogram eligibility\b",
)


@dataclass(frozen=True)
class SpecialProgramSignals:
    special_program_type: str = NONE
    special_program_required: bool = False
    special_program_evidence: str = ""
    required_groups: tuple[str, ...] = ()
    title_signal: bool = False
    preference_only: bool = False
    explicitly_open_to_all: bool = False

    def persisted(self) -> dict[str, Any]:
        data = asdict(self)
        for transient in (
            "required_groups",
            "title_signal",
            "preference_only",
            "explicitly_open_to_all",
        ):
            data.pop(transient)
        return data


@dataclass(frozen=True)
class SpecialProgramDecision:
    state: str
    score: float
    reason: str
    blockers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    positives: tuple[str, ...] = ()


def _segments(raw: str) -> list[str]:
    cleaned = re.sub(r"\bU[.]S[.]", "US", clean_text(raw), flags=re.IGNORECASE)
    return [
        normalized_token(segment)
        for segment in re.split(r"(?:[.!?;]|\r?\n|[|])", cleaned)
        if normalized_token(segment)
    ]


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _groups_in(text: str) -> list[tuple[str, str]]:
    return [
        (program_type, group)
        for program_type, group, pattern in GROUP_PATTERNS
        if re.search(pattern, text)
    ]


def extract_special_program_signals(job: Any) -> SpecialProgramSignals:
    clean_title = clean_text(value(job, "title", "") or "")
    title = normalized_token(clean_title)
    requirements_raw = value(job, "requirements", "") or ""
    description_raw = value(job, "description", "") or ""
    preferred_raw = value(job, "preferred_qualifications", "") or ""

    title_program_types = [
        program_type
        for program_type, pattern in TITLE_PROGRAM_PATTERNS
        if re.search(pattern, title)
    ]
    title_groups = _groups_in(title)
    title_signal = bool(title_program_types or title_groups)

    required_groups: list[str] = []
    observed_types: list[str] = [*title_program_types, *(item[0] for item in title_groups)]
    evidence: list[str] = [f"Title: {clean_title}"] if title_signal else []
    preference_only = False
    explicitly_open_to_all = False

    sources = (
        ("requirements", requirements_raw),
        ("description", description_raw),
        ("preferred", preferred_raw),
    )
    for source_name, raw in sources:
        for segment in _segments(raw):
            groups = _groups_in(segment)
            if not groups:
                continue
            observed_types.extend(program_type for program_type, _ in groups)
            if _matches_any(segment, OPEN_TO_ALL_PATTERNS):
                explicitly_open_to_all = True
                evidence.append(segment)
                continue
            if _matches_any(segment, EEO_PATTERNS):
                continue
            if source_name == "preferred" or _matches_any(segment, PREFERENCE_PATTERNS):
                preference_only = True
                evidence.append(segment)
                continue
            has_restriction_cue = _matches_any(segment, RESTRICTION_CUES)
            if has_restriction_cue:
                required_groups.extend(group for _, group in groups)
                evidence.append(segment)

    if title_groups and _matches_any(title, RESTRICTION_CUES):
        required_groups.extend(group for _, group in title_groups)
        evidence.append(title)

    program_type = next(
        (candidate for candidate in observed_types if candidate in SPECIAL_PROGRAM_TYPES),
        NONE,
    )
    unique_groups = tuple(dict.fromkeys(required_groups))
    unique_evidence = " | ".join(dict.fromkeys(evidence))[:1500]
    return SpecialProgramSignals(
        special_program_type=program_type,
        special_program_required=bool(unique_groups) and not explicitly_open_to_all,
        special_program_evidence=unique_evidence,
        required_groups=unique_groups,
        title_signal=title_signal,
        preference_only=preference_only and not bool(unique_groups),
        explicitly_open_to_all=explicitly_open_to_all,
    )


def apply_job_special_program_signals(job: Any) -> SpecialProgramSignals:
    signals = extract_special_program_signals(job)
    for key, item in signals.persisted().items():
        setattr(job, key, item)
    return signals


def _profile_group_match(group: str, profile: Any) -> bool | None:
    veteran_status = str(value(profile, "veteran_status", "UNKNOWN") or "UNKNOWN").upper()
    military_status = str(value(profile, "military_status", "UNKNOWN") or "UNKNOWN").upper()
    disability_status = str(
        value(profile, "disability_status", "UNKNOWN") or "UNKNOWN"
    ).upper()

    if group == "VETERAN":
        if veteran_status == "UNKNOWN":
            return None
        return veteran_status in {"VETERAN", "US_VETERAN"}
    if group == "ACTIVE_DUTY":
        if (
            military_status == "UNKNOWN"
            and value(profile, "current_service_member", None) is None
        ):
            return None
        return (
            bool(value(profile, "current_service_member", False))
            or military_status == "ACTIVE_DUTY"
        )
    if group == "TRANSITIONING_SERVICE_MEMBER":
        if military_status == "UNKNOWN":
            return None
        return military_status in {"TRANSITIONING", "TRANSITIONING_SERVICE_MEMBER"}
    if group == "MILITARY_SPOUSE":
        spouse = value(profile, "military_spouse", None)
        return None if spouse is None else bool(spouse)
    if group == "DISABILITY":
        if disability_status == "UNKNOWN":
            return None
        return disability_status in {"HAS_DISABILITY", "DISABILITY", "PERSON_WITH_DISABILITY"}

    degree_level = str(value(profile, "degree_level_current", "UNKNOWN") or "UNKNOWN").upper()
    degree_status = str(value(profile, "degree_status", "UNKNOWN") or "UNKNOWN").upper()
    if group == "HIGH_SCHOOL_STUDENT":
        if degree_level == "UNKNOWN" or degree_status == "UNKNOWN":
            return None
        return degree_level == "HIGH_SCHOOL" and degree_status == "IN_PROGRESS"
    if group == "GRADUATE_STUDENT":
        if degree_level == "UNKNOWN" or degree_status == "UNKNOWN":
            return None
        return degree_level in {"MASTERS", "PHD"} and degree_status == "IN_PROGRESS"
    if group == "POSTDOCTORAL":
        if degree_level == "UNKNOWN" or degree_status == "UNKNOWN":
            return None
        return degree_level == "POSTDOCTORAL" and degree_status == "IN_PROGRESS"

    # The profile intentionally does not infer returnship, former-employee,
    # gender, Indigenous, or other protected-group membership.
    return None


def evaluate_special_program_eligibility(
    signals: SpecialProgramSignals,
    profile: Any,
) -> SpecialProgramDecision:
    if signals.explicitly_open_to_all:
        return SpecialProgramDecision(
            state="ELIGIBLE",
            score=95.0,
            reason="The posting explicitly states that the program is open to all applicants.",
        )
    if signals.preference_only:
        return SpecialProgramDecision(
            state="ELIGIBLE",
            score=95.0,
            reason="The posting expresses a group preference, not a mandatory membership requirement.",
        )
    if signals.title_signal and not signals.special_program_required:
        reason = (
            "The title suggests a restricted special program, but the official description does not "
            "confirm its membership requirement."
        )
        return SpecialProgramDecision(
            state="UNKNOWN",
            score=55.0,
            reason=reason,
            risks=(reason,),
        )
    if not signals.special_program_required:
        return SpecialProgramDecision(
            state="ELIGIBLE",
            score=95.0,
            reason="No mandatory special-program membership requirement was found.",
        )

    matches = [_profile_group_match(group, profile) for group in signals.required_groups]
    if any(match is True for match in matches):
        return SpecialProgramDecision(
            state="ELIGIBLE",
            score=95.0,
            reason="The explicit profile satisfies at least one accepted special-program group.",
            positives=("The special-program membership requirement is explicitly satisfied.",),
        )
    if any(match is None for match in matches):
        reason = (
            "The posting has a restricted special-program requirement, but the profile does not "
            "contain an explicit status for every accepted group."
        )
        return SpecialProgramDecision(
            state="UNKNOWN",
            score=55.0,
            reason=reason,
            risks=(reason,),
        )

    labels = ", ".join(group.replace("_", " ").title() for group in signals.required_groups)
    blocker = (
        f"Special program requires membership in: {labels}. "
        "The candidate profile explicitly does not meet this requirement."
    )
    return SpecialProgramDecision(
        state="NOT_ELIGIBLE",
        score=0.0,
        reason=blocker,
        blockers=(blocker,),
    )
