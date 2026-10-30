"""Candidate-scoped manual URL import using the normal Job and analysis models."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.refresh import _merge_duplicate, persist_analysis
from app.models import CandidateJobOverride, Job, UserProfile
from app.services.dedupe import same_job
from app.services.force_apply import can_force_apply_now, is_application_confirmed_unavailable, set_force_apply_now
from app.services.normalization import clean_text, normalized_token
from app.services.safe_job_fetch import FetchedPage, JobFetchError, fetch_job_page, validate_job_url
from app.services.target_companies import canonicalize_url
from app.sources.base import NormalizedJob
from app.sources.greenhouse import GreenhouseAdapter
from app.sources.lever import LeverAdapter
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.smartrecruiters import SmartRecruitersAdapter
from app.sources.workday import WorkdayAdapter


class JobExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class JobURLImportResult:
    job: Job
    created: bool
    verified: bool
    force_apply_now: bool
    force_apply_error: str | None = None


def _ats_identity(url: str) -> tuple[str, str, str] | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if ".myworkdayjobs.com" in host and len(parts) >= 3:
        if re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
            parts = parts[1:]
        if parts and parts[0] == "job":
            return None
        # Workday slugs may end with either a numeric requisition plus a
        # locale suffix (e.g. ``Internship_3169469-1``) or a prefixed ID
        # (e.g. ``..._R-10063630``). Preserve the latter in full so the CXS
        # API search and exact jobReqId comparison can find the posting.
        match = re.search(r"_((?:[A-Za-z]+-)?[A-Za-z0-9]+)(?:-\d+)?$", parts[-1])
        if len(parts) >= 2 and match:
            return "workday", parts[0], match.group(1)
    if host in {"job-boards.greenhouse.io", "boards.greenhouse.io"} and len(parts) >= 3:
        if parts[1] == "jobs" and parts[2].isdigit():
            return "greenhouse", parts[0], parts[2]
    if host == "jobs.lever.co" and len(parts) >= 2:
        return "lever", parts[0], parts[1]
    if host == "jobs.smartrecruiters.com" and len(parts) >= 2:
        match = re.match(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[A-Za-z0-9]+)", parts[1])
        if match:
            return "smartrecruiters", parts[0], match.group(1)
    return None


async def _ats_job(url: str) -> NormalizedJob | None:
    identity = _ats_identity(url)
    if not identity:
        return None
    kind, board, public_id = identity
    host = urlsplit(url).hostname or ""
    try:
        if kind == "workday":
            tenant = host.split(".", 1)[0]
            base = f"https://{host}/wday/cxs/{tenant}/{board}"
            listing = await fetch_job_page(
                f"{base}/jobs", method="POST",
                json_body={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": public_id},
            )
            postings = json.loads(listing.text).get("jobPostings", [])
            for item in postings:
                path = item.get("externalPath") or ""
                if not path:
                    continue
                detail = await fetch_job_page(f"{base}{path}")
                raw = json.loads(detail.text).get("jobPostingInfo", {})
                if str(raw.get("jobReqId") or raw.get("jobRequisitionId") or "") != public_id:
                    continue
                raw["_listing"] = item
                raw["externalUrl"] = url
                company = tenant.upper() if len(tenant) <= 3 else tenant.title()
                adapter = WorkdayAdapter(company, f"{tenant}|{board}", f"https://{host}/{board}")
                return adapter.normalize_job(raw)
        elif kind == "greenhouse":
            detail = await fetch_job_page(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{public_id}?content=true")
            raw = json.loads(detail.text)
            company = clean_text(raw.get("company_name") or "").removesuffix(" - Careers")
            if not company:
                raise JobExtractionError("The official job API did not identify the employer.")
            adapter = GreenhouseAdapter(company, board, f"https://job-boards.greenhouse.io/{board}")
            return adapter.normalize_job(raw)
        elif kind == "lever":
            detail = await fetch_job_page(f"https://api.lever.co/v0/postings/{board}/{public_id}")
            raw = json.loads(detail.text)
            employer = raw.get("company") or board
            company = clean_text(employer.get("name") if isinstance(employer, dict) else employer)
            adapter = LeverAdapter(company, board, f"https://jobs.lever.co/{board}")
            return adapter.normalize_job(raw)
        elif kind == "smartrecruiters":
            detail = await fetch_job_page(f"https://api.smartrecruiters.com/v1/companies/{board}/postings/{public_id}")
            raw = json.loads(detail.text)
            employer = raw.get("company") or board
            company = clean_text(employer.get("name") if isinstance(employer, dict) else employer)
            adapter = SmartRecruitersAdapter(company, board, f"https://jobs.smartrecruiters.com/{board}")
            return adapter.normalize_job(raw)
    except (JobFetchError, ValueError, KeyError, TypeError):
        # A temporarily inaccessible ATS API may still have useful JSON-LD or
        # rendered HTML on the public page. Never claim API verification then.
        return None
    return None


def _job_posting_jsonld(soup: BeautifulSoup) -> dict:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidates_in_graph = candidate.get("@graph", [candidate])
            for item in candidates_in_graph if isinstance(candidates_in_graph, list) else []:
                if isinstance(item, dict) and "JobPosting" in str(item.get("@type", "")):
                    return item
    return {}


def _text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return clean_text(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True))


def _official_link(soup: BeautifulSoup, page_url: str) -> str | None:
    source_host = (urlsplit(page_url).hostname or "").lower()
    third_party = ("linkedin.com", "indeed.com", "simplify.jobs")
    if not any(source_host.endswith(domain) for domain in third_party):
        return None
    ats_hosts = ("myworkdayjobs.com", "greenhouse.io", "lever.co", "smartrecruiters.com", "ashbyhq.com")
    for anchor in soup.select("a[href]"):
        href = urljoin(page_url, anchor.get("href", ""))
        host = (urlsplit(href).hostname or "").lower()
        if any(host.endswith(domain) for domain in ats_hosts):
            try:
                return validate_job_url(href)
            except ValueError:
                continue
    return None


def _embedded_source_job(page: FetchedPage) -> dict | None:
    """Extract official job data embedded in JavaScript-rendered careers pages."""
    host = (urlsplit(page.url).hostname or "").lower()
    soup = BeautifulSoup(page.text, "html.parser")

    if host.endswith("jobs.apple.com"):
        for script in soup.select("script"):
            text = script.string or script.get_text()
            marker = "window.__staticRouterHydrationData"
            start = text.find(marker)
            if start < 0:
                continue
            assignment = text[start + len(marker):].lstrip()
            if not assignment.startswith("="):
                continue
            assignment = assignment[1:].lstrip()
            parse_prefix = "JSON.parse("
            if not assignment.startswith(parse_prefix):
                continue
            try:
                encoded, end = json.JSONDecoder().raw_decode(assignment[len(parse_prefix):])
                if not assignment[len(parse_prefix) + end:].lstrip().startswith(")"):
                    continue
                hydration = json.loads(encoded)
            except (TypeError, ValueError):
                continue
            job = (hydration.get("loaderData") or {}).get("jobDetails", {}).get("jobsData")
            if not isinstance(job, dict) or not job.get("jobNumber"):
                continue
            locations = [
                _text(location.get("name") or location.get("countryName"))
                for location in job.get("locations", [])
                if isinstance(location, dict) and location.get("active", True)
            ]
            locale = _text(job.get("selectedLocale") or "en_US").lower().replace("_", "-")
            apply_url = f"https://jobs.apple.com/app/{locale}/apply/{job['jobNumber']}"
            footer_text = " ".join(_text(item) for item in (job.get("postingFooters") or []))
            footer_lower = footer_text.lower()
            if any(term in footer_lower for term in ("no longer accepting", "position has been filled", "posting is closed", "applications are closed")):
                official_status = "closed"
            elif "accepts applications" in footer_lower:
                official_status = "open"
            else:
                official_status = "unknown"
            return {
                "company": "Apple",
                "title": _text(job.get("postingTitle")),
                "external_id": _text(job.get("jobNumber")),
                "location": "; ".join(dict.fromkeys(filter(None, locations))),
                "description": "\n\n".join(filter(None, (
                    _text(job.get("jobSummary")),
                    _text(job.get("description")),
                ))),
                "requirements": _text(job.get("minimumQualifications")),
                "preferred": _text(job.get("preferredQualifications")),
                "employment_type": "Internship" if "intern" in _text(job.get("postingTitle")).lower() else "Unknown",
                "posted_at": job.get("postingDate"),
                "expires_at": None,
                "apply_url": apply_url,
                "official_status": official_status,
            }

    if host.endswith("tesla.com"):
        for script in soup.select("script"):
            text = script.string or script.get_text()
            marker = "window.tesla = "
            start = text.find(marker)
            if start < 0:
                continue
            payload = text[start + len(marker):].lstrip()
            try:
                state, _ = json.JSONDecoder().raw_decode(payload)
            except (TypeError, ValueError):
                continue
            jobs = (
                state.get("App", {})
                .get("initialReduxState", {})
                .get("root", {})
                .get("jobs", {})
                .get("data", {})
            )
            path_id = urlsplit(page.url).path.rsplit("-", 1)[-1]
            if not path_id.isdigit():
                continue
            job = jobs.get(path_id)
            if not isinstance(job, dict) or not job.get("title") or not job.get("jobDescription"):
                continue
            description = "\n\n".join(filter(None, (
                _text(job.get("jobDescription")),
                _text(job.get("jobResponsibilities")),
                _text(job.get("jobRequirements")),
            )))
            req_id = _text(job.get("id") or path_id)
            return {
                "company": "Tesla",
                "title": _text(job.get("title")),
                "external_id": req_id,
                "location": _text(job.get("location")),
                "description": description,
                "requirements": _text(job.get("jobRequirements")),
                "preferred": "",
                "responsibilities": _text(job.get("jobResponsibilities")),
                "employment_type": _text(job.get("subWorkerType") or "Internship"),
                "posted_at": None,
                "expires_at": job.get("postUntilDate"),
                "apply_url": f"https://www.tesla.com/careers/search/job/apply/{req_id}",
                "official_status": "open",
            }
    return None


def _generic_job(page: FetchedPage) -> tuple[NormalizedJob, str | None]:
    soup = BeautifulSoup(page.text, "html.parser")
    official_link = _official_link(soup, page.url)
    structured = _job_posting_jsonld(soup)
    embedded = _embedded_source_job(page) or {}
    title = _text(
        embedded.get("title")
        or structured.get("title")
        or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
        or (soup.find("meta", property="og:title") or {}).get("content")
    )
    organization = structured.get("hiringOrganization") or {}
    host = (urlsplit(page.url).hostname or "").lower()
    embedded_company = embedded.get("company")
    third_party = any(host.endswith(domain) for domain in ("linkedin.com", "indeed.com", "simplify.jobs"))
    company = _text(embedded_company or (organization.get("name") if isinstance(organization, dict) else organization))
    if not company and not third_party:
        company = _text((soup.find("meta", property="og:site_name") or {}).get("content"))
    location_node = structured.get("jobLocation") or {}
    if isinstance(location_node, list):
        location_node = location_node[0] if location_node else {}
    address = location_node.get("address", {}) if isinstance(location_node, dict) else {}
    location = _text(
        embedded.get("location")
        or (", ".join(str(address.get(key) or "") for key in ("addressLocality", "addressRegion", "addressCountry") if address.get(key))
            if isinstance(address, dict) else "")
    )
    description = _text(embedded.get("description") or structured.get("description"))
    if len(description) < 80:
        content = soup.find("main") or soup.find("article") or soup.body
        if content:
            for item in content.select("script, style, nav, footer, header"):
                item.decompose()
            description = _text(content.get_text(" ", strip=True))[:30_000]
    requirements = _text(
        embedded.get("requirements")
        or structured.get("qualifications")
        or structured.get("educationRequirements")
    )
    responsibilities = _text(embedded.get("responsibilities") or structured.get("responsibilities"))
    if responsibilities and responsibilities not in description:
        description = f"{description}\nResponsibilities: {responsibilities}"
    preferred = _text(embedded.get("preferred") or structured.get("preferredQualifications"))
    if not company or not title or len(description) < 80:
        raise JobExtractionError("Internship Radar could not reliably extract this job posting.")
    page_text = _text(soup.get_text(" ", strip=True)).lower()
    closed = bool(embedded.get("official_status") == "closed") or any(term in page_text for term in (
        "job is no longer available", "no longer accepting applications", "position has been filled", "job has expired",
    ))
    expires_at = embedded.get("expires_at") or structured.get("validThrough")
    if expires_at:
        try:
            expiration_date = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).date()
            if expiration_date < datetime.now(timezone.utc).date():
                closed = True
        except (TypeError, ValueError):
            pass
    apply_link = embedded.get("apply_url") or next(
        (urljoin(page.url, anchor.get("href", "")) for anchor in soup.select("a[href]")
         if re.search(r"\bapply\b", anchor.get_text(" ", strip=True), re.I)),
        None,
    )
    if apply_link:
        try:
            apply_link = validate_job_url(apply_link)
        except ValueError:
            apply_link = None
    official = not third_party
    source_status = embedded.get("official_status")
    verified = (
        official and bool(apply_link) and not closed
        and (source_status == "open" or (not embedded and source_status is None))
    )
    status = "closed" if closed else "open" if verified else "unknown"
    identifier = structured.get("identifier") or {}
    external_id = _text(embedded.get("external_id")) or _text(
        identifier.get("value") if isinstance(identifier, dict) else identifier
    ) or None
    if not external_id and _ats_identity(page.url):
        external_id = _ats_identity(page.url)[2]
    adapter = OfficialCareersAdapter(company, "manual_url", page.url)
    normalized = adapter.build_job(
        {"url": page.url, "title": title, "import_method": "manual_url"},
        external_id=external_id, title=title, location=location, description=description,
        requirements=requirements, preferred_qualifications=preferred,
        apply_url=apply_link or page.url, original_source_url=page.url,
        official_apply_url=(apply_link or page.url) if official and not closed else None,
        official_status=status, verification_status="verified" if verified or closed else "unverified",
        verification_method="manual_url_embedded_state" if embedded else "manual_url_html",
        last_verified_at=datetime.now(timezone.utc) if verified or closed else None,
        status_reason=(
            "The posting says the application is closed." if closed else
            "Official job page exposed active application details." if verified else
            "Application availability needs verification."
        ),
        employment_type=_text(embedded.get("employment_type") or structured.get("employmentType")) or "Unknown",
        posted_at=embedded.get("posted_at") or structured.get("datePosted"),
        expires_at=expires_at,
        discovered_from_source="manual_url", discovery_sources=["manual_url"], is_active=not closed,
    )
    return normalized, official_link


async def extract_job_url(url: str) -> NormalizedJob:
    submitted = validate_job_url(url)
    ats = await _ats_job(submitted)
    if ats and len(ats.description) >= 80:
        return ats
    page = await fetch_job_page(submitted)
    if page.status_code in {404, 410}:
        raise JobExtractionError("The official application appears closed or removed.")
    if page.status_code >= 400:
        raise JobExtractionError("Internship Radar could not reliably extract this job posting.")
    official_link = _official_link(BeautifulSoup(page.text, "html.parser"), page.url)
    if official_link:
        official = await _ats_job(official_link)
        if official is None:
            try:
                official_page = await fetch_job_page(official_link)
                if official_page.status_code == 200:
                    official, _ = _generic_job(official_page)
            except (JobFetchError, JobExtractionError):
                pass
        if official and len(official.description) >= 80:
            return official
    generic, _ = _generic_job(page)
    return generic


def _find_canonical(existing: list[Job], candidate: NormalizedJob, submitted_url: str) -> Job | None:
    candidate_ids = {str(item) for item in (candidate.external_id, candidate.ats_requisition_id) if item}
    company = normalized_token(candidate.company)
    candidate_ats = _ats_identity(candidate.original_source_url or submitted_url)

    def identity_conflicts(job: Job) -> bool:
        for field in ("external_id", "ats_requisition_id"):
            incoming = getattr(candidate, field, None)
            stored = getattr(job, field, None)
            if incoming and stored and str(incoming) != str(stored):
                return True
        stored_ats = _ats_identity(job.original_source_url or job.apply_url)
        # An ATS employer/tenant plus a different requisition is a distinct
        # posting even if a stale URL or similar title points at this record.
        return bool(
            candidate_ats and stored_ats
            and candidate_ats[:2] == stored_ats[:2]
            and candidate_ats[2] != stored_ats[2]
        )

    for job in existing:
        if identity_conflicts(job):
            continue
        stored_ids = {str(item) for item in (job.external_id, job.ats_requisition_id) if item}
        stored_ats = _ats_identity(job.original_source_url or job.apply_url)
        same_ats = bool(candidate_ats and stored_ats and candidate_ats == stored_ats)
        if candidate_ids & stored_ids and (normalized_token(job.company) == company or same_ats):
            return job
    urls = {canonicalize_url(item) for item in (
        submitted_url, candidate.apply_url, candidate.original_source_url, candidate.canonical_official_url,
    ) if item}
    for job in existing:
        if identity_conflicts(job):
            continue
        stored_urls = (job.apply_url, job.posting_url, job.original_source_url, job.canonical_official_url,
                       *(item.get("submitted_url") or item.get("apply_url") for item in job.alternate_sources or []))
        if urls & {canonicalize_url(item) for item in stored_urls if item}:
            return job
    for job in existing:
        if identity_conflicts(job):
            continue
        stored_ids = {str(item) for item in (job.external_id, job.ats_requisition_id) if item}
        if candidate_ids and stored_ids and not candidate_ids & stored_ids:
            continue
        if same_job(job, candidate):
            return job
    return None


def persist_imported_job(
    db: Session, normalized: NormalizedJob, submitted_url: str,
    owner_user_id: str, force_apply_now: bool, *, commit: bool = True,
) -> JobURLImportResult:
    profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == owner_user_id))
    if profile is None:
        raise JobExtractionError("The selected candidate profile is unavailable.")
    existing = list(db.scalars(select(Job).where(Job.owner_user_id == owner_user_id)))
    job = _find_canonical(existing, normalized, submitted_url)
    created = job is None
    data = normalized.to_dict()
    data["owner_user_id"] = owner_user_id
    if created:
        job = Job(**data)
        if normalized.official_status in {"closed", "expired", "unavailable"}:
            job.status = "expired"
            job.is_active = False
            job.expired_at = datetime.now(timezone.utc)
        db.add(job)
        db.flush()
    else:
        # Preserve candidate lifecycle and attachments while enriching weak
        # source metadata through the same merge used by normal discovery.
        state = {field: getattr(job, field) for field in (
            "status", "is_active", "applied_at", "archived_at", "expired_at", "submitted_resume_id",
        )}
        existing_content = {field: getattr(job, field) for field in (
            "description", "requirements", "preferred_qualifications",
        )}
        if (
            len(normalized.description) > len(job.description or "")
            or not job.official_apply_url
            or normalized.verification_status == "verified"
        ):
            _merge_duplicate(job, data)
            for field, previous in existing_content.items():
                if len(previous or "") > len(getattr(job, field) or ""):
                    setattr(job, field, previous)
        for field, value in state.items():
            setattr(job, field, value)
        if state["status"] == "expired" and normalized.official_status == "open" and normalized.verification_status == "verified":
            job.status = "active"
            job.is_active = True
            job.expired_at = None
        elif state["status"] != "applied" and normalized.official_status in {"closed", "expired", "unavailable"} and normalized.verification_status == "verified":
            job.status = "expired"
            job.is_active = False
            job.expired_at = datetime.now(timezone.utc)
    sources = list(job.alternate_sources or [])
    if not any(canonicalize_url(item.get("submitted_url", "")) == canonicalize_url(submitted_url) for item in sources):
        sources.append({"source_name": "manual_url", "submitted_url": submitted_url,
                        "apply_url": submitted_url, "discovered_at": datetime.now(timezone.utc).isoformat()})
        job.alternate_sources = sources
    raw = dict(job.raw_data or {})
    raw["import_method"] = "manual_url"
    raw["last_submitted_url"] = submitted_url
    job.raw_data = raw
    persist_analysis(db, job, profile)
    override_error = None
    if force_apply_now:
        if str(job.status or "").casefold() == "applied":
            override_error = "This job is already marked Applied; its application history was preserved."
        elif not can_force_apply_now(job):
            override_error = (
                "Cannot enable Apply Now because the official application is closed."
                if is_application_confirmed_unavailable(job)
                else "Cannot enable Apply Now without a usable application URL."
            )
        else:
            if job.status not in {"active", "saved"} or not job.is_active:
                job.status = "active"
                job.is_active = True
                job.archived_at = None
                job.expired_at = None
            override = db.scalar(select(CandidateJobOverride).where(
                CandidateJobOverride.owner_user_id == owner_user_id,
                CandidateJobOverride.job_id == job.id,
            ))
            if override is None:
                override = CandidateJobOverride(owner_user_id=owner_user_id, job_id=job.id)
                db.add(override)
                job.candidate_job_override = override
            set_force_apply_now(override, True)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(job)
    return JobURLImportResult(
        job=job, created=created,
        verified=job.verification_status == "verified" and job.official_status == "open",
        force_apply_now=bool(job.candidate_job_override and job.candidate_job_override.force_apply_now),
        force_apply_error=override_error,
    )


def persist_imported_job_for_all_profiles(
    db: Session, normalized: NormalizedJob, submitted_url: str,
    importing_user_id: str, force_apply_now: bool,
) -> JobURLImportResult:
    """Make a URL-imported opportunity available with independent analysis per profile.

    Jobs are candidate-owned in the current data model, so each profile receives
    its own canonical job row and analysis. Existing per-candidate lifecycle,
    application history, and overrides are preserved by the normal upsert path.
    """
    profiles = list(db.scalars(
        select(UserProfile)
        .order_by(UserProfile.owner_user_id)
        .execution_options(skip_owner_scope=True)
    ))
    if not any(profile.owner_user_id == importing_user_id for profile in profiles):
        raise JobExtractionError("The selected candidate profile is unavailable.")

    importing_result: JobURLImportResult | None = None
    previous_scope = db.info.get("owner_user_id")
    try:
        for profile in profiles:
            # This scoped, server-side fanout is intentional: each profile is
            # re-evaluated with its own facts and only its own job row is read.
            db.info["owner_user_id"] = profile.owner_user_id
            result = persist_imported_job(
                db,
                normalized,
                submitted_url,
                profile.owner_user_id,
                force_apply_now and profile.owner_user_id == importing_user_id,
                commit=False,
            )
            if profile.owner_user_id == importing_user_id:
                importing_result = result

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if previous_scope is None:
            db.info.pop("owner_user_id", None)
        else:
            db.info["owner_user_id"] = previous_scope

    assert importing_result is not None
    db.refresh(importing_result.job)
    return importing_result
