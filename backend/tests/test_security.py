from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import ResumeProfile, UserProfile
from app.security.identity import (
    IdentityValidationError,
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
    try:
        validate_user_identity(f"{payload}.{signature[:-1]}A")
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
        profile = db.scalar(select(UserProfile).limit(1))
        assert profile
        original_owner = profile.owner_user_id
        profile.owner_user_id = "another-user"
        profile_id = profile.id
        db.commit()
    try:
        with TestClient(app, headers=security_headers()) as client:
            assert client.get("/api/profile").status_code == 404
    finally:
        with SessionLocal() as db:
            profile = db.get(UserProfile, profile_id)
            assert profile
            profile.owner_user_id = original_owner
            db.commit()


def test_rate_limit_is_scoped_to_primary_user():
    rule = RateLimitRule("unit-test-operation", 2, 60)
    assert check_rate_limit("user-a", rule, current_time=100)[0]
    assert check_rate_limit("user-a", rule, current_time=101)[0]
    allowed, retry_after = check_rate_limit("user-a", rule, current_time=102)
    assert not allowed
    assert retry_after > 0
    assert check_rate_limit("user-b", rule, current_time=102)[0]
