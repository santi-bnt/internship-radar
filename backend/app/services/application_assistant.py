from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ApplicationProfile,
    GeneratedPortfolio,
    GeneratedResume,
    Job,
    ResumeProfile,
    UserProfile,
)
from app.services.company_portal_registry import detect_portal_from_url
from app.services.application_selection import build_application_selection
from app.services.language_evidence import resume_language_lines
from app.services.resume_skills import build_verified_skill_registry


FIELD_POLICIES = (
    "AUTO_FILL",
    "AUTO_FILL_REVIEW_REQUIRED",
    "REVIEW_RECOMMENDED",
    "CONFIRM_REQUIRED",
    "MANUAL_ONLY",
)
AUTO_FILL_REVIEW_QUESTION_KEYS = frozenset(
    {
        "US_WORK_AUTHORIZATION",
        "US_SPONSORSHIP_REQUIRED",
        "MEXICO_WORK_AUTHORIZATION",
        "WORK_AUTHORIZATION_CURRENT_COUNTRY",
        "SPONSORSHIP_CURRENT_COUNTRY",
        "CITIZENSHIP",
        "FULL_TIME_SUMMER_AVAILABILITY",
        "SPRING_SUMMER_COMBINED_AVAILABILITY",
        "JOB_DISCOVERY_SOURCE",
    }
)
SENSITIVE_QUESTION_KEYS = frozenset(
    {
        "FORMER_INTEL_EMPLOYEE",
        "FORMER_GE_EMPLOYEE",
        "FORMER_EY_EMPLOYEE",
        "EY_SAN_JOSE_FAMILY",
        "NONCOMPETE_RESTRICTION",
        "SECONDARY_EMPLOYMENT",
        "US_WORK_AUTHORIZATION",
        "US_SPONSORSHIP_REQUIRED",
        "MEXICO_WORK_AUTHORIZATION",
        "WORK_AUTHORIZATION_CURRENT_COUNTRY",
        "SPONSORSHIP_CURRENT_COUNTRY",
        "CITIZENSHIP",
        "GOVERNMENT_EMPLOYEE",
        "FAMILY_GOVERNMENT_EMPLOYEE",
        "VETERAN_STATUS",
        "DISABILITY_STATUS",
        "INTEL_IP_INTEREST",
        "INTELLECTUAL_PROPERTY",
        "EXPORT_CONTROL",
        "RELOCATION",
        "SALARY_EXPECTATION",
        "CRIMINAL_LEGAL_DISCLOSURE",
        "NDA_NONCOMPETE",
        "CONFLICT_OF_INTEREST",
    }
)

QUESTION_ALIASES: dict[str, tuple[str, ...]] = {
    "US_WORK_AUTHORIZATION": (
        "authorized to work in the us",
        "authorized to work in the u s",
        "authorized to work in the united states",
        "legally authorized to work in the united states",
    ),
    "US_SPONSORSHIP_REQUIRED": (
        "require sponsorship",
        "need sponsorship",
        "employment visa sponsorship",
        "immigration sponsorship",
    ),
    "MEXICO_WORK_AUTHORIZATION": (
        "authorized to work in mexico",
        "legally authorized to work in mexico",
    ),
    "WORK_AUTHORIZATION_CURRENT_COUNTRY": (
        "authorized to work in the country where this job is located",
        "authorized to work in this country",
    ),
    "SPONSORSHIP_CURRENT_COUNTRY": (
        "require sponsorship to work in mexico",
        "sponsorship to work in mexico",
        "require sponsorship to work in this country",
        "sponsorship in the country in which this position is based",
    ),
    "CITIZENSHIP": ("citizenship", "citizen of which country", "country of citizenship"),
    "VETERAN_STATUS": ("veteran status", "protected veteran", "military veteran"),
    "DISABILITY_STATUS": ("disability status", "have a disability", "self identify disability"),
    "GOVERNMENT_EMPLOYEE": ("government employee", "employed by a government"),
    "FAMILY_GOVERNMENT_EMPLOYEE": ("family member government", "relative government employee"),
    "SECONDARY_EMPLOYMENT": ("secondary employment", "outside employment", "other employment"),
    "NONCOMPETE_RESTRICTION": ("non compete", "noncompete", "restrictive covenant"),
    "NDA_NONCOMPETE": ("non disclosure agreement", "nda", "non compete agreement"),
    "EXPORT_CONTROL": ("export control", "export authorization", "itar", "ear regulation"),
    "RELOCATION": ("willing to relocate", "relocation"),
    "SALARY_EXPECTATION": ("salary expectation", "expected salary", "desired compensation"),
    "CRIMINAL_LEGAL_DISCLOSURE": ("criminal conviction", "criminal record", "legal disclosure"),
    "FORMER_INTEL_EMPLOYEE": ("former intel employee", "previously employed by intel", "worked for intel"),
    "FORMER_GE_EMPLOYEE": ("former ge employee", "previously employed by ge", "worked for ge"),
    "FORMER_EY_EMPLOYEE": ("former ey employee", "previously employed by ey"),
    "EY_SAN_JOSE_FAMILY": ("ey san jose family", "relative at ey san jose"),
    "INTEL_IP_INTEREST": ("intel intellectual property", "interest in intel ip", "intellectual property interest"),
    "INTELLECTUAL_PROPERTY": ("intellectual property ownership", "own intellectual property", "intellectual property disclosure"),
    "CONFLICT_OF_INTEREST": ("conflict of interest", "potential conflict", "personal or financial conflict"),
    "FULL_TIME_SUMMER_AVAILABILITY": (
        "available for a full time onsite internship this summer",
        "available for full time summer internship",
        "work full time during the summer",
        "available may june through august september",
    ),
    "SPRING_SUMMER_COMBINED_AVAILABILITY": (
        "interested and available for a combined spring and summer internship",
        "combined spring and summer internship",
        "available january to august or september",
    ),
    "JOB_DISCOVERY_SOURCE": (
        "how you heard about zipline and this job",
        "how did you hear about us",
        "how did you hear about this job",
        "application source",
    ),
}


def normalize_question_text(value: str) -> str:
    normalized = value.casefold().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def classify_question(question: str) -> dict[str, Any]:
    normalized = normalize_question_text(question)
    if not normalized:
        return {"question_key": "UNKNOWN", "confidence": 0.0, "policy": "MANUAL_ONLY"}
    best_key = "UNKNOWN"
    best_score = 0.0
    for key, aliases in QUESTION_ALIASES.items():
        for alias in aliases:
            if normalized == alias:
                score = 1.0
            elif alias in normalized:
                score = min(0.98, 0.76 + len(alias) / max(len(normalized), 1) * 0.22)
            else:
                alias_words = set(alias.split())
                words = set(normalized.split())
                score = len(alias_words & words) / max(len(alias_words | words), 1)
            if score > best_score:
                best_key, best_score = key, score
    if best_score < 0.72:
        return {"question_key": "UNKNOWN", "confidence": round(best_score, 3), "policy": "MANUAL_ONLY"}
    return {
        "question_key": best_key,
        "confidence": round(best_score, 3),
        "policy": (
            "AUTO_FILL_REVIEW_REQUIRED"
            if best_key in AUTO_FILL_REVIEW_QUESTION_KEYS
            else "CONFIRM_REQUIRED"
            if best_key in SENSITIVE_QUESTION_KEYS
            else "MANUAL_ONLY"
        ),
    }


def detect_portal(application_url: str, company: str = "") -> dict[str, Any]:
    return detect_portal_from_url(application_url, company)


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def get_or_create_application_profile(db: Session, owner_user_id: str) -> ApplicationProfile:
    existing = db.scalar(
        select(ApplicationProfile).where(ApplicationProfile.owner_user_id == owner_user_id)
    )
    if existing:
        return existing
    candidate = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    resume = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == owner_user_id))
    education = (resume.education_json or [{}])[0] if resume and resume.education_json else {}
    location_parts = [part.strip() for part in (resume.location if resume else "").split(",") if part.strip()]
    expected = None
    if candidate:
        expected = candidate.expected_graduation_date or candidate.graduation_date
    profile = ApplicationProfile(
        owner_user_id=owner_user_id,
        full_name=(resume.full_name if resume else "") or (candidate.full_name if candidate else ""),
        professional_email=resume.email if resume else "",
        phone=resume.phone if resume else "",
        city=location_parts[0] if location_parts else "",
        state=location_parts[1] if len(location_parts) > 2 else "",
        country=(location_parts[-1] if len(location_parts) > 1 else "Mexico") or "Mexico",
        university=_first_text(education, "institution", "university") or (candidate.university if candidate else ""),
        degree=_first_text(education, "degree") or (candidate.degree if candidate else ""),
        field_of_study=(candidate.degree_field if candidate else "") or _first_text(education, "field", "field_of_study"),
        gpa=candidate.gpa if candidate else None,
        gpa_scale=candidate.gpa_scale if candidate else None,
        expected_graduation_date=expected,
        languages_json=resume_language_lines(resume) if resume else [],
        linkedin_url=resume.linkedin_url if resume else "",
        github_url=resume.github_url if resume else "",
        skills_json=list(
            (resume.skills_json if resume and resume.skills_json else None)
            or (candidate.skills if candidate else [])
        ),
        projects_json=list(
            (resume.projects_json if resume and resume.projects_json else None)
            or (candidate.projects if candidate else [])
        ),
        work_experience_json=list(resume.experience_json or []) if resume else [],
        application_preferences_confirmed_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.flush()
    return profile


def profile_snapshot(
    profile: ApplicationProfile,
    candidate: UserProfile | None = None,
) -> dict[str, Any]:
    current_location = ", ".join(
        part for part in (profile.city, profile.state, profile.country) if part
    )
    return {
        "contact": {
            "full_name": profile.full_name,
            "professional_email": profile.professional_email,
            "phone": profile.phone,
            "address_line1": profile.address_line1,
            "address_line2": profile.address_line2,
            "city": profile.city,
            "state": profile.state,
            "postal_code": profile.postal_code,
            "country": profile.country,
            "current_location": current_location,
        },
        "education": {
            "university": profile.university,
            "degree": profile.degree,
            "field_of_study": profile.field_of_study,
            "gpa": profile.gpa,
            "gpa_scale": profile.gpa_scale,
            "start_date": profile.education_start_date.isoformat() if profile.education_start_date else None,
            "expected_graduation_date": profile.expected_graduation_date.isoformat() if profile.expected_graduation_date else None,
        },
        "languages": list(profile.languages_json or []),
        "links": {"linkedin": profile.linkedin_url, "github": profile.github_url},
        "verified_skills": list(build_verified_skill_registry(profile)),
        "verified_projects": list(profile.projects_json or []),
        "verified_work_experience": list(profile.work_experience_json or []),
        "academic_project_workaround_allowed": profile.academic_project_workaround_allowed,
        "work_authorization": {
            "citizenship_country": candidate.citizenship_country if candidate else profile.country,
            "work_authorized_countries": list(candidate.work_authorized_countries or []) if candidate else [profile.country],
            "us_work_authorized": bool(candidate.us_work_authorized) if candidate else False,
            "requires_us_employment_sponsorship": bool(candidate.requires_us_employment_sponsorship) if candidate else True,
        },
        "application_preferences": {
            "job_discovery_source": profile.job_discovery_source,
            "full_time_summer_availability": profile.full_time_summer_availability,
            "spring_summer_combined_availability": profile.spring_summer_combined_availability,
            "confirmed_at": (
                profile.application_preferences_confirmed_at.isoformat()
                if profile.application_preferences_confirmed_at
                else None
            ),
            "answer_source": "USER_CONFIRMED",
        },
    }


def select_role_specific_projects(resume: GeneratedResume, profile: ApplicationProfile) -> list[dict[str, Any]]:
    tailored = resume.tailored_content_json or {}
    selected = tailored.get("projects") if isinstance(tailored, dict) else []
    verified_by_name = {
        normalize_question_text(str(item.get("name", ""))): item
        for item in profile.projects_json or []
        if isinstance(item, dict) and item.get("name")
    }
    result: list[dict[str, Any]] = []
    for item in selected or []:
        if not isinstance(item, dict):
            continue
        verified = verified_by_name.get(normalize_question_text(str(item.get("name", ""))))
        if verified:
            result.append({**verified, "resume_selection": item})
    return result


def _latex_escape(value: object) -> str:
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
    return "".join(replacements.get(char, char) for char in str(value or ""))


def _portfolio_latex(
    profile: ApplicationProfile,
    job: Job,
    projects: list[dict[str, Any]],
) -> str:
    sections: list[str] = []
    for project in projects[:4]:
        selection = project.get("resume_selection") if isinstance(project.get("resume_selection"), dict) else {}
        bullets = selection.get("bullets") if isinstance(selection, dict) else []
        if not isinstance(bullets, list) or not bullets:
            bullets = project.get("bullets") if isinstance(project.get("bullets"), list) else []
        detail = project.get("description") or project.get("details") or ""
        bullet_lines = "\n".join(
            rf"\item {_latex_escape(item)}" for item in bullets[:5] if str(item).strip()
        )
        if not bullet_lines and detail:
            bullet_lines = rf"\item {_latex_escape(detail)}"
        sections.append(
            rf"\section*{{{_latex_escape(project.get('name') or 'Verified Project')}}}"
            "\n"
            rf"\begin{{itemize}}{bullet_lines}\end{{itemize}}"
        )
    return "\n".join(
        [
            r"\documentclass[10pt]{article}",
            r"\usepackage[margin=0.65in]{geometry}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{lmodern}",
            r"\setlength{\parindent}{0pt}",
            r"\begin{document}",
            rf"{{\LARGE\textbf{{{_latex_escape(profile.full_name)}}}}}",
            r"\vspace{2mm}",
            rf"{{\large Project Portfolio — {_latex_escape(job.title)}}}",
            r"\hrule\vspace{3mm}",
            *sections,
            r"\end{document}",
        ]
    )


def get_or_create_role_specific_portfolio(
    db: Session,
    owner_user_id: str,
    job: Job,
    resume: GeneratedResume,
    profile: ApplicationProfile,
) -> GeneratedPortfolio | None:
    projects = select_role_specific_projects(resume, profile)
    if not projects:
        return None
    fingerprint = hashlib.sha256(
        json.dumps(
            {"job_id": job.id, "resume_id": resume.id, "projects": projects},
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(GeneratedPortfolio).where(
            GeneratedPortfolio.user_id == owner_user_id,
            GeneratedPortfolio.job_id == job.id,
            GeneratedPortfolio.content_hash == fingerprint,
            GeneratedPortfolio.status == "ready",
        )
    )
    if existing:
        return existing
    next_version = (
        db.scalar(
            select(GeneratedPortfolio.version)
            .where(
                GeneratedPortfolio.user_id == owner_user_id,
                GeneratedPortfolio.job_id == job.id,
            )
            .order_by(GeneratedPortfolio.version.desc())
            .limit(1)
        )
        or 0
    ) + 1
    safe_name = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        f"{profile.full_name}_{job.company}_{job.title}_Project_Portfolio_v{next_version}",
    ).strip("_")
    portfolio = GeneratedPortfolio(
        user_id=owner_user_id,
        job_id=job.id,
        version=next_version,
        status="ready",
        filename=f"{safe_name}.pdf",
        target_role=job.title,
        selected_projects_json=projects,
        latex_source=_portfolio_latex(profile, job, projects),
        content_hash=fingerprint,
    )
    db.add(portfolio)
    db.flush()
    return portfolio


def application_readiness(
    job: Job,
    profile: ApplicationProfile,
    resume: GeneratedResume | None,
    candidate: UserProfile | None = None,
    portfolio: GeneratedPortfolio | None = None,
) -> dict[str, Any]:
    portal = detect_portal(job.official_apply_url or job.apply_url, job.company)
    eligibility = job.analysis.eligibility_status if job.analysis else "UNKNOWN"
    hard_blocked = eligibility.upper().replace(" ", "_") == "NOT_ELIGIBLE"
    contact_complete = all((profile.full_name, profile.professional_email, profile.phone))
    education_complete = all((profile.university, profile.degree, profile.field_of_study, profile.expected_graduation_date))
    location_complete = all((profile.city, profile.state, profile.country))
    authorization_resolved = bool(candidate and candidate.citizenship_country and candidate.work_authorized_countries)
    selection = (
        build_application_selection(job, profile, resume)
        if resume
        else {
            "selected_projects": [],
            "generated_experience_text": "",
            "selected_skills": [],
            "skill_match_reasons": {},
            "project_match_reasons": {},
            "selection_warnings": [],
        }
    )
    selected_projects = selection["selected_projects"]
    selected_skills = selection["selected_skills"]
    checks = [
        {"key": "eligibility", "label": "Eligibility verified", "ready": not hard_blocked},
        {"key": "resume", "label": "Recommended resume generated", "ready": bool(resume and resume.status == "compiled")},
        {"key": "contact", "label": "Contact profile complete", "ready": contact_complete},
        {"key": "education", "label": "Education complete", "ready": education_complete},
        {"key": "location", "label": "Location complete", "ready": location_complete},
        {"key": "availability", "label": "Availability confirmed", "ready": bool(profile.application_preferences_confirmed_at)},
        {"key": "authorization", "label": "Work authorization resolved", "ready": authorization_resolved},
        {"key": "skills", "label": "Skills selected for this job", "ready": bool(selected_skills)},
        {"key": "projects", "label": "Experience selected for this job", "ready": bool(selected_projects)},
        {"key": "portfolio", "label": "Project portfolio ready" if portfolio else "Project portfolio optional", "ready": True},
        {
            "key": "portal",
            "label": f"{portal['portal_type'].replace('_', ' ').title()} assistant ({portal['support_status'].title()})",
            "ready": portal["support_status"] in {"SUPPORTED", "BETA"},
        },
    ]
    blocker = ""
    if hard_blocked:
        blocker = (job.analysis.blocker_reasons[0] if job.analysis and job.analysis.blocker_reasons else "This job is marked Not Eligible.")
    elif portal["support_status"] == "UNSUPPORTED":
        blocker = f"{portal['portal_type'].replace('_', ' ').title()} does not yet have a tested assistant adapter."
    return {
        "ready": all(item["ready"] for item in checks),
        "hard_blocked": hard_blocked,
        "blocker_reason": blocker,
        "portal_type": portal["portal_type"],
        "portal_job_id": portal["portal_job_id"],
        "support_status": portal["support_status"],
        "company_policy_key": portal["company_policy_key"],
        "detection_evidence": portal["detection_evidence"],
        "checks": checks,
        "sensitive_confirmation_notice": "Recognized stable eligibility answers are filled from the verified profile and shown for final review. New legal questions remain manual.",
        "selected_experience": selected_projects,
        "selected_skills": selected_skills,
        "generated_experience_text": selection["generated_experience_text"],
        "skill_match_reasons": selection["skill_match_reasons"],
        "project_match_reasons": selection["project_match_reasons"],
        "selection_warnings": selection["selection_warnings"],
    }


def validate_application_consistency(
    profile: dict[str, Any],
    observed: dict[str, Any],
    *,
    expected_resume_version_id: int | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    contact = profile.get("contact", {}) if isinstance(profile, dict) else {}
    education = profile.get("education", {}) if isinstance(profile, dict) else {}

    def mismatch(key: str, label: str, expected: Any) -> None:
        actual = observed.get(key)
        if actual not in (None, "") and expected not in (None, "") and str(actual).strip().casefold() != str(expected).strip().casefold():
            issues.append({"code": f"MISMATCH_{key.upper()}", "field": key, "message": f"{label} does not match the verified profile.", "observed": actual, "expected": expected})

    mismatch("email", "Email", contact.get("professional_email"))
    mismatch("city", "City", contact.get("city"))
    mismatch("graduation_date", "Graduation date", education.get("expected_graduation_date"))
    mismatch("gpa", "GPA", education.get("gpa"))
    if "city" in observed and not str(observed.get("city") or "").strip() and contact.get("city"):
        issues.append({"code": "MISSING_CITY", "field": "city", "message": "City is missing from the application.", "observed": "", "expected": contact.get("city")})
    canonical_start = str(education.get("start_date") or "")[:4]
    observed_start = str(observed.get("education_start_year") or "")[:4]
    if canonical_start and observed_start and canonical_start != observed_start:
        issues.append({"code": "BAD_EDUCATION_START_YEAR", "field": "education_start_year", "message": "Education start year conflicts with the verified profile.", "observed": observed_start, "expected": canonical_start})
    if observed_start.isdigit() and int(observed_start) < 1980:
        issues.append({"code": "IMPOSSIBLE_EDUCATION_DATE", "field": "education_start_year", "message": "Education start year appears impossible.", "observed": observed_start, "expected": canonical_start or None})
    canonical_end = str(education.get("expected_graduation_date") or "")[:4]
    observed_end = str(observed.get("education_end_year") or "")[:4]
    if canonical_end and observed_end and canonical_end != observed_end:
        issues.append({"code": "BAD_EDUCATION_END_YEAR", "field": "education_end_year", "message": "Education end year conflicts with the verified profile.", "observed": observed_end, "expected": canonical_end})
    if observed_end.isdigit() and int(observed_end) < 1980:
        issues.append({"code": "IMPOSSIBLE_EDUCATION_END_DATE", "field": "education_end_year", "message": "Education end year appears impossible.", "observed": observed_end, "expected": canonical_end or None})
    if "education_end_year" in observed and not observed_end and canonical_end:
        issues.append({"code": "MISSING_EDUCATION_END_DATE", "field": "education_end_year", "message": "Education end date is missing from the application.", "observed": "", "expected": canonical_end})
    address1 = normalize_question_text(str(observed.get("address_line1") or ""))
    address2 = normalize_question_text(str(observed.get("address_line2") or ""))
    if address1 and address1 == address2:
        issues.append({"code": "DUPLICATED_ADDRESS", "field": "address_line2", "message": "Address line 2 duplicates address line 1.", "observed": observed.get("address_line2"), "expected": ""})
    if expected_resume_version_id and observed.get("resume_version_id") not in (None, expected_resume_version_id):
        issues.append({"code": "WRONG_RESUME", "field": "resume_version_id", "message": "The selected resume is not the version bound to this application session.", "observed": observed.get("resume_version_id"), "expected": expected_resume_version_id})
    expected_resume_filename = str(observed.get("expected_resume_filename") or "")
    uploaded_resume_filename = str(observed.get("uploaded_resume_filename") or "")
    if expected_resume_filename and uploaded_resume_filename and uploaded_resume_filename != expected_resume_filename:
        issues.append({"code": "WRONG_RESUME_FILE", "field": "uploaded_resume_filename", "message": "The uploaded resume is not the file bound to this application session.", "observed": uploaded_resume_filename, "expected": expected_resume_filename})
    for missing in observed.get("required_missing_fields", []) if isinstance(observed.get("required_missing_fields"), list) else []:
        issues.append({"code": "MISSING_REQUIRED_FIELD", "field": str(missing), "message": f"Required field is blank: {missing}.", "observed": "", "expected": "Completed before final review"})
    if education.get("expected_graduation_date") and re.search(
        r"\b(?:graduated|degree completed)\b",
        normalize_question_text(str(observed.get("degree_status") or "")),
    ):
        issues.append({"code": "DEGREE_STATUS_CONTRADICTION", "field": "degree_status", "message": "Portal degree status says completed while the verified degree is still in progress.", "observed": observed.get("degree_status"), "expected": "In progress"})
    verified_skills = {normalize_question_text(str(item)) for item in profile.get("verified_skills", [])}
    unverified = [item for item in observed.get("skills", []) if normalize_question_text(str(item)) not in verified_skills]
    if unverified:
        issues.append({"code": "UNVERIFIED_SKILLS", "field": "skills", "message": "The page contains skills not present in the verified profile.", "observed": unverified, "expected": sorted(profile.get("verified_skills", []))})
    if observed.get("project_as_employment") and "not professional employment" not in normalize_question_text(str(observed.get("experience_description", ""))):
        issues.append({"code": "PROJECT_EMPLOYMENT_DISCLOSURE", "field": "experience_description", "message": "Academic project experience must state that it is not professional employment.", "observed": observed.get("experience_description"), "expected": "Academic and personal software projects; not professional employment."})
    def language_parts(value: Any) -> tuple[str, str]:
        parts = re.split(r"\s*(?:[-—–:|])\s*", str(value), maxsplit=1)
        return normalize_question_text(parts[0]), normalize_question_text(parts[1]) if len(parts) > 1 else ""

    canonical_languages = {
        name: level for name, level in (language_parts(item) for item in profile.get("languages", [])) if name
    }
    for item in observed.get("languages", []) if isinstance(observed.get("languages"), list) else []:
        name, level = language_parts(item)
        expected_level = canonical_languages.get(name)
        if name and level and expected_level and level != expected_level:
            issues.append({"code": "INCONSISTENT_LANGUAGE_FLUENCY", "field": "languages", "message": f"Language fluency for {name.title()} conflicts with the verified profile.", "observed": item, "expected": f"{name.title()} — {expected_level.title()}"})
    observed_authorization = observed.get("work_authorization_answers", {})
    confirmed_authorization = observed.get("confirmed_application_answers", {})
    if isinstance(observed_authorization, dict):
        for key, raw_values in observed_authorization.items():
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            normalized_values = {normalize_question_text(str(value)) for value in values if str(value).strip()}
            if len(normalized_values) > 1:
                issues.append({"code": "CONTRADICTORY_WORK_AUTHORIZATION", "field": str(key), "message": "The Workday page contains contradictory work-authorization answers.", "observed": values, "expected": None})
            confirmed = confirmed_authorization.get(key) if isinstance(confirmed_authorization, dict) else None
            confirmed_value = confirmed.get("answer") if isinstance(confirmed, dict) else confirmed
            if confirmed_value is not None and normalized_values and normalize_question_text(str(confirmed_value)) not in normalized_values:
                issues.append({"code": "CONTRADICTORY_WORK_AUTHORIZATION", "field": str(key), "message": "The visible work-authorization answer differs from the answer confirmed for this application.", "observed": values, "expected": confirmed_value})
    return issues
