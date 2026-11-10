"""Additive dashboard over Jobs; never changes another candidate's records."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Job, OpportunityTracking, UserProfile
from app.schemas.opportunities import OpportunityInput

JOB_FIELDS = {"program", "organization", "country", "city", "official_url", "application_url", "description", "research_areas", "lab", "professor", "notes", "deadline"}
AREAS = {"robotics": 14, "artificial intelligence": 12, "embedded systems": 10, "iot": 7, "autonomous systems": 7, "control": 7, "machine learning": 6, "computer vision": 6, "computer systems": 5, "electrical engineering": 4, "fpga": 4}
UNLOADED = object()


def lock_collection(db: Session, owner: str):
    """Serialize duplicate checks and insertion, including concurrent first opens."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        key = int.from_bytes(hashlib.sha256(f"opportunities:{owner}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    elif dialect == "sqlite" and not db.in_transaction():
        db.execute(text("BEGIN IMMEDIATE"))


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    # This program's landing and apply pages are the same opportunity.
    if host == "eee.epfl.ch" and path in {"", "/apply"}:
        path = ""
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source"}))
    return urlunsplit(("https", host, path, query, ""))


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def duplicate(jobs: list[Job], value: OpportunityInput) -> Job | None:
    key = canonical_url(value.official_url)
    for job in jobs:
        years = set(re.findall(r"\b20\d{2}\b", value.program))
        existing_years = set(re.findall(r"\b20\d{2}\b", job.title))
        if years and existing_years and not years.intersection(existing_years):
            continue
        urls = [job.canonical_official_url, job.research_url, job.apply_url, job.posting_url, job.source_url, job.application_url]
        if any(canonical_url(url) == key for url in urls if url):
            return job
        if normalized(value.organization) not in {"", "unknown"} and normalized(job.company) not in {"", "unknown"} and normalized(job.title) == normalized(value.program) and normalized(job.company) == normalized(value.organization):
            return job
    return None


def fit(value: dict) -> tuple[int, list[str]]:
    areas = {a.casefold() for a in value["research_areas"]}
    aliases = {"ai": "artificial intelligence", "internet of things": "iot", "ece": "electrical engineering"}
    areas = {aliases.get(a, a) for a in areas}
    technical = min(50, sum(points for area, points in AREAS.items() if area in areas))
    reasons = [f"Research interests: {technical}/50"] if technical else []
    score = technical
    bonuses = [
        (value["country"] in {"United States", "USA", "US"}, 15, "United States geographic priority"),
        (value["country"] == "Canada", 12, "Canada geographic priority"),
        (value["international_eligibility"] == "International students accepted", 10, "International students accepted (program conditions still apply)"),
        (bool(set(value["funding"]) & {"Fully funded", "Paid", "Stipend"}), 10, "Published funding or payment"),
        (value["undergraduate_eligible"] == "Yes", 5, "Undergraduate program eligibility"),
        (value["program_type"] in {"Research Internship", "Summer Research", "Visiting Research"}, 5, "Research experience"),
        (value["citizenship_restriction"] == "No", 5, "Confirmed absence of a citizenship restriction"),
    ]
    for enabled, points, reason in bonuses:
        if enabled:
            score += points
            reasons.append(f"+{points}: {reason}")
    return min(100, score), reasons


def get_job(db: Session, owner: str, job_id: int) -> Job | None:
    return db.scalar(select(Job).where(Job.id == job_id, Job.owner_user_id == owner))


def tracking(db: Session, job: Job) -> OpportunityTracking | None:
    return db.scalar(select(OpportunityTracking).where(OpportunityTracking.job_id == job.id, OpportunityTracking.owner_user_id == job.owner_user_id))


def snapshot(db: Session, job: Job, now: datetime | None = None, record=UNLOADED) -> dict:
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if record is UNLOADED:
        record = tracking(db, job)
    details = record.details if record else {}
    defaults = OpportunityInput.model_construct(program=job.title, organization=job.company, official_url=job.canonical_official_url or job.research_url or job.apply_url or job.source_url)
    data = defaults.model_dump(mode="json") | details
    def existing_or_seed(value, key, default=""):
        return value if value and value != "Unknown" else details.get(key, default)
    data.update(program=job.title, organization=job.company, country=existing_or_seed(job.country, "country", "Unknown"), city=existing_or_seed(job.city, "city", "Unknown"), description=existing_or_seed(job.description, "description"), research_areas=existing_or_seed(job.research_areas, "research_areas", []), lab=existing_or_seed(job.lab, "lab"), professor=existing_or_seed(job.supervisor, "professor"), notes=existing_or_seed(job.research_notes, "notes"), deadline=job.application_deadline.isoformat() if job.application_deadline else details.get("deadline"))
    data["official_url"] = defaults.official_url
    data["application_url"] = job.application_url or job.apply_url or ""
    applications = [a for a in job.applications if a.owner_user_id == job.owner_user_id]
    latest = max(applications, key=lambda a: a.id or 0, default=None)
    # Existing Applications remains authoritative for stages it supports; Offer is not Accepted.
    status_changed_at = datetime.fromisoformat(details["status_updated_at"]) if details.get("status_updated_at") else utc(record.created_at) if record else None
    if latest and latest.status in {"Applied", "Interview", "Rejected"} and (data["status"] == "Unknown" or status_changed_at is None or utc(latest.updated_at) > utc(status_changed_at)):
        data["status"] = latest.status
    elif job.status == "applied" and data["status"] == "Unknown":
        data["status"] = "Applied"
    moment = now or datetime.now(timezone.utc)
    exact = datetime.fromisoformat(data["deadline_at"]) if data.get("deadline_at") else None
    past = (exact <= moment if exact else bool(data["deadline"] and data["deadline"] < moment.date().isoformat()))
    if (past or job.status in {"expired", "archived"}) and data["status"] in {"Unknown", "Open", "Not Open Yet"}:
        data["status"] = "Closed"
    data["employment_type"] = job.employment_type or data.get("employment_type", "Unknown")
    data["fit_score"], data["fit_reasons"] = fit(data)
    if data.get("compatibility_level") == "Partial":
        # A recruiter-provided senior role is not an admission/ATS score.
        # Show the assessment and explicit gap instead of fabricated precision.
        data["fit_score"] = None
        data["fit_reasons"] = [data.get("compatibility_notes") or "Partial match; no calibrated compatibility percentage is available."]
    data.pop("status_updated_at", None)
    data.update(id=job.id, created_at=utc(job.first_seen_at).isoformat(), updated_at=max(utc(job.updated_at), utc(record.updated_at)).isoformat() if record else utc(job.updated_at).isoformat())
    return data


def list_opportunities(db: Session, owner: str) -> list[dict]:
    tracked = select(OpportunityTracking.job_id).where(OpportunityTracking.owner_user_id == owner)
    jobs = db.scalars(select(Job).where(Job.owner_user_id == owner, or_(Job.opportunity_type == "research", Job.status.in_(["saved", "applied"]), Job.id.in_(tracked))).options(selectinload(Job.applications)).order_by(Job.id.desc())).all()
    records = {r.job_id: r for r in db.scalars(select(OpportunityTracking).where(OpportunityTracking.owner_user_id == owner))}
    now = datetime.now(timezone.utc)
    return [snapshot(db, job, now, records.get(job.id)) for job in jobs]


def save(db: Session, owner: str, value: OpportunityInput, job: Job | None = None, provenance: dict | None = None) -> tuple[Job, bool]:
    if job is not None and job.owner_user_id != owner:
        raise ValueError("Candidate scope mismatch")
    lock_collection(db, owner)
    jobs = db.scalars(select(Job).where(Job.owner_user_id == owner)).all()
    found = duplicate(jobs, value)
    if found and (job is None or found.id != job.id):
        return found, False
    created = job is None
    if job is None:
        job = Job(owner_user_id=owner, title=value.program, company=value.organization, source_name="manual_research", source_url=value.official_url, opportunity_type="research", status="saved", raw_data_hash=hashlib.sha256(f"{owner}:{value.official_url}".encode()).hexdigest())
        db.add(job)
    else:
        from app.services.discovery_records import snapshot_description
        snapshot_description(db, job)
        if (job.title, job.company, job.canonical_official_url) != (value.program, value.organization, value.official_url):
            job.verification_status, job.official_status = "unverified", "unknown"
    job.title, job.company = value.program, value.organization
    job.country, job.city = value.country, value.city
    job.location = ", ".join(p for p in [value.city, value.country] if p != "Unknown")
    job.description, job.research_areas = value.description, value.research_areas
    if value.employment_type != "Unknown":
        job.employment_type = value.employment_type
    job.lab, job.supervisor, job.research_notes = value.lab, value.professor, value.notes
    job.research_url, job.canonical_official_url = value.official_url, value.official_url
    job.application_url = value.application_url
    job.apply_url = value.application_url or value.official_url
    job.application_deadline = value.deadline
    db.flush()
    record = tracking(db, job)
    if record is None:
        record = OpportunityTracking(job_id=job.id, owner_user_id=owner)
        db.add(record)
    previous = record.details or {}
    status_updated_at = previous.get("status_updated_at") if previous.get("status") == value.status else None
    record.details = value.model_dump(mode="json") | {"status_updated_at": status_updated_at or datetime.now(timezone.utc).isoformat(), "provenance": provenance or {"kind": "manual", "note": "User-provided fields; not independently verified"}}
    record.updated_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    sync_application(db, job, owner, value.status)
    db.flush()
    from app.services.discovery_records import record_discovery
    from app.jobs.refresh import persist_analysis
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner))
    if profile:
        persist_analysis(db, job, profile)
    record_discovery(db, job, {"source_name": job.source_name, "source_url": job.source_url, "original_source_url": value.official_url, "external_id": job.external_id})
    return job, created


def sync_application(db: Session, job: Job, owner: str, status: str):
    if job.owner_user_id != owner:
        raise ValueError("Candidate scope mismatch")
    # Keep the existing Applications view in sync for supported workflow stages.
    if status in {"Applied", "Interview", "Rejected"}:
        application = max([a for a in job.applications if a.owner_user_id == owner], key=lambda a: a.id or 0, default=None)
        if application is None:
            application = Application(owner_user_id=owner, job=job, company=job.company)
            db.add(application)
        if application.status != status:
            application.status_history = list(application.status_history or []) + [{"status": status, "at": datetime.now(timezone.utc).isoformat(), "source": "opportunities_dashboard"}]
        application.status = status
        if status == "Applied":
            job.status = "applied"
            job.applied_at = job.applied_at or datetime.now(timezone.utc)
            application.applied_at = application.applied_at or job.applied_at
    db.flush()
