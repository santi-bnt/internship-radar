from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AIDecisionLog,
    AIUserSettings,
    ApplicationAnswerRegistry,
    ApplicationProfile,
    ApplicationSession,
    CandidateCorrectionMemory,
    UserApprovedMapping,
)
from app.schemas.api import AgentFieldInput, ApplicationAgentResponse, FieldResolution, TextAnswer
from app.services.ai_privacy import CandidateAIContextBuilder, PrivacyLevel, PrivacyPolicyEngine
from app.services.application_assistant import classify_question, normalize_question_text
from app.services.resume_skills import canonicalize_skill


PROFILE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("FULL_NAME", ("full name", "legal name", "preferred name")),
    ("FIRST_NAME", ("first name", "given name")),
    ("LAST_NAME", ("last name", "family name", "surname")),
    ("EMAIL", ("email", "e mail")),
    ("PHONE", ("phone", "mobile")),
    ("ADDRESS_LINE_1", ("address line 1", "street address")),
    ("ADDRESS_LINE_2", ("address line 2", "apartment", "suite")),
    ("CURRENT_CITY", ("current city", "city")),
    ("CURRENT_STATE", ("state", "province", "region")),
    ("CURRENT_COUNTRY", ("current country", "country")),
    ("POSTAL_CODE", ("postal code", "zip code", "zipcode")),
    ("UNIVERSITY", ("university", "school", "institution")),
    ("FIELD_OF_STUDY", ("field of study", "major", "discipline")),
    ("DEGREE", ("degree", "degree type")),
    ("GPA", ("gpa", "grade point")),
    ("EDUCATION_START_DATE", ("education start", "school start", "start date")),
    ("EXPECTED_GRADUATION", ("expected graduation", "graduation date", "completion date", "education end")),
    ("LINKEDIN", ("linkedin",)),
    ("GITHUB", ("github", "portfolio website")),
    ("LANGUAGES", ("languages", "language proficiency")),
    ("RELOCATION", ("willing to relocate", "relocation")),
    ("HOURS_PER_WEEK", ("hours per week", "weekly hours")),
)

WORK_AUTHORIZATION_PATTERNS = (
    "authorized to work", "work authorization", "require sponsorship", "visa sponsorship",
    "citizenship", "country of citizenship",
)
VOLUNTARY_PATTERNS = (
    "disability", "veteran", "race", "ethnicity", "religion", "sexual orientation",
    "gender identity", "criminal history", "self identification", "self identify",
)
ASSESSMENT_PATTERNS = (
    "coding assessment", "coding challenge", "online assessment", "behavioral assessment",
    "work simulation", "personality test", "technical assessment", "technical test",
)
ATTESTATION_PATTERNS = (
    "electronic signature", "type your name to certify", "i certify", "attestation",
    "signature", "certify and submit",
)
LEGAL_PATTERNS = (
    "non compete", "noncompete", "government employee", "conflict of interest",
    "intellectual property", "criminal conviction", "export control", "nda",
)
LEGAL_MEMORY_KEYS = frozenset({
    "FORMER_INTEL_EMPLOYEE", "FORMER_GE_EMPLOYEE", "FORMER_EY_EMPLOYEE",
    "EY_SAN_JOSE_FAMILY", "NONCOMPETE_RESTRICTION", "SECONDARY_EMPLOYMENT",
    "GOVERNMENT_EMPLOYEE", "FAMILY_GOVERNMENT_EMPLOYEE", "INTEL_IP_INTEREST",
    "INTELLECTUAL_PROPERTY", "EXPORT_CONTROL", "CRIMINAL_LEGAL_DISCLOSURE",
    "NDA_NONCOMPETE", "CONFLICT_OF_INTEREST",
})
JOB_TEXT_PATTERNS = (
    "why are you interested", "why this role", "why do you want to work", "hiring team",
    "areas are you interested", "technical background", "what interests you", "areas of interest",
    "why are you a good fit", "why should we hire", "what makes you a good fit",
)
EXPERIENCE_PATTERNS = (
    "describe your experience", "relevant project", "experience with", "tell us about a project",
    "describe a project", "tell us about your experience", "technical project",
    "engineering project", "technical challenge", "describe your background",
)
EMPLOYMENT_PATTERNS = ("employment history", "previous employers", "years of professional experience", "years of work experience", "professional experience", "professional work experience", "previous employment")
SKILL_PATTERNS = ("skills", "technologies", "proficient", "experience using")

DEGREE_PRIORITY: tuple[tuple[str, str], ...] = (
    ("robotics and digital systems engineering", "EXACT"),
    ("robotics engineering", "STRONG_EQUIVALENT"),
    ("robotics", "STRONG_EQUIVALENT"),
    ("software engineering", "RELATED_PROGRAMMING"),
    ("computer science", "RELATED_PROGRAMMING"),
    ("computer engineering", "RELATED_PROGRAMMING"),
    ("computer systems engineering", "RELATED_PROGRAMMING"),
    ("embedded systems engineering", "RELATED_PROGRAMMING"),
    ("electrical and computer engineering", "RELATED_ENGINEERING"),
    ("electrical engineering", "RELATED_ENGINEERING"),
    ("electronics engineering", "RELATED_ENGINEERING"),
    ("mechatronics engineering", "RELATED_ENGINEERING"),
    ("engineering", "RELATED_ENGINEERING"),
    ("other", "OTHER"),
)


def _normalized(value: Any) -> str:
    return normalize_question_text(str(value or ""))


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


class QuestionClassifier:
    def classify(self, label: str) -> tuple[str, str, float, str]:
        text = _normalized(label)
        if not text:
            return "UNKNOWN", "UNKNOWN", 0.0, "MANUAL_ONLY"
        if _contains(text, ASSESSMENT_PATTERNS):
            return "ASSESSMENT", "ASSESSMENT", 1.0, "MANUAL_ONLY"
        if _contains(text, ATTESTATION_PATTERNS):
            return "ELECTRONIC_ATTESTATION", "ELECTRONIC_ATTESTATION", 1.0, "MANUAL_ONLY"
        if _contains(text, VOLUNTARY_PATTERNS):
            return "VOLUNTARY_DISCLOSURE", "VOLUNTARY_DISCLOSURE", 1.0, "MANUAL_ONLY"
        if _contains(text, WORK_AUTHORIZATION_PATTERNS):
            return "WORK_AUTHORIZATION", self._authorization_field(text), 0.98, "AUTO_FILL_REVIEW"
        remembered = classify_question(text)
        if remembered["question_key"] in LEGAL_MEMORY_KEYS:
            return "LEGAL_COMPLIANCE", remembered["question_key"], remembered["confidence"], "CONFIRM"
        if _contains(text, LEGAL_PATTERNS):
            return "LEGAL_COMPLIANCE", "LEGAL_COMPLIANCE", 0.97, "CONFIRM"
        accepts_projects = _contains(text, (
            "academic or professional experience", "professional or academic experience",
            "personal projects or work experience", "project experience or professional experience",
        ))
        if _contains(text, EMPLOYMENT_PATTERNS) and not accepts_projects:
            return "UNKNOWN", "EMPLOYMENT_HISTORY", 1.0, "MANUAL_ONLY"
        if accepts_projects or text in {"experience", "relevant experience", "technical experience", "experience description"}:
            return "EXPERIENCE_QUESTION", "EXPERIENCE_ANSWER", 0.94, "GENERATE_REVIEW"
        # Open-ended questions can mention profile words such as "degree" or
        # "university". Classify the question before matching short field labels.
        if _contains(text, EXPERIENCE_PATTERNS) or re.search(
            r"\b(?:describe|tell us about|tell me about)\b.{0,160}\b(?:experience|project|background|challenge)\b", text,
        ):
            return "EXPERIENCE_QUESTION", "EXPERIENCE_ANSWER", 0.94, "GENERATE_REVIEW"
        if _contains(text, JOB_TEXT_PATTERNS):
            return "JOB_SPECIFIC_TEXT", "JOB_SPECIFIC_ANSWER", 0.93, "GENERATE_REVIEW"
        for canonical, aliases in PROFILE_PATTERNS:
            if any(alias == text or alias in text for alias in aliases):
                category = "EDUCATION_MAPPING" if canonical in {"DEGREE", "FIELD_OF_STUDY"} else "PROFILE_FACT"
                return category, canonical, 0.97, "AUTO_FILL"
        if _contains(text, SKILL_PATTERNS):
            return "SKILL_QUESTION", "SKILLS", 0.9, "AUTO_FILL_REVIEW"
        return "UNKNOWN", "UNKNOWN", 0.25, "MANUAL_ONLY"

    @staticmethod
    def _authorization_field(text: str) -> str:
        if "sponsor" in text:
            return "SPONSORSHIP"
        if "citizen" in text:
            return "CITIZENSHIP"
        return "WORK_AUTHORIZATION"


@dataclass(frozen=True)
class DropdownMatch:
    selected_option: str | None
    match_type: str
    confidence: float
    requires_review: bool
    reason: str


class DropdownMatcher:
    def match_degree(
        self,
        canonical_value: str,
        options: list[str],
        approved: list[UserApprovedMapping] | None = None,
    ) -> DropdownMatch:
        normalized_options = {_normalized(option): option for option in options if _normalized(option)}
        for mapping in approved or []:
            if _normalized(mapping.canonical_value) == _normalized(canonical_value):
                option = normalized_options.get(_normalized(mapping.portal_option))
                if option:
                    return DropdownMatch(option, mapping.match_type, 1.0, False, "Reused a mapping previously approved by this user.")
        exact = normalized_options.get(_normalized(canonical_value))
        if exact:
            return DropdownMatch(exact, "EXACT", 1.0, False, "The portal contains the canonical program name.")
        for preferred, match_type in DEGREE_PRIORITY:
            option = normalized_options.get(preferred)
            if option:
                confidence = {
                    "STRONG_EQUIVALENT": 0.96,
                    "RELATED_PROGRAMMING": 0.88,
                    "RELATED_ENGINEERING": 0.74,
                    "OTHER": 0.65,
                }.get(match_type, 0.5)
                requires_review = match_type not in {"EXACT", "STRONG_EQUIVALENT"}
                reason = (
                    "Exact Robotics option unavailable; selected the closest programming-oriented truthful option."
                    if match_type == "RELATED_PROGRAMMING"
                    else "Selected the closest truthful robotics-equivalent option."
                    if match_type == "STRONG_EQUIVALENT"
                    else "Only a broader truthful representation is available; user confirmation is required."
                )
                return DropdownMatch(option, match_type, confidence, requires_review, reason)
        return DropdownMatch(None, "UNKNOWN", 0.0, True, "No truthful portal option is available.")

    def match(self, canonical_value: Any, options: list[str]) -> DropdownMatch:
        if canonical_value is None or not options:
            return DropdownMatch(None, "UNKNOWN", 0.0, True, "No candidate value or portal options were available.")
        target = _normalized(canonical_value)
        exact = next((option for option in options if _normalized(option) == target), None)
        if exact:
            return DropdownMatch(exact, "EXACT", 1.0, False, "Exact normalized option match.")
        aliases = {"yes": {"yes", "true", "authorized"}, "no": {"no", "false", "not authorized"}}
        for canonical, values in aliases.items():
            if target in values:
                option = next((item for item in options if _normalized(item) in values), None)
                if option:
                    return DropdownMatch(option, "STRONG_EQUIVALENT", 0.97, False, "Matched a normalized boolean option.")
        scored = sorted(
            ((SequenceMatcher(None, target, _normalized(option)).ratio(), option) for option in options),
            reverse=True,
        )
        if scored and scored[0][0] >= 0.9:
            return DropdownMatch(scored[0][1], "STRONG_EQUIVALENT", scored[0][0], False, "Matched a high-confidence normalized alias.")
        return DropdownMatch(None, "UNKNOWN", scored[0][0] if scored else 0.0, True, "No high-confidence truthful option match.")


class FreeTextAnswerGenerator:
    RISKY_CLAIMS = ("Power Automate", "GitHub Copilot", "Copilot", "CUDA", "ROS", "ROS2", "C#", "AWS", "LangChain")

    @staticmethod
    def _mentions(text: str, skill: str) -> bool:
        # Preserve language punctuation and token boundaries: Java != JavaScript,
        # and C != C++ or a letter embedded in another word.
        return bool(re.search(rf"(?<![\w+#]){re.escape(skill.casefold())}(?![\w+#])", text.casefold()))

    @staticmethod
    def _fit_limit(text: str, limit: int | None) -> str:
        if not limit or len(text) <= limit:
            return text
        sentences = re.split(r"(?<=[.!?])\s+", text)
        result = ""
        for sentence in sentences:
            candidate = f"{result} {sentence}".strip()
            if len(candidate) <= limit:
                result = candidate
        if result:
            return result
        return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")

    def generate(
        self,
        question: str,
        candidate_context: dict[str, Any],
        job_context: dict[str, Any],
        *,
        maxlength: int | None = None,
    ) -> TextAnswer:
        skills = [str(item) for item in candidate_context.get("verified_skills", [])]
        projects = [item for item in candidate_context.get("verified_projects", []) if isinstance(item, dict)]
        job_text = " ".join(str(job_context.get(key, "")) for key in ("title", "description", "requirements"))
        question_text = _normalized(question)
        question_skills = [skill for skill in skills if self._mentions(question, skill)]
        relevant_skills = list(dict.fromkeys([
            *question_skills, *[skill for skill in skills if self._mentions(job_text, skill)],
        ]))[:6]
        def relevance(project: dict[str, Any]) -> int:
            project_skills = {str(item).casefold() for item in project.get("verified_skills", [])}
            return 10 * sum(skill.casefold() in project_skills for skill in question_skills) + sum(
                skill.casefold() in project_skills for skill in relevant_skills
            )
        # A concrete implementation is required for a project-based claim.
        relevant_projects = sorted(
            [item for item in projects if item.get("verified_facts")], key=relevance, reverse=True,
        )
        if question_skills:
            relevant_projects = [item for item in relevant_projects if any(
                skill.casefold() in {str(value).casefold() for value in item.get("verified_skills", [])}
                for skill in question_skills
            )]
        evidence_ids = [str(item.get("project_id")) for item in relevant_projects[:2] if item.get("project_id")]
        lead = relevant_projects[0] if relevant_projects else None
        title = str(job_context.get("title") or "this opportunity")
        company = str(job_context.get("company") or "the company")
        asked_technology = any(self._mentions(question, skill) for skill in (
            *self.RISKY_CLAIMS, "Java", "JavaScript", "Python", "C++", "C", "SQL", "Verilog",
            "Kubernetes", "Azure", "AUTOSAR", "UVM",
        ))
        unsupported_question = asked_technology and not question_skills
        if unsupported_question or (not relevant_skills and not lead):
            answer = ""
            evidence_ids = []
            relevant_skills = []
        elif "area" in question_text and "interest" in question_text:
            answer = f"I am most interested in {', '.join(relevant_skills[:4] or skills[:4])}, where I can apply my verified technical project experience."
        elif "project" in question_text or "experience" in question_text or question_skills or "challenge" in question_text:
            if lead:
                facts = [str(item) for item in lead.get("verified_facts", [])]
                supported = [skill for skill in question_skills if skill.casefold() in {
                    str(item).casefold() for item in lead.get("verified_skills", [])
                }]
                introduction = f"In my academic/personal project {lead['name']}, I used {', '.join(supported)}." if supported else f"A relevant academic/personal project is {lead['name']}."
                answer = f"{introduction} {' '.join(facts[:2])}"
                evidence_ids = [str(lead["project_id"])] if lead.get("project_id") else []
            else:
                answer = ""
        else:
            project_phrase = f" In {lead['name']}, {str(lead['verified_facts'][0])}" if lead else ""
            skill_phrase = ", ".join(relevant_skills[:4] or skills[:4])
            alignment = f"my experience with {skill_phrase}" if skill_phrase else "my technical project work"
            answer = f"I am interested in the {title} opportunity at {company} because it aligns with {alignment}.{project_phrase}"
        verified = {item.strip().casefold() for item in skills}
        for claim in self.RISKY_CLAIMS:
            present = re.search(rf"(?<!\w){re.escape(claim.casefold())}(?!\w)", answer.casefold())
            if present and claim.casefold() not in verified:
                raise ValueError(f"Generated answer contains unsupported claim: {claim}")
        answer = self._fit_limit(answer, maxlength)
        evidence_skill_ids = [
            f"skill_{re.sub(r'[^a-z0-9]+', '_', _normalized(skill)).strip('_')}"
            for skill in relevant_skills
        ]
        return TextAnswer(
            answer=answer,
            confidence=0.35 if not answer else 0.92 if evidence_ids else 0.85 if evidence_skill_ids else 0.7,
            evidence_project_ids=evidence_ids,
            evidence_skill_ids=evidence_skill_ids,
            character_count=len(answer),
            requires_review=True,
        )


class BrowserExecutorPolicy:
    ALLOWED = frozenset({"SET_VALUE", "SELECT_OPTION", "ATTACH_FILE"})

    @classmethod
    def validate(cls, resolution: FieldResolution, field: AgentFieldInput) -> bool:
        if resolution.action in {"MANUAL_ONLY", "CONFIRM"}:
            return False
        if resolution.confidence < 0.8:
            return False
        if resolution.selected_option and resolution.selected_option not in field.available_options:
            return False
        if resolution.question_category in {"ASSESSMENT", "ELECTRONIC_ATTESTATION", "VOLUNTARY_DISCLOSURE"}:
            return False
        return True


class SemanticFieldResolver:
    def __init__(self):
        self.classifier = QuestionClassifier()
        self.dropdowns = DropdownMatcher()
        self.answers = FreeTextAnswerGenerator()
        self.privacy = PrivacyPolicyEngine()

    @staticmethod
    def _profile_value(canonical: str, snapshot: dict[str, Any]) -> Any:
        contact = snapshot.get("contact", {})
        education = snapshot.get("education", {})
        authorization = snapshot.get("work_authorization", {})
        preferences = snapshot.get("application_preferences", {})
        full_name = str(contact.get("full_name") or "")
        names = full_name.split()
        values = {
            "FULL_NAME": full_name,
            "FIRST_NAME": names[0] if names else "",
            "LAST_NAME": " ".join(names[1:]),
            "EMAIL": contact.get("professional_email"),
            "PHONE": contact.get("phone"),
            "ADDRESS_LINE_1": contact.get("address_line1"),
            "ADDRESS_LINE_2": contact.get("address_line2"),
            "CURRENT_CITY": contact.get("city"),
            "CURRENT_STATE": contact.get("state"),
            "CURRENT_COUNTRY": contact.get("country"),
            "POSTAL_CODE": contact.get("postal_code"),
            "UNIVERSITY": education.get("university"),
            "DEGREE": education.get("degree"),
            "FIELD_OF_STUDY": education.get("field_of_study"),
            "GPA": education.get("gpa"),
            "EDUCATION_START_DATE": education.get("start_date"),
            "EXPECTED_GRADUATION": education.get("expected_graduation_date"),
            "LANGUAGES": snapshot.get("languages", []),
            "LINKEDIN": snapshot.get("links", {}).get("linkedin"),
            "GITHUB": snapshot.get("links", {}).get("github"),
            "RELOCATION": preferences.get("willing_to_relocate"),
            "HOURS_PER_WEEK": preferences.get("hours_per_week"),
            "CITIZENSHIP": authorization.get("citizenship_country"),
        }
        return values.get(canonical)

    @staticmethod
    def _authorization_value(canonical: str, label: str, snapshot: dict[str, Any], job: dict[str, Any]) -> Any:
        authorization = snapshot.get("work_authorization", {})
        country = str(job.get("physical_work_country_required") or job.get("country") or "")
        if canonical == "CITIZENSHIP":
            return authorization.get("citizenship_country")
        if canonical == "SPONSORSHIP":
            return authorization.get("requires_us_employment_sponsorship") if "united states" in _normalized(country) else None
        if "united states" in _normalized(country):
            return authorization.get("us_work_authorized")
        return any(_normalized(item) == _normalized(country) for item in authorization.get("work_authorized_countries", []))

    @staticmethod
    def _format_value(canonical: str, value: Any, field: AgentFieldInput) -> Any:
        if value in (None, ""):
            return value
        label = _normalized(f"{field.raw_label} {field.nearby_text}")
        if canonical in {"EXPECTED_GRADUATION", "EDUCATION_START_DATE"}:
            raw = str(value)
            match = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?", raw)
            if not match:
                return value
            year, month, day = match.group(1), match.group(2), match.group(3) or "01"
            if field.control_type == "month":
                return f"{year}-{month}"
            if field.control_type == "date":
                return f"{year}-{month}-{day}"
            if "month" in label and "year" not in label:
                return [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December",
                ][int(month) - 1]
            if "year" in label and "month" not in label:
                return year
            if "mm/yy" in label or "mm / yy" in label:
                return f"{month}/{year[-2:]}"
        return value

    def resolve(
        self,
        field: AgentFieldInput,
        *,
        snapshot: dict[str, Any],
        candidate_context: dict[str, Any],
        job_context: dict[str, Any],
        approved_mappings: list[UserApprovedMapping],
        corrections: dict[str, Any],
        answer_memory: dict[str, Any],
    ) -> FieldResolution:
        category, canonical, confidence, action = self.classifier.classify(f"{field.raw_label} {field.nearby_text}")
        privacy_level = self.privacy.classify(canonical.casefold()).value
        selected: Any = None
        selected_option: str | None = None
        match_type = "UNKNOWN"
        requires_review = action in {"AUTO_FILL_REVIEW", "GENERATE_REVIEW", "CONFIRM", "MANUAL_ONLY"}
        reason = "Field requires manual review because it could not be mapped safely."
        evidence_ids: list[str] = []
        if canonical in corrections:
            selected = corrections[canonical]
            confidence = 1.0
            reason = "Used a verified correction stored for this user and scope."
        elif category == "LEGAL_COMPLIANCE" and canonical in answer_memory:
            selected = answer_memory[canonical]
            confidence = 0.95
            action = "AUTO_FILL_REVIEW"
            requires_review = True
            reason = "Used this user's previously confirmed stable legal answer; final review remains required."
        elif category == "WORK_AUTHORIZATION":
            selected = self._authorization_value(canonical, field.raw_label, snapshot, job_context)
            reason = "Resolved from the authenticated user's structured work-authorization profile."
            privacy_level = PrivacyLevel.SENSITIVE.value
        elif category in {"PROFILE_FACT", "EDUCATION_MAPPING"}:
            selected = self._profile_value(canonical, snapshot)
            reason = "Resolved deterministically from the authenticated user's verified profile."
        elif category == "SKILL_QUESTION":
            selected = list(job_context.get("selected_skills") or candidate_context.get("verified_skills", []))
            reason = "Selected only skills verified for this user and ranked for this application."
        elif category in {"JOB_SPECIFIC_TEXT", "EXPERIENCE_QUESTION"}:
            generated = self.answers.generate(
                field.raw_label, candidate_context, job_context, maxlength=field.maxlength
            )
            selected = generated.answer
            evidence_ids = [*generated.evidence_project_ids, *generated.evidence_skill_ids]
            confidence = generated.confidence
            reason = "Generated locally from evidence-addressable verified projects and skills."
            if not selected:
                reason = "No supported answer was found in the verified evidence. Complete this question on the portal."
        selected = self._format_value(canonical, selected, field)
        if field.available_options and selected not in (None, "", []):
            match = (
                self.dropdowns.match_degree(str(selected), field.available_options, approved_mappings)
                if canonical == "FIELD_OF_STUDY"
                else self.dropdowns.match(selected, field.available_options)
            )
            selected_option = match.selected_option
            match_type = match.match_type
            confidence = min(confidence, match.confidence) if confidence else match.confidence
            requires_review = requires_review or match.requires_review
            reason = match.reason
            if match.match_type in {"RELATED_ENGINEERING", "OTHER", "UNKNOWN"}:
                action = "CONFIRM" if match.selected_option else "MANUAL_ONLY"
            elif match.match_type == "RELATED_PROGRAMMING":
                action = "AUTO_FILL_REVIEW"
        if selected in (None, "", []) and action not in {"MANUAL_ONLY", "CONFIRM"}:
            action = "MANUAL_ONLY"
            confidence = min(confidence, 0.4)
            requires_review = True
            reason = "The authenticated profile does not contain a verified value for this field."
        resolution = FieldResolution(
            field_id=field.field_id,
            canonical_field=canonical,
            question_category=category,
            action=action,
            selected_value=selected,
            selected_option=selected_option,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            match_type=match_type,
            reason_summary=reason,
            requires_review=requires_review,
            evidence_ids=evidence_ids,
            privacy_level=privacy_level,
        )
        if not BrowserExecutorPolicy.validate(resolution, field) and resolution.action in {"AUTO_FILL", "AUTO_FILL_REVIEW", "GENERATE_REVIEW"}:
            resolution.action = "CONFIRM" if resolution.confidence >= 0.6 else "MANUAL_ONLY"
            resolution.requires_review = True
        return resolution


class PageInterpreter:
    """Accept DOM/accessibility-derived field descriptions; vision is deliberately not primary."""

    @staticmethod
    def interpret(fields: list[AgentFieldInput]) -> list[AgentFieldInput]:
        return [field for field in fields if field.raw_label.strip() or field.nearby_text.strip()]


class ApplicationAgent:
    def __init__(self):
        self.context_builder = CandidateAIContextBuilder()
        self.resolver = SemanticFieldResolver()
        self.interpreter = PageInterpreter()

    @staticmethod
    def _corrections(db: Session, owner: str, session: ApplicationSession) -> dict[str, Any]:
        rows = list(db.scalars(select(CandidateCorrectionMemory).where(
            CandidateCorrectionMemory.owner_user_id == owner,
            CandidateCorrectionMemory.verified.is_(True),
        ).order_by(CandidateCorrectionMemory.created_at.desc())))
        result: dict[str, Any] = {}
        for row in rows:
            applies = (
                row.scope == "USER_GLOBAL"
                or row.scope == "PORTAL" and row.portal == session.portal_type
                or row.scope == "COMPANY" and _normalized(row.company) == _normalized(session.company)
                or row.scope == "APPLICATION_ONLY" and row.application_session_id == session.id
            )
            if applies and row.canonical_field not in result:
                result[row.canonical_field] = row.corrected_value_json.get("value")
        return result

    def analyze(self, db: Session, session: ApplicationSession, fields: list[AgentFieldInput]) -> ApplicationAgentResponse:
        profile = db.scalar(select(ApplicationProfile).where(
            ApplicationProfile.owner_user_id == session.owner_user_id
        ))
        if profile is None:
            raise ValueError("Application profile is unavailable for this authenticated user.")
        settings_row = db.get(AIUserSettings, session.owner_user_id)
        if settings_row is None:
            settings_row = AIUserSettings(owner_user_id=session.owner_user_id)
            db.add(settings_row)
        context = self.context_builder.build(profile, include_authorization=False)
        selected_project_names = {
            _normalized(item.get("name") or item.get("title"))
            for item in (session.selected_projects_json or [])
            if isinstance(item, dict)
        }
        if selected_project_names:
            context["verified_projects"] = [
                item for item in context["verified_projects"]
                if _normalized(item.get("name")) in selected_project_names
            ]
            project_order = {
                _normalized(item.get("name") or item.get("title")): index
                for index, item in enumerate(session.selected_projects_json or []) if isinstance(item, dict)
            }
            context["verified_projects"].sort(key=lambda item: project_order.get(_normalized(item.get("name")), 999))
        selected_skill_keys = {canonicalize_skill(item) for item in (session.selected_skills_json or [])}
        if selected_skill_keys:
            context["verified_skills"] = [
                item for item in session.profile_snapshot_json.get("verified_skills", context["verified_skills"])
                if canonicalize_skill(item) in selected_skill_keys
            ]
        job = dict(session.job_snapshot_json or {})
        job["selected_skills"] = list(session.selected_skills_json or [])
        approved = list(db.scalars(select(UserApprovedMapping).where(
            UserApprovedMapping.owner_user_id == session.owner_user_id,
            UserApprovedMapping.portal == session.portal_type,
            UserApprovedMapping.approved_by_user.is_(True),
        )))
        corrections = self._corrections(db, session.owner_user_id, session)
        answer_memory = {
            row.question_key: row.answer_json.get("value")
            for row in db.scalars(select(ApplicationAnswerRegistry).where(
                ApplicationAnswerRegistry.owner_user_id == session.owner_user_id,
                ApplicationAnswerRegistry.last_confirmed_at.is_not(None),
            ))
        }
        resolutions = [
            self.resolver.resolve(
                field,
                snapshot=dict(session.profile_snapshot_json or {}),
                candidate_context=context,
                job_context=job,
                approved_mappings=approved,
                corrections=corrections,
                answer_memory=answer_memory,
            )
            for field in self.interpreter.interpret(fields)
        ]
        for resolution, field in zip(resolutions, self.interpreter.interpret(fields), strict=False):
            logged_value = (
                "[REDACTED]"
                if resolution.privacy_level in {
                    PrivacyLevel.PERSONAL.value,
                    PrivacyLevel.SENSITIVE.value,
                    PrivacyLevel.HIGHLY_SENSITIVE.value,
                    PrivacyLevel.NEVER_AI.value,
                }
                else resolution.selected_option or resolution.selected_value
            )
            db.add(AIDecisionLog(
                owner_user_id=session.owner_user_id,
                application_session_id=session.id,
                field=resolution.canonical_field,
                question_normalized=_normalized(f"{field.raw_label} {field.nearby_text}"),
                decision_type=resolution.action,
                provider=resolution.provider,
                execution_location=resolution.execution_location,
                confidence=resolution.confidence,
                selected_value_json={"value": logged_value},
                reason_summary=resolution.reason_summary,
            ))
        waiting = any(
            field.required and resolution.action in {"CONFIRM", "MANUAL_ONLY"}
            for field, resolution in zip(self.interpreter.interpret(fields), resolutions, strict=False)
        )
        db.commit()
        return ApplicationAgentResponse(
            status="WAITING_FOR_USER" if waiting else "PLAN_READY",
            resolutions=resolutions,
            local_ai_available=None,
            final_submit_policy="MANUAL_ONLY",
        )
