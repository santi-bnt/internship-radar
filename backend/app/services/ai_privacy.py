from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any

from app.services.language_evidence import resume_language_lines


class PrivacyLevel(StrEnum):
    PUBLIC = "PUBLIC"
    NORMAL = "NORMAL"
    PERSONAL = "PERSONAL"
    SENSITIVE = "SENSITIVE"
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"
    NEVER_AI = "NEVER_AI"


NEVER_EXTERNAL_KEYS = frozenset({
    "password", "passcode", "mfa", "mfa_code", "otp", "captcha", "captcha_response",
    "authentication_token", "access_token", "refresh_token", "session_token", "cookie",
    "passport_number", "visa_document_number", "ssn", "curp", "rfc",
    "government_id", "bank_account", "credit_card", "electronic_signature",
})

HIGHLY_SENSITIVE_KEYS = frozenset({
    "medical", "medical_documents", "disability", "disability_status", "veteran_status",
    "race", "ethnicity", "religion", "sexual_orientation", "criminal_history",
})

PERSONAL_KEYS = frozenset({
    "full_name", "first_name", "last_name", "email", "professional_email", "phone",
    "address", "address_line1", "address_line2", "postal_code", "current_location",
    "city", "state", "country", "linkedin", "github",
})

SENSITIVE_KEYS = frozenset({
    "citizenship", "citizenship_country", "work_authorization", "work_authorized_countries",
    "us_work_authorized", "requires_us_employment_sponsorship", "salary_expectation",
})

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
_GOVERNMENT_ID = re.compile(r"\b(?:CURP|RFC|SSN|passport|visa document)\s*[:#-]?\s*[A-Z0-9-]{5,}\b", re.I)


class PrivacyPolicyError(ValueError):
    pass


class PrivacyPolicyEngine:
    """Classify context and enforce an absolute external-provider boundary."""

    @staticmethod
    def classify(field: str) -> PrivacyLevel:
        key = field.strip().casefold()
        if key in NEVER_EXTERNAL_KEYS:
            return PrivacyLevel.NEVER_AI
        if key in HIGHLY_SENSITIVE_KEYS:
            return PrivacyLevel.HIGHLY_SENSITIVE
        if key in SENSITIVE_KEYS:
            return PrivacyLevel.SENSITIVE
        if key in PERSONAL_KEYS:
            return PrivacyLevel.PERSONAL
        if key in {"skills", "verified_skills", "projects", "verified_projects", "education_summary"}:
            return PrivacyLevel.NORMAL
        return PrivacyLevel.NORMAL

    @staticmethod
    def redact_text(value: str) -> tuple[str, list[str]]:
        redacted: list[str] = []
        result = value
        for label, pattern in (("email", _EMAIL), ("phone", _PHONE), ("government_identifier", _GOVERNMENT_ID)):
            if pattern.search(result):
                result = pattern.sub(f"[{label.upper()}_REDACTED]", result)
                redacted.append(label)
        return result, redacted

    def prepare_external_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
        included: list[str] = []
        redacted: list[str] = []

        def clean(value: Any, path: str) -> Any:
            key = path.rsplit(".", 1)[-1].casefold()
            level = self.classify(key)
            if level in {PrivacyLevel.NEVER_AI, PrivacyLevel.HIGHLY_SENSITIVE, PrivacyLevel.SENSITIVE, PrivacyLevel.PERSONAL}:
                redacted.append(path)
                return None
            if isinstance(value, dict):
                return {
                    child_key: cleaned
                    for child_key, child_value in value.items()
                    if (cleaned := clean(child_value, f"{path}.{child_key}" if path else child_key)) is not None
                }
            if isinstance(value, list):
                return [cleaned for index, item in enumerate(value) if (cleaned := clean(item, f"{path}[{index}]")) is not None]
            if isinstance(value, str):
                cleaned, detected = self.redact_text(value)
                redacted.extend(f"{path}:{item}" for item in detected)
                if cleaned:
                    included.append(path)
                return cleaned
            included.append(path)
            return value

        safe = clean(payload, "")
        if not isinstance(safe, dict):
            raise PrivacyPolicyError("External AI payload must be a structured object.")
        serialized = repr(safe)
        if _EMAIL.search(serialized) or _PHONE.search(serialized) or _GOVERNMENT_ID.search(serialized):
            raise PrivacyPolicyError("External AI payload still contains prohibited personal data.")
        return safe, sorted(set(included)), sorted(set(redacted))


class CandidateAIContextBuilder:
    """Build identity-free, evidence-addressable AI context from one authenticated profile."""

    @staticmethod
    def _value(item: Any, key: str, default: Any = "") -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @staticmethod
    def _evidence_id(kind: str, name: str, index: int) -> str:
        digest = hashlib.sha256(f"{kind}:{index}:{name}".encode("utf-8")).hexdigest()[:12]
        return f"{kind}_{digest}"

    def build(self, profile: Any, *, include_authorization: bool = False) -> dict[str, Any]:
        education_items = list(getattr(profile, "education_json", []) or [])
        education = education_items[0] if education_items else {}
        if not education and hasattr(profile, "university"):
            education = {
                "institution": getattr(profile, "university", ""),
                "degree": getattr(profile, "degree", ""),
                "field_of_study": getattr(profile, "field_of_study", ""),
                "graduation": str(getattr(profile, "expected_graduation_date", "") or ""),
                "gpa": getattr(profile, "gpa", None),
                "gpa_scale": getattr(profile, "gpa_scale", None),
            }
        projects = []
        for index, item in enumerate(getattr(profile, "projects_json", []) or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or f"Project {index + 1}").strip()
            facts = item.get("bullets") if isinstance(item.get("bullets"), list) else []
            if not facts and item.get("details"):
                facts = [str(item["details"])]
            projects.append({
                "project_id": self._evidence_id("project", name, index),
                "name": name,
                "verified_skills": list(item.get("technologies") or []),
                "verified_facts": [str(fact).strip() for fact in facts if str(fact).strip()],
                "team_project": bool(item.get("team_project", False)),
                "individual_contribution": str(item.get("individual_contribution") or ""),
                "allowed_claims": [str(fact).strip() for fact in facts if str(fact).strip()],
            })
        context: dict[str, Any] = {
            "education_summary": {
                "institution": self._value(education, "institution", self._value(education, "university")),
                "degree": self._value(education, "degree"),
                "field_of_study": self._value(education, "field_of_study", self._value(education, "field")),
                "graduation": self._value(education, "graduation"),
                "gpa": self._value(education, "gpa"),
                "gpa_scale": self._value(education, "gpa_scale"),
            },
            "verified_skills": list(getattr(profile, "skills_json", []) or []),
            "verified_projects": projects,
            "verified_work_experience": list(getattr(profile, "work_experience_json", getattr(profile, "experience_json", [])) or []),
            "languages": resume_language_lines(profile),
            "forbidden_claims": list(getattr(profile, "forbidden_claims_json", []) or []),
        }
        if include_authorization:
            context["work_authorization"] = {
                "citizenship_country": getattr(profile, "citizenship_country", ""),
                "work_authorized_countries": list(getattr(profile, "work_authorized_countries", []) or []),
                "us_work_authorized": bool(getattr(profile, "us_work_authorized", False)),
                "requires_us_employment_sponsorship": bool(getattr(profile, "requires_us_employment_sponsorship", True)),
            }
        return context

    def for_resume(self, profile: Any) -> dict[str, Any]:
        return self.build(profile, include_authorization=False)
