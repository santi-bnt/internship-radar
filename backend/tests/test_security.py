from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.init_db import _consolidate_primary_identity
from app.main import app
from app.models import Job, JobAnalysis, ResumeProfile, UserProfile
from app.services.resume_generation import generate_local_content
from app.security.identity import (
    IdentityValidationError,
    JOSHUA_EMAIL,
    JOSHUA_USER_ID,
    is_authorized_email,
    resolve_primary_user,
    validate_user_identity,
)
from app.security.rate_limit import RateLimitRule, check_rate_limit
from conftest import security_headers


AUTHORIZED_EMAILS = (
    "candidate@example.com",
    "alerts@example.com",
    "alternate@example.com",
)


def test_health_is_public_and_contains_only_safe_status_fields():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert set(response.json()) == {
        "status",
        "database",
        "latex_compiler",
        "scheduler",
        "last_successful_search",
    }
    serialized = response.text.lower()
    assert "@gmail.com" not in serialized
    assert "secret" not in serialized
    assert "database_url" not in serialized


def test_private_api_requires_both_service_and_signed_user_identity():
    with TestClient(app) as client:
        assert client.get("/api/jobs").status_code == 401
        only_service = client.get(
            "/api/jobs",
            headers={"x-internal-api-secret": settings.internal_api_secret},
        )
        assert only_service.status_code == 401
        raw_email = client.get(
            "/api/jobs",
            headers={
                "x-internal-api-secret": settings.internal_api_secret,
                "x-user-email": AUTHORIZED_EMAILS[0],
            },
        )
        assert raw_email.status_code == 401


def test_three_authorized_emails_resolve_to_same_primary_user():
    for email in AUTHORIZED_EMAILS:
        assert is_authorized_email(email.upper())
        assert resolve_primary_user(f" {email} ") == settings.primary_user_id
        identity = validate_user_identity(security_headers(email)["x-user-identity"])
        assert identity.primary_user_id == settings.primary_user_id
        assert identity.authenticated_email == email


def test_joshua_resolves_to_an_independent_account_and_profile():
    assert is_authorized_email(JOSHUA_EMAIL)
    assert resolve_primary_user(JOSHUA_EMAIL) == JOSHUA_USER_ID
    identity = validate_user_identity(security_headers(
        JOSHUA_EMAIL, subject=JOSHUA_USER_ID
    )["x-user-identity"])
    assert identity.primary_user_id == JOSHUA_USER_ID
    assert identity.primary_user_id != settings.primary_user_id
    with TestClient(app, headers=security_headers(
        JOSHUA_EMAIL, subject=JOSHUA_USER_ID
    )) as client:
        response = client.get("/api/profile")
        jobs_response = client.get("/api/jobs")
        application_profile_response = client.get("/api/application-profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["full_name"].startswith("Taylor Morgan")
    assert payload["official_degree_name"] == "B.S. in Robotics and Digital Systems Engineering"
    assert payload["expected_graduation_date"] == "2028-06-30"
    assert payload["nationality"] == "Mexican"
    assert payload["citizenship_country"] == "Mexico"
    assert payload["gpa"] == 3.7
    assert payload["gpa_scale"] == 4.0
    assert payload["gpa_scale_status"] == "CONFIRMED"
    assert payload["us_authorization_conflict_detected"] is True
    assert payload["only_remote"] is False
    assert payload["include_hybrid"] is True
    assert payload["include_onsite"] is True
    assert "Santiago" not in response.text
    assert jobs_response.status_code == 200
    assert jobs_response.json()["total"] > 0
    assert application_profile_response.status_code == 200
    assert application_profile_response.json()["gpa"] == 3.7
    assert application_profile_response.json()["gpa_scale"] == 4.0
    assert application_profile_response.json()["languages_json"] == [
        "Spanish — Native", "English — Fluent"
    ]
    assert any(
        (item.get("analysis") or {}).get("overall_score", 0) > 0
        for item in jobs_response.json()["items"]
    )
    with SessionLocal() as db:
        resume_profile = db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == JOSHUA_USER_ID
        ))
        job = db.scalar(select(Job).where(
            Job.owner_user_id == JOSHUA_USER_ID,
            Job.description != "",
        ))
        assert resume_profile and job
        assert resume_profile.languages_json == ["Spanish — Native", "English — Fluent"]
        content = generate_local_content(job, resume_profile)
        assert "verified" not in content.summary.lower()


def test_joshua_job_reads_are_read_only_and_do_not_create_analyses():
    headers = security_headers(JOSHUA_EMAIL, subject=JOSHUA_USER_ID)
    with TestClient(app, headers=headers) as client:
        with SessionLocal() as db:
            joshua_job_ids = select(Job.id).where(Job.owner_user_id == JOSHUA_USER_ID)
            db.execute(delete(JobAnalysis).where(JobAnalysis.job_id.in_(joshua_job_ids)))
            db.commit()
        assert client.get("/api/jobs?active=true&page_size=6").status_code == 200
        assert client.get("/api/jobs?active=true&page_size=50").status_code == 200
        with SessionLocal() as db:
            remaining = db.scalar(select(func.count(JobAnalysis.id)).join(Job).where(
                Job.owner_user_id == JOSHUA_USER_ID
            ))
        assert remaining == 0


def test_legacy_joshua_resume_identity_is_not_merged_into_santiago():
    with SessionLocal() as db:
        db.add(ResumeProfile(
            user_id=JOSHUA_EMAIL,
            full_name="Legacy Joshua",
            email=JOSHUA_EMAIL,
        ))
        db.commit()
    _consolidate_primary_identity()
    with SessionLocal() as db:
        assert db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == JOSHUA_EMAIL
        )) is None
        assert db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == JOSHUA_USER_ID
        )) is not None
        assert db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == settings.primary_user_id
        )) is not None


def test_existing_primary_id_wins_over_a_legacy_row_with_canonical_email():
    legacy_id = "alerts@example.com"
    with SessionLocal() as db:
        primary = db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == settings.primary_user_id
        ))
        assert primary
        primary.email = "older-primary@example.com"
        db.add(ResumeProfile(
            user_id=legacy_id,
            full_name="Polluted legacy row",
            email=settings.resume_email,
        ))
        db.commit()
    _consolidate_primary_identity()
    with SessionLocal() as db:
        assert db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == legacy_id
        )) is None
        primary = db.scalar(select(ResumeProfile).where(
            ResumeProfile.user_id == settings.primary_user_id
        ))
        assert primary
        assert primary.full_name != "Polluted legacy row"


def test_allowlist_rejects_partial_and_unverified_identity_values():
    rejected = (
        "attacker+candidate@example.com",
        "fake-alerts@example.com",
        "candidate@example.com.attacker.test",
        "",
    )
    assert all(not is_authorized_email(email) for email in rejected)


def test_bad_signature_and_expired_identity_are_rejected():
    valid = security_headers()["x-user-identity"]
    payload, signature = valid.split(".")
    with TestClient(app) as client:
        bad_signature = client.get(
            "/api/jobs",
            headers={
                "x-internal-api-secret": settings.internal_api_secret,
                "x-user-identity": f"{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}",
            },
        )
        expired = client.get("/api/jobs", headers=security_headers(expires_offset=-1))
    assert bad_signature.status_code == 401
    assert expired.status_code == 401
    replacement = "A" if signature[-1] != "A" else "B"
    try:
        validate_user_identity(f"{payload}.{signature[:-1]}{replacement}")
    except IdentityValidationError:
        pass
    else:
        raise AssertionError("A manipulated identity token was accepted.")


def test_authorized_accounts_share_profile_without_creating_duplicates():
    payloads = []
    for email in AUTHORIZED_EMAILS:
        with TestClient(app, headers=security_headers(email)) as client:
            response = client.get("/api/resume-profile")
        assert response.status_code == 200
        payloads.append(response.json())
    assert {payload["id"] for payload in payloads} == {payloads[0]["id"]}
    assert all(payload["email"] == settings.resume_email for payload in payloads)
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(ResumeProfile.id)).where(
                    ResumeProfile.user_id == settings.primary_user_id
                )
            )
            == 1
        )


def test_login_identity_never_changes_resume_or_notification_email():
    for email in AUTHORIZED_EMAILS:
        with TestClient(app, headers=security_headers(email)) as client:
            assert client.get("/api/profile").status_code == 200
            assert client.get("/api/resume-profile").status_code == 200
    with SessionLocal() as db:
        resume_profile = db.scalar(
            select(ResumeProfile).where(
                ResumeProfile.user_id == settings.primary_user_id
            )
        )
        notification_profile = db.scalar(select(UserProfile).limit(1))
        assert resume_profile
        assert notification_profile
        assert resume_profile.email == settings.resume_email
        assert notification_profile.notification_email == settings.notification_email


def test_maintenance_mode_blocks_reads_writes_and_downloads(monkeypatch):
    monkeypatch.setattr(settings, "app_access_enabled", False)
    with TestClient(app, headers=security_headers()) as client:
        assert client.get("/api/jobs").status_code == 503
        assert client.post("/api/jobs/search").status_code == 503
        assert client.get("/api/generated-resumes/1/pdf").status_code == 503
        assert client.get("/health").status_code == 200


def test_resource_owned_by_another_user_is_not_visible():
    with SessionLocal() as db:
        db.info["owner_user_id"] = settings.primary_user_id
        assert db.scalar(select(UserProfile).where(
            UserProfile.owner_user_id == JOSHUA_USER_ID
        )) is None


def test_rate_limit_is_scoped_to_primary_user():
    rule = RateLimitRule("unit-test-operation", 2, 60)
    assert check_rate_limit("user-a", rule, current_time=100)[0]
    assert check_rate_limit("user-a", rule, current_time=101)[0]
    allowed, retry_after = check_rate_limit("user-a", rule, current_time=102)
    assert not allowed
    assert retry_after > 0
    assert check_rate_limit("user-b", rule, current_time=102)[0]
