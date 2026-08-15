from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import Base
from app.models import Application, Job, JobAnalysis, Notification, UserProfile
from app.services.email_service import (
    ConsoleEmailProvider,
    EmailProvider,
    EmailService,
    OutgoingEmail,
    ProviderResult,
    SMTPEmailProvider,
)


class RecordingProvider(EmailProvider):
    name = "recording"

    def __init__(self, error: str | None = None):
        self.error = error
        self.sent: list[OutgoingEmail] = []

    def validate(self) -> tuple[bool, str]:
        return True, "ready"

    def send(self, email: OutgoingEmail) -> ProviderResult:
        if self.error:
            raise RuntimeError(self.error)
        self.sent.append(email)
        return ProviderResult(message_id=f"recording-{len(self.sent)}")

    def test_connection(self) -> tuple[bool, str]:
        return True, "ready"


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def config() -> Settings:
    return Settings(
        email_enabled=True,
        email_provider="console",
        email_recipient="alerts@example.com",
        email_deadline_alerts=True,
        email_daily_digest=True,
        app_base_url="http://localhost:3000",
    )


def make_profile(db: Session, **overrides) -> UserProfile:
    values = {
        "full_name": "Alex Rivera",
        "degree": "B.S. Computer Engineering",
        "university": "Example Institute of Technology",
        "graduation_year": 2029,
        "gpa": 3.7,
        "gpa_scale": 4.0,
        "nationality": "Mexican",
        "email_notifications": True,
        "notification_email": "alerts@example.com",
        "priority_email_alerts": True,
        "major_company_email_alerts": True,
        "deadline_alerts": True,
        "daily_digest": True,
        "application_follow_up_alerts": True,
        "email_minimum_score": 80,
        "major_company_minimum_score": 70,
    }
    values.update(overrides)
    profile = UserProfile(**values)
    db.add(profile)
    db.commit()
    return profile


def make_job(
    db: Session,
    *,
    company: str = "NXP",
    company_importance: str = "Major company",
    official_status: str = "open",
    verification_status: str = "verified",
    is_active: bool = True,
    is_priority_alert: bool = True,
    expires_at: datetime | None = None,
    blockers: list[str] | None = None,
    overall_score: float = 88,
    recommendation: str = "Apply Today",
) -> Job:
    now = datetime.now(timezone.utc)
    job = Job(
        external_id=f"job-{now.timestamp()}",
        source_name="Official",
        source_url="https://careers.example.com",
        company=company,
        title="Embedded Software Intern",
        location="Austin, Texas, United States",
        country="United States",
        remote_type="Hybrid",
        employment_type="Internship",
        area="Firmware / Embedded",
        company_importance=company_importance,
        description="Embedded C firmware and hardware debugging.",
        requirements="C, C++, microcontrollers, and Git.",
        preferred_qualifications="FreeRTOS, UART, SPI, and I2C.",
        apply_url="https://careers.example.com/jobs/123",
        official_apply_url="https://careers.example.com/jobs/123",
        official_status=official_status,
        verification_status=verification_status,
        last_verified_at=now,
        posted_at=now - timedelta(days=1),
        expires_at=expires_at,
        is_active=is_active,
        is_priority_alert=is_priority_alert,
        raw_data_hash=f"hash-{now.timestamp()}",
    )
    job.analysis = JobAnalysis(
        technical_score=92,
        academic_score=90,
        eligibility_score=82,
        level_score=100,
        logistics_score=80,
        freshness_score=95,
        overall_score=overall_score,
        recommendation=recommendation,
        eligibility_status="Review",
        recommended_resume_type="Firmware / Embedded",
        matched_skills=["C", "C++", "Embedded Systems"],
        missing_required_skills=[],
        positive_reasons=["Strong embedded systems match."],
        risk_flags=["Work authorization is not clearly explained."],
        blocker_reasons=blockers or [],
        explanation="Strong match.",
    )
    db.add(job)
    db.commit()
    return job


def notification_count(db: Session) -> int:
    return db.scalar(select(func.count(Notification.id))) or 0


def test_new_priority_alert_sends_email(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is True
    assert len(provider.sent) == 1
    assert notification_count(db) == 1


def test_duplicate_job_does_not_send_twice(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider()
    service = EmailService(db, config, provider)

    first = service.send_priority_job_alert(job, job.analysis, profile)
    second = service.send_priority_job_alert(job, job.analysis, profile)

    assert first.success is True
    assert second.success is False
    assert len(provider.sent) == 1
    assert notification_count(db) == 1


def test_verified_transition_can_send_priority_alert(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider()
    previous_state = {
        "official_status": "unknown",
        "verification_status": "unverified",
        "recommendation": "Needs Verification",
    }

    results = EmailService(db, config, provider).dispatch_job_notifications(
        job,
        profile,
        is_new=False,
        previous_state=previous_state,
    )

    assert any(result.success for result in results)
    assert len(provider.sent) == 1


def test_priority_only_mode_skips_ordinary_status_change(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db, is_priority_alert=False)
    application = Application(job_id=job.id, status="Saved", resume_type="General Engineering")
    db.add(application)
    db.commit()
    provider = RecordingProvider()
    previous_state = {
        "official_status": "open",
        "verification_status": "verified",
        "recommendation": "Review",
    }
    job.analysis.recommendation = "Low Match"

    results = EmailService(db, config, provider).dispatch_job_notifications(
        job,
        profile,
        is_new=False,
        previous_state=previous_state,
    )

    assert provider.sent == []
    assert not any(result.success for result in results)
    assert notification_count(db) == 0


def test_unverified_job_does_not_send(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db, verification_status="unverified")
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert provider.sent == []


def test_closed_job_does_not_send(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db, official_status="closed", is_active=False, recommendation="Closed")
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert provider.sent == []


def test_citizenship_blocker_does_not_send(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db, blockers=["U.S. citizenship is explicitly required."])
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert provider.sent == []


def test_major_company_with_score_sends(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db, is_priority_alert=False, overall_score=86)
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_major_company_alert(
        job, job.analysis, profile
    )

    assert result.success is True
    assert len(provider.sent) == 1


def test_major_company_with_blocker_does_not_send(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(
        db,
        is_priority_alert=False,
        blockers=["Permanent U.S. work authorization is required."],
    )
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_major_company_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert provider.sent == []


def test_deadline_within_seven_days_sends(db: Session, config: Settings):
    now = datetime.now(timezone.utc)
    profile = make_profile(db)
    job = make_job(db, expires_at=now + timedelta(days=6))
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_deadline_alert(
        job, job.analysis, profile, now
    )

    assert result.success is True
    assert len(provider.sent) == 1


def test_deadline_under_72_hours_can_send_second_alert(db: Session, config: Settings):
    now = datetime.now(timezone.utc)
    profile = make_profile(db)
    job = make_job(db, expires_at=now + timedelta(days=6))
    provider = RecordingProvider()
    service = EmailService(db, config, provider)

    first = service.send_deadline_alert(job, job.analysis, profile, now)
    job.expires_at = now + timedelta(days=2)
    db.commit()
    urgent = service.send_deadline_alert(job, job.analysis, profile, now)

    assert first.success is True
    assert urgent.success is True
    assert len(provider.sent) == 2


def test_empty_digest_does_not_send(db: Session, config: Settings):
    profile = make_profile(db)
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_daily_digest([], [], profile)

    assert result.success is False
    assert provider.sent == []
    assert notification_count(db) == 0


def test_daily_digest_sends_only_once_per_local_day(db: Session, config: Settings):
    profile = make_profile(db)
    first_job = make_job(db)
    provider = RecordingProvider()
    service = EmailService(db, config, provider)
    now = datetime.now(timezone.utc)

    first = service.send_daily_digest([first_job], [], profile, now)
    second_job = make_job(db, company="Intel")
    second = service.send_daily_digest([first_job, second_job], [], profile, now)

    assert first.success is True
    assert second.success is False
    assert len(provider.sent) == 1


def test_smtp_failure_does_not_break_system(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider(error="SMTP unavailable")

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert db.get(Job, job.id) is not None
    record = db.scalar(select(Notification))
    assert record is not None
    assert record.status == "failed"


def test_credentials_do_not_appear_in_logs(db: Session, config: Settings, caplog):
    profile = make_profile(db)
    job = make_job(db)
    secret = "super-secret-app-password"
    provider = RecordingProvider(error=secret)
    caplog.set_level("ERROR")

    EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert secret not in caplog.text
    record = db.scalar(select(Notification))
    assert record is not None
    assert secret not in (record.error_message or "")


def test_email_disabled_prevents_all_sends(db: Session):
    config = Settings(email_enabled=False, email_provider="console")
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider()

    result = EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is False
    assert provider.sent == []
    assert notification_count(db) == 0


def test_console_provider_works_without_credentials(db: Session, config: Settings, caplog):
    profile = make_profile(db)
    job = make_job(db)
    caplog.set_level("INFO")

    result = EmailService(db, config, ConsoleEmailProvider()).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert result.success is True
    assert "Console email preview" in caplog.text


def test_gmail_app_password_display_spaces_are_removed(monkeypatch):
    captured: dict[str, str] = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def ehlo(self):
            return None

        def starttls(self, **_kwargs):
            return None

        def login(self, username: str, password: str):
            captured["username"] = username
            captured["password"] = password

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", FakeSMTP)
    provider = SMTPEmailProvider(
        Settings(
            smtp_host="smtp.gmail.com",
            smtp_username="sender@example.com",
            smtp_password="abcd efgh ijkl mnop",
        )
    )

    provider._connect()

    assert captured == {
        "username": "sender@example.com",
        "password": "abcdefghijklmnop",
    }


def test_default_recipient_is_requested_address(db: Session, config: Settings):
    profile = make_profile(db)
    job = make_job(db)
    provider = RecordingProvider()

    EmailService(db, config, provider).send_priority_job_alert(
        job, job.analysis, profile
    )

    assert provider.sent[0].recipient == "alerts@example.com"
