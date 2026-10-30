"""Company targeting context is independent of job requisitions and user evidence."""
import json
import re
from types import SimpleNamespace

from app.services.talent_matching import AREA_SIGNALS

DEFAULT_TARGETS = list(AREA_SIGNALS)[:6]
BOSTON_DYNAMICS = {
    "company_id": "boston-dynamics",
    "company_name": "Boston Dynamics",
    "company_summary": "Develops mobile robots for industrial inspection, warehouse automation and robotic manipulation.",
    "technical_areas": ["Robotics", "Embedded Systems", "Robot Software", "Controls", "Autonomous Systems", "Hardware Software Integration", "Systems Engineering"],
    "common_role_categories": DEFAULT_TARGETS,
    "preferred_project_categories": ["Robotics", "Embedded Systems", "Hardware Software Integration", "FPGA / Digital Systems"],
    "preferred_skill_categories": ["Embedded Systems", "Robotics", "Controls", "Software Engineering"],
    "source_url": "https://bostondynamics.com/faq/",
    "last_verified_at": "2026-09-08T00:00:00+00:00",
    "talent_community_url": "https://bostondynamics.wd1.myworkdayjobs.com/en-US/Boston_Dynamics/introduceYourself",
    "talent_community_description": "Share a resume for consideration for future opportunities. No specific role or requisition. The technical areas are broad candidate targeting preferences, not stated job requirements.",
}


def is_talent_community(title: str, url: str = "") -> bool:
    # Inspect the entry title, not a job description's generic careers footer.
    text = title.casefold().replace("’", "'")
    return any(phrase in text for phrase in (
        "talent community", "talent network", "general interest", "future opportunities",
        "don't see a role", "talent hub",
    )) or "introduceyourself" in url.casefold()


def company_snapshot(company):
    if isinstance(company, dict):
        return dict(company)
    data = {column.name: getattr(company, column.name) for column in company.__table__.columns if column.name != "owner_user_id"}
    if data.get("last_verified_at"):
        data["last_verified_at"] = data["last_verified_at"].isoformat()
    return data


def talent_context(company, targets):
    data = company_snapshot(company)
    areas = list(dict.fromkeys(data["technical_areas"] + data["preferred_project_categories"]))
    context = {"company_areas": areas, "targets": targets, "description": data["company_summary"] + " " + data["talent_community_description"]}
    signals = list(dict.fromkeys(signal for area in targets + data["preferred_skill_categories"] for signal in AREA_SIGNALS.get(area, [area])))
    return SimpleNamespace(
        id=None, application_type="TALENT_COMMUNITY", company_id=data["company_id"],
        company=data["company_name"], title="Talent Community", status="active",
        description=context["description"] + " Technical focus: " + ", ".join(targets + signals),
        requirements="", preferred_qualifications="", area=" / ".join(targets),
        resume_target="talent_community", talent_ranking_context=json.dumps(context),
        target_role_categories=targets, analysis=None, ats_requisition_id="",
        official_apply_url=data["talent_community_url"], apply_url=data["talent_community_url"],
        location="", country="Unknown", physical_work_country_required="Unknown",
        remote_type="Unknown", research_areas=[],
    )


def company_resume_filename(name, company, targets, version):
    from app.services.resume_generation import sanitize_filename
    focus = targets[0] if targets else "Engineering"
    return sanitize_filename(f"{name}_{company}_{focus}_Resume_v{version}") + ".pdf"


def store_discovered_community(db, owner, data):
    from app.models import CompanyTalentProfile
    slug = re.sub(r"[^a-z0-9]+", "-", data["company"].casefold()).strip("-")[:80]
    if not slug:
        return
    row = db.get(CompanyTalentProfile, (slug, owner))
    if row is None:
        defaults = dict(BOSTON_DYNAMICS) if slug == "boston-dynamics" else {}
        defaults.pop("company_id", None)
        defaults.pop("company_name", None)
        if defaults.get("last_verified_at"):
            from datetime import datetime
            defaults["last_verified_at"] = datetime.fromisoformat(defaults["last_verified_at"])
        row = CompanyTalentProfile(company_id=slug, owner_user_id=owner, company_name=data["company"], **defaults)
        db.add(row)
    row.talent_community_url = data.get("official_apply_url") or data.get("apply_url") or ""
    row.talent_community_description = data.get("description") or data.get("title") or ""
    row.source_url = data.get("source_url") or ""
    db.flush()
