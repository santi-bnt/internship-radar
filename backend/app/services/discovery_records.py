"""Discovery provenance, conservative facts and canonical projections over Job."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from urllib.parse import urlsplit
from sqlalchemy import select, func
from app.models import CompanySource, JobDescriptionSnapshot, OpportunityDiscoveryState, OpportunitySourceObservation, OpportunityTracking


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def detect_ats(url):
    host = (urlsplit(url or "").hostname or "").lower()
    for ats, domains in {
        "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
        "lever": ("jobs.lever.co",), "ashby": ("jobs.ashbyhq.com",),
        "smartrecruiters": ("jobs.smartrecruiters.com",),
    }.items():
        if host in domains:
            return ats
    if host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")):
        return "workday"
    return "unknown"


def opportunity_ats(value):
    for field in ("application_url", "apply_url", "canonical_official_url", "posting_url"):
        url = value.get(field, "") if isinstance(value, dict) else getattr(value, field, "")
        kind = detect_ats(url)
        if kind != "unknown":
            return kind
    return "unknown"


def state_for(db, job):
    state = db.scalar(select(OpportunityDiscoveryState).where(OpportunityDiscoveryState.job_id == job.id, OpportunityDiscoveryState.owner_user_id == job.owner_user_id))
    if state is None:
        state = OpportunityDiscoveryState(job_id=job.id, owner_user_id=job.owner_user_id, availability="UNKNOWN", facts={})
        db.add(state)
    return state


def snapshot_description(db, job, now=None):
    if not job.description:
        return
    digest = sha256(job.description.encode()).hexdigest()
    if db.scalar(select(JobDescriptionSnapshot.id).where(JobDescriptionSnapshot.job_id == job.id, JobDescriptionSnapshot.owner_user_id == job.owner_user_id, JobDescriptionSnapshot.content_hash == digest)) is None:
        db.add(JobDescriptionSnapshot(job_id=job.id, owner_user_id=job.owner_user_id, content_hash=digest, description=job.description, source_url=job.canonical_official_url or job.source_url, recorded_at=now or datetime.now(timezone.utc)))
        db.flush()


def eligibility_facts(job):
    text = " ".join((job.description or "", job.requirements or ""))
    verified = job.verification_status == "verified" and bool(job.canonical_official_url or job.official_apply_url)
    facts = {"internationalEligibility": "unknown", "visaSponsorship": "unknown", "canApplyFromMexico": "unknown", "studentLevel": "Unknown", "eligibilityEvidence": [], "eligibilitySourceUrl": ""}
    rules = (
        (r"(?:open to|accepts?|eligible for|welcome)[^.\n]{0,60}international (?:undergraduate )?students", "internationalEligibility", "confirmed" if verified else "likely"),
        (r"(?:international (?:undergraduate )?students)[^.\n]{0,70}(?:eligible|welcome|may apply|can apply|accepted)", "internationalEligibility", "confirmed" if verified else "likely"),
        (r"(?:visa sponsorship (?:is )?(?:available|provided)|(?:provide|offers?) visa sponsorship)", "visaSponsorship", "yes" if verified else "unknown"),
        (r"(?:no visa sponsorship|(?:cannot|does not|do not|will not) (?:provide|offer|sponsor)[^.\n]{0,40}(?:visa|sponsorship))", "visaSponsorship", "no" if verified else "unknown"),
        (r"(?:visa sponsorship (?:is )?not required|no visa sponsorship (?:is )?required)", "visaSponsorship", "notRequired" if verified else "unknown"),
        (r"(?:not open to international (?:undergraduate )?students|international (?:undergraduate )?students[^.\n]{0,40}(?:not eligible|may not apply|cannot apply))", "internationalEligibility", "notEligible" if verified else "unknown"),
        (r"(?:u\.?s\.? citizenship (?:is )?required|must be (?:a )?(?:u\.?s\.?|united states) citizen|(?:u\.?s\.?|united states) citizens only)", "internationalEligibility", "notEligible" if verified else "unknown"),
    )
    for pattern, key, value in rules:
        match = re.search(pattern, text, re.I)
        if match:
            facts[key] = value
            facts["eligibilityEvidence"].append(match.group(0))
    if re.search(r"\b(undergraduate|bachelor(?:'s)?)\b", text, re.I):
        facts["studentLevel"] = "Undergraduate" if re.search(r"\bundergraduate\b", text, re.I) else "Bachelor"
    elif re.search(r"\b(ph\.?d|doctoral)\b", text, re.I):
        facts["studentLevel"] = "PhD"
    elif re.search(r"\bmaster(?:'s)?\b", text, re.I):
        facts["studentLevel"] = "Master"
    if facts["internationalEligibility"] == "notEligible":
        facts["canApplyFromMexico"] = "no" if verified else "unknown"
    elif facts["internationalEligibility"] == "confirmed":
        facts["canApplyFromMexico"] = "likely"  # Other program conditions still apply.
    mexico_exclusion = re.search(r"(?:excluding (?:Mexico|Mexican students)|Mexican (?:students|citizens|applicants)[^.\n]{0,30}(?:not eligible|excluded|may not apply))", text, re.I)
    if mexico_exclusion:
        facts["canApplyFromMexico"] = "no" if verified else "unknown"
        facts["eligibilityEvidence"].append(mexico_exclusion.group(0))
    if facts["eligibilityEvidence"]:
        facts["eligibilitySourceUrl"] = job.canonical_official_url or job.source_url
    return facts


def record_discovery(db, job, data, now=None):
    now = now or datetime.now(timezone.utc)
    source = data.get("discovered_from_source") or data.get("source_name") or "Unknown"
    url = (data.get("raw_data") or {}).get("_discovered_url") or data.get("original_source_url") or data.get("source_url") or ""
    key = sha256(f"{source}:{url}".encode()).hexdigest()
    observation = db.scalar(select(OpportunitySourceObservation).where(OpportunitySourceObservation.job_id == job.id, OpportunitySourceObservation.owner_user_id == job.owner_user_id, OpportunitySourceObservation.observation_key == key))
    if observation is None:
        source_id = ((data.get("raw_data") or {}).get("_discovery_metadata") or {}).get("sourceExternalId") or data.get("external_id")
        observation = OpportunitySourceObservation(job_id=job.id, owner_user_id=job.owner_user_id, observation_key=key, source=source, source_url=url, external_id=source_id, first_seen_at=now)
        db.add(observation)
    observation.last_seen_at = now
    official_source = data.get("source_name")
    official_url = data.get("canonical_official_url") or data.get("official_apply_url")
    if official_source and official_source != source and official_url and data.get("verification_status") == "verified":
        official_key = sha256(f"{official_source}:{official_url}".encode()).hexdigest()
        official_observation = db.scalar(select(OpportunitySourceObservation).where(OpportunitySourceObservation.job_id == job.id, OpportunitySourceObservation.owner_user_id == job.owner_user_id, OpportunitySourceObservation.observation_key == official_key))
        if official_observation is None:
            official_observation = OpportunitySourceObservation(job_id=job.id, owner_user_id=job.owner_user_id, observation_key=official_key, source=official_source, source_url=official_url, external_id=data.get("external_id"), first_seen_at=now)
            db.add(official_observation)
        official_observation.last_seen_at = now
    snapshot_description(db, job, now)
    state = state_for(db, job)
    if job.official_status in {"closed", "unavailable", "expired"}:
        state.availability = "CLOSED"
        state.closed_at = state.closed_at or now
    elif job.official_status == "open":
        state.availability, state.closed_at = "ACTIVE", None
    elif state.availability not in {"CLOSED", "MISSING"}:
        state.availability = "UNKNOWN"
    facts = eligibility_facts(job)
    facts["ats"] = opportunity_ats(job)
    metadata = (data.get("raw_data") or {}).get("_discovery_metadata", {})
    if metadata.get("attribution"):
        facts["attribution"] = str(metadata["attribution"])[:1000]
    state.facts = (state.facts or {}) | facts
    register_discovered_board(db, job)
    return state


def register_discovered_board(db, job):
    """Only a verified posting can nominate a board for the existing catalog."""
    url = job.canonical_official_url or job.apply_url
    kind = detect_ats(url)
    if kind == "unknown" or job.verification_status != "verified":
        return
    parsed = urlsplit(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return
    if kind == "smartrecruiters" and parts[0] == "ni":
        parts = parts[1:]
    board = parts[0]
    if kind == "workday":
        if re.fullmatch(r"[a-z]{2}-[A-Z]{2}", board) and len(parts) > 1:
            board = parts[1]
        board = f"{parsed.hostname.split('.')[0]}|{board}"
    existing = db.scalar(select(CompanySource).where(CompanySource.owner_user_id == job.owner_user_id, CompanySource.source_type == kind, func.lower(CompanySource.source_identifier) == board.lower()))
    if existing is None:
        db.add(CompanySource(owner_user_id=job.owner_user_id, company=job.company, source_type=kind, source_identifier=board,
            source_url=f"https://{parsed.netloc}/{board.split('|')[-1]}", registry_type="OFFICIAL_ATS",
            enabled=True, reference_only=False, supports_structured_data=True,
            notes=f"Discovered via verified posting {url}; full board fetch is pending.", geography_scope="US_CANADA" if job.country in {"United States", "Canada"} else "OTHER"))
        db.flush()


def record_absence(db, job, *, complete_snapshot, now=None):
    if not complete_snapshot:
        return
    state = state_for(db, job)
    state.availability = "CLOSED" if not job.is_active else "MISSING"
    if state.availability == "CLOSED":
        state.closed_at = state.closed_at or now or datetime.now(timezone.utc)


def canonical_opportunity(db, job, *, new_days=3, now=None):
    now = now or datetime.now(timezone.utc)
    state = db.scalar(select(OpportunityDiscoveryState).where(OpportunityDiscoveryState.job_id == job.id, OpportunityDiscoveryState.owner_user_id == job.owner_user_id))
    facts = dict(state.facts or {}) if state else eligibility_facts(job)
    tracking = db.scalar(select(OpportunityTracking).where(OpportunityTracking.job_id == job.id, OpportunityTracking.owner_user_id == job.owner_user_id))
    if tracking:
        details = tracking.details or {}
        funding = [f for f in details.get("funding", []) if f != "Unknown"]
        if funding:
            facts["fundingType"] = ", ".join(funding)
        facts["recommendationLetters"] = details.get("recommendation_letters", "Unknown")
    analysis = job.analysis
    fit = round(analysis.technical_score * .65 + analysis.academic_score * .15 + analysis.level_score * .10 + analysis.logistics_score * .10, 1) if analysis else None
    eligibility = analysis.eligibility_score if analysis else None
    if facts.get("internationalEligibility") == "notEligible":
        eligibility = min(eligibility or 0, 10)
    observations = db.scalars(select(OpportunitySourceObservation).where(OpportunitySourceObservation.job_id == job.id, OpportunitySourceObservation.owner_user_id == job.owner_user_id)).all()
    availability = "CLOSED" if job.official_status in {"closed", "unavailable", "expired"} else "ACTIVE" if job.official_status == "open" else (state.availability or "UNKNOWN") if state else "UNKNOWN"
    areas = list(job.research_areas or [])
    if not areas:
        text = f"{job.title} {job.description}".lower()
        areas = [area for area, signals in {
            "Robotics": ("robotics", "robotic"), "Artificial Intelligence": ("artificial intelligence", "machine learning", "ai"),
            "Embedded Systems": ("embedded", "firmware"), "FPGA": ("fpga", "verilog"),
            "IoT": ("internet of things", "iot"), "Autonomous Systems": ("autonomous systems",),
            "Control": ("control systems", "pid control"), "Computer Vision": ("computer vision",),
        }.items() if any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in signals)]
    return {
        "id": job.id, "externalId": job.external_id, "title": job.title, "company": job.company, "organization": job.company,
        "location": job.location, "country": job.country or "Unknown", "remoteType": job.remote_type,
        "description": job.description, "canonicalUrl": job.canonical_official_url or job.official_apply_url or job.posting_url or job.apply_url,
        "applicationUrl": job.application_url or job.apply_url, "sourceName": job.source_name, "sourceUrl": (job.raw_data or {}).get("_discovered_url") or job.source_url,
        "discoveredFrom": job.discovered_from_source or job.source_name, "ats": facts.get("ats", opportunity_ats(job)),
        "postedAt": utc(job.posted_at), "firstSeenAt": utc(job.first_seen_at), "lastSeenAt": utc(job.last_seen_at), "lastCheckedAt": utc(job.last_checked_at),
        "closedAt": utc(state.closed_at) if state else None, "status": availability, "applicationStatus": job.status,
        "opportunityType": job.opportunity_type, "researchAreas": areas,
        "skills": analysis.matched_skills if analysis else [], "studentLevel": facts.get("studentLevel", "Unknown"),
        "internationalEligibility": facts.get("internationalEligibility", "unknown"), "visaSponsorship": facts.get("visaSponsorship", "unknown"),
        "canApplyFromMexico": facts.get("canApplyFromMexico", "unknown"), "eligibilityEvidence": facts.get("eligibilityEvidence", []), "eligibilitySourceUrl": facts.get("eligibilitySourceUrl", ""),
        "fundingType": facts.get("fundingType", "Unknown"), "salaryMin": facts.get("salaryMin"), "salaryMax": facts.get("salaryMax"), "currency": facts.get("currency"),
        "housingSupport": facts.get("housingSupport", "Unknown"), "travelSupport": facts.get("travelSupport", "Unknown"), "recommendationLetters": facts.get("recommendationLetters", "Unknown"),
        "deadline": job.application_deadline, "fitScore": fit, "eligibilityScore": eligibility, "freshnessScore": analysis.freshness_score if analysis else None,
        "verificationStatus": job.verification_status, "duplicateConfidence": state.duplicate_confidence if state else None, "duplicateCandidateId": state.duplicate_candidate_id if state else None,
        "isNew": bool(job.first_seen_at and utc(job.first_seen_at) >= now - timedelta(days=new_days)),
        "rawMetadata": {"source": job.source_name, "attribution": facts.get("attribution"), "sourceUpdatedAt": (job.raw_data or {}).get("updated_at")},
        "observations": [{"source": o.source, "sourceUrl": o.source_url, "externalId": o.external_id, "firstSeenAt": utc(o.first_seen_at), "lastSeenAt": utc(o.last_seen_at)} for o in observations],
    }
