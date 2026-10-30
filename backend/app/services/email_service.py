from __future__ import annotations

import hashlib
import json
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, settings
from app.models import Application, Job, JobAnalysis, Notification, UserProfile


logger = logging.getLogger(__name__)
INTERNSHIP_TERMS = ("intern", "internship", "co-op", "coop", "student program")
SENIOR_TERMS = ("senior", "staff", "principal", "manager", "lead", "director")


@dataclass(frozen=True)
class OutgoingEmail:
    recipient: str
    subject: str
    body: str


@dataclass(frozen=True)
class ProviderResult:
    message_id: str | None = None


@dataclass(frozen=True)
class EmailResult:
    success: bool
    message: str
    provider: str
    notification_id: int | None = None


class EmailProvider(ABC):
    name = "unknown"

    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def send(self, email: OutgoingEmail) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        raise NotImplementedError


class SMTPEmailProvider(EmailProvider):
    name = "smtp"

    def __init__(self, config: Settings = settings):
        self.config = config

    def validate(self) -> tuple[bool, str]:
        missing = []
        if not self.config.smtp_host:
            missing.append("SMTP_HOST")
        if not self.config.smtp_username:
            missing.append("SMTP_USERNAME")
        if not self.config.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not (self.config.smtp_from_email or self.config.smtp_username):
            missing.append("SMTP_FROM_EMAIL")
        if missing:
            return False, f"Missing email configuration: {', '.join(missing)}."
        return True, "SMTP configuration is complete."

    def _connect(self) -> smtplib.SMTP:
        client = smtplib.SMTP(
            self.config.smtp_host,
            self.config.smtp_port,
            timeout=self.config.request_timeout_seconds,
        )
        client.ehlo()
        if self.config.smtp_use_tls:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        password = self.config.smtp_password
        if self.config.smtp_host.strip().lower() == "smtp.gmail.com":
            compact_password = "".join(password.split())
            if len(compact_password) == 16:
                password = compact_password
        client.login(self.config.smtp_username, password)
        return client

    def send(self, email: OutgoingEmail) -> ProviderResult:
        valid, message = self.validate()
        if not valid:
            raise RuntimeError(message)
        message_id = make_msgid(domain="internship-radar.local")
        payload = EmailMessage()
        payload["Subject"] = email.subject
        payload["From"] = formataddr(
            (
                self.config.smtp_from_name,
                self.config.smtp_from_email or self.config.smtp_username,
            )
        )
        payload["To"] = email.recipient
        payload["Message-ID"] = message_id
        payload.set_content(email.body)
        client = self._connect()
        try:
            client.send_message(payload)
        finally:
            try:
                client.quit()
            except smtplib.SMTPException:
                client.close()
        return ProviderResult(message_id=message_id)

    def test_connection(self) -> tuple[bool, str]:
        valid, message = self.validate()
        if not valid:
            return False, message
        try:
            client = self._connect()
            try:
                client.noop()
            finally:
                try:
                    client.quit()
                except smtplib.SMTPException:
                    client.close()
            return True, "SMTP connection succeeded."
        except Exception:
            return False, "Could not connect to the SMTP server. Check the host, TLS, and credentials."


class ConsoleEmailProvider(EmailProvider):
    name = "console"

    def validate(self) -> tuple[bool, str]:
        return True, "Console email provider is ready."

    def send(self, email: OutgoingEmail) -> ProviderResult:
        message_id = make_msgid(domain="console.internship-radar.local")
        logger.info(
            "Console email preview\nTo: %s\nSubject: %s\n\n%s",
            email.recipient,
            email.subject,
            email.body,
        )
        return ProviderResult(message_id=message_id)

    def test_connection(self) -> tuple[bool, str]:
        return True, "Console email provider is ready."


def create_email_provider(config: Settings = settings) -> EmailProvider:
    provider_name = config.email_provider.strip().lower()
    if provider_name == "smtp":
        return SMTPEmailProvider(config)
    if provider_name == "console":
        return ConsoleEmailProvider()
    raise ValueError(f"Unsupported email provider: {provider_name}")


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _format_date(value: datetime | None) -> str:
    value = _as_aware(value)
    return value.strftime("%B %d, %Y") if value else "Not available"


def _bullet_list(items: Iterable[str], empty: str = "None identified") -> str:
    values = [item for item in items if item]
    return "\n".join(f"- {item}" for item in values) if values else f"- {empty}"


def _content_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _deadline_bucket(job: Job, now: datetime | None = None) -> str:
    now = _as_aware(now) or datetime.now(timezone.utc)
    expires_at = _as_aware(job.expires_at)
    if not expires_at:
        return "no-deadline"
    remaining = expires_at - now
    if remaining <= timedelta(0):
        return "expired"
    if remaining <= timedelta(hours=72):
        return "under-72-hours"
    if remaining <= timedelta(days=7):
        return "under-7-days"
    return "later"


def _is_internship(job: Job) -> bool:
    text = f"{job.title} {job.employment_type}".lower()
    return any(term in text for term in INTERNSHIP_TERMS)


def _is_senior(job: Job) -> bool:
    title = job.title.lower()
    return any(term in title for term in SENIOR_TERMS)


def _eligible_for_email(job: Job, analysis: JobAnalysis | None, minimum_score: float) -> bool:
    return bool(
        analysis
        and _is_internship(job)
        and not _is_senior(job)
        and job.discovery_status != "demo"
        and getattr(job, "status", "active") in {"active", "saved"}
        and job.is_active
        and job.official_status == "open"
        and job.verification_status == "verified"
        and bool(job.official_apply_url or job.apply_url)
        and analysis.overall_score >= minimum_score
        and analysis.recommendation not in {"Not Eligible", "Closed", "Expired", "Needs Verification"}
        and not analysis.blocker_reasons
    )


def _recipient(profile: UserProfile | None, config: Settings) -> str:
    if profile and profile.notification_email.strip():
        return profile.notification_email.strip()
    return config.email_recipient.strip()


def _job_email(job: Job, analysis: JobAnalysis, config: Settings, intro: str) -> str:
    apply_url = job.official_apply_url or job.apply_url
    return "\n".join(
        [
            intro,
            "",
            f"Company: {job.company}",
            f"Position: {job.title}",
            f"Location: {job.location or 'Not available'}",
            f"Country: {job.country or 'Not available'}",
            f"Work arrangement: {job.remote_type}",
            f"Published: {_format_date(job.official_posted_at or job.posted_at)}",
            f"Verified: {_format_date(job.last_verified_at)}",
            f"Deadline: {_format_date(job.expires_at)}",
            f"Technical score: {analysis.technical_score:.0f}%",
            f"Eligibility score: {analysis.eligibility_score:.0f}%",
            f"Overall score: {analysis.overall_score:.0f}%",
            f"Category: {job.area}",
            f"Status: {analysis.recommendation}",
            f"Recommended resume: {analysis.recommended_resume_type}",
            "",
            "Matching skills:",
            _bullet_list(analysis.matched_skills),
            "",
            "Missing skills:",
            _bullet_list(analysis.missing_required_skills),
            "",
            "Why it matches:",
            _bullet_list(analysis.positive_reasons),
            "",
            "Important risks:",
            _bullet_list(analysis.risk_flags),
            "",
            f"Official application: {apply_url}",
            f"Internship Radar: {config.app_base_url.rstrip('/')}/jobs/{job.id}",
        ]
    )


class EmailService:
    def __init__(
        self,
        db: Session,
        config: Settings = settings,
        provider: EmailProvider | None = None,
    ):
        self.db = db
        self.config = config
        self.provider = provider or create_email_provider(config)

    def _enabled(self, profile: UserProfile | None = None) -> tuple[bool, str]:
        if not self.config.email_enabled:
            logger.warning("Email notifications are disabled.")
            return False, "Email notifications are disabled."
        if profile and not profile.email_notifications:
            return False, "Email notifications are disabled in the profile."
        return True, ""

    def test_email_connection(self, profile: UserProfile | None = None) -> EmailResult:
        enabled, message = self._enabled(profile)
        if not enabled:
            return EmailResult(False, message, self.provider.name)
        success, message = self.provider.test_connection()
        return EmailResult(success, message, self.provider.name)

    def _already_sent(
        self,
        *,
        job_id: int | None,
        application_id: int | None,
        notification_type: str,
        recipient: str,
        content_hash: str,
    ) -> bool:
        return (
            self.db.scalar(
                select(Notification.id).where(
                    Notification.job_id == job_id,
                    Notification.application_id == application_id,
                    Notification.notification_type == notification_type,
                    Notification.recipient == recipient,
                    Notification.content_hash == content_hash,
                    Notification.status == "sent",
                )
            )
            is not None
        )

    def _send(
        self,
        email: OutgoingEmail,
        notification_type: str,
        content_hash: str,
        *,
        job_id: int | None = None,
        application_id: int | None = None,
        profile: UserProfile | None = None,
    ) -> EmailResult:
        enabled, message = self._enabled(profile)
        if not enabled:
            return EmailResult(False, message, self.provider.name)
        if self._already_sent(
            job_id=job_id,
            application_id=application_id,
            notification_type=notification_type,
            recipient=email.recipient,
            content_hash=content_hash,
        ):
            return EmailResult(
                False,
                "An equivalent notification was already sent.",
                self.provider.name,
            )

        record = Notification(
            job_id=job_id,
            application_id=application_id,
            notification_type=notification_type,
            recipient=email.recipient,
            subject=email.subject,
            provider=self.provider.name,
            status="pending",
            content_hash=content_hash,
        )
        self.db.add(record)
        self.db.flush()
        try:
            provider_result = self.provider.send(email)
            record.status = "sent"
            record.sent_at = datetime.now(timezone.utc)
            record.provider_message_id = provider_result.message_id
            message = "Email sent successfully."
            success = True
        except Exception:
            logger.error("Email delivery failed without exposing provider credentials.")
            record.status = "failed"
            record.error_message = (
                "Email delivery failed. Check the provider configuration and credentials."
            )
            message = record.error_message
            success = False
        self.db.commit()
        return EmailResult(success, message, self.provider.name, record.id)

    def send_priority_job_alert(
        self,
        job: Job,
        analysis: JobAnalysis,
        profile: UserProfile,
    ) -> EmailResult:
        if not (
            profile.priority_email_alerts
            and self.config.email_priority_alerts
            and job.is_priority_alert
            and _eligible_for_email(job, analysis, profile.email_minimum_score)
        ):
            return EmailResult(False, "The job does not qualify for a priority email.", self.provider.name)
        recipient = _recipient(profile, self.config)
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Nueva oportunidad: {job.company} — {job.title}",
            body=_job_email(
                job,
                analysis,
                self.config,
                "A new internship matching your profile was found.",
            ),
        )
        content_hash = _content_hash(
            {
                "job_id": job.id,
                "type": "priority_job",
                "verification": job.verification_status,
                "recommendation": analysis.recommendation,
                "deadline": job.expires_at.date().isoformat() if job.expires_at else None,
            }
        )
        return self._send(
            email,
            "priority_job",
            content_hash,
            job_id=job.id,
            profile=profile,
        )

    def send_major_company_alert(
        self,
        job: Job,
        analysis: JobAnalysis,
        profile: UserProfile,
    ) -> EmailResult:
        minimum_score = max(
            profile.email_minimum_score,
            profile.major_company_minimum_score,
        )
        if not (
            profile.major_company_email_alerts
            and job.company_importance == "Major company"
            and _eligible_for_email(job, analysis, minimum_score)
        ):
            return EmailResult(False, "The job does not qualify for a major-company email.", self.provider.name)
        recipient = _recipient(profile, self.config)
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Nueva oportunidad: {job.company} — {job.title}",
            body=_job_email(
                job,
                analysis,
                self.config,
                "A compatible opportunity from a major company was found.",
            ),
        )
        content_hash = _content_hash(
            {
                "job_id": job.id,
                "type": "major_company_job",
                "verification": job.verification_status,
                "recommendation": analysis.recommendation,
            }
        )
        return self._send(
            email,
            "major_company_job",
            content_hash,
            job_id=job.id,
            profile=profile,
        )

    def send_deadline_alert(
        self,
        job: Job,
        analysis: JobAnalysis,
        profile: UserProfile,
        now: datetime | None = None,
    ) -> EmailResult:
        bucket = _deadline_bucket(job, now)
        if not (
            profile.deadline_alerts
            and self.config.email_deadline_alerts
            and bucket in {"under-7-days", "under-72-hours"}
            and _eligible_for_email(job, analysis, profile.email_minimum_score)
        ):
            return EmailResult(False, "The job does not qualify for a deadline email.", self.provider.name)
        recipient = _recipient(profile, self.config)
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Deadline approaching: {job.company} — {job.title}",
            body=_job_email(
                job,
                analysis,
                self.config,
                "A saved opportunity is approaching its application deadline.",
            ),
        )
        content_hash = _content_hash(
            {
                "job_id": job.id,
                "type": "deadline_warning",
                "deadline": _as_aware(job.expires_at).isoformat() if job.expires_at else None,
                "bucket": bucket,
            }
        )
        return self._send(
            email,
            "deadline_warning",
            content_hash,
            job_id=job.id,
            profile=profile,
        )

    def send_status_change(
        self,
        job: Job,
        analysis: JobAnalysis,
        profile: UserProfile,
        previous_state: dict[str, str | None],
    ) -> EmailResult:
        current_state = {
            "official_status": job.official_status,
            "verification_status": job.verification_status,
            "recommendation": analysis.recommendation,
        }
        if previous_state == current_state or not _eligible_for_email(
            job, analysis, profile.email_minimum_score
        ):
            return EmailResult(False, "No notifiable job status change was found.", self.provider.name)
        saved = self.db.scalar(
            select(Application.id).where(Application.job_id == job.id).limit(1)
        )
        if saved is None:
            return EmailResult(False, "The changed job is not saved.", self.provider.name)
        recipient = _recipient(profile, self.config)
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Status changed: {job.company} — {job.title}",
            body=_job_email(
                job,
                analysis,
                self.config,
                "A tracked opportunity changed status.",
            ),
        )
        content_hash = _content_hash(
            {
                "job_id": job.id,
                "type": "status_change",
                "from": previous_state,
                "to": current_state,
            }
        )
        return self._send(
            email,
            "status_change",
            content_hash,
            job_id=job.id,
            profile=profile,
        )

    def send_application_follow_up(
        self,
        application: Application,
        profile: UserProfile,
        now: datetime | None = None,
    ) -> EmailResult:
        now = _as_aware(now) or datetime.now(timezone.utc)
        next_action = _as_aware(application.next_action_at)
        if not (
            profile.application_follow_up_alerts
            and self.config.email_follow_up_alerts
            and next_action
            and now - timedelta(hours=24) <= next_action <= now + timedelta(hours=24)
        ):
            return EmailResult(False, "The application does not need a follow-up email.", self.provider.name)
        recipient = _recipient(profile, self.config)
        job = application.job
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Application follow-up: {job.company} — {job.title}",
            body="\n".join(
                [
                    "An application follow-up is approaching.",
                    "",
                    f"Company: {job.company}",
                    f"Position: {job.title}",
                    f"Application status: {application.status}",
                    f"Next action: {_format_date(next_action)}",
                    f"Notes: {application.notes or 'None'}",
                    f"Internship Radar: {self.config.app_base_url.rstrip('/')}/applications",
                ]
            ),
        )
        content_hash = _content_hash(
            {
                "application_id": application.id,
                "type": "application_follow_up",
                "next_action": next_action.isoformat(),
            }
        )
        return self._send(
            email,
            "application_follow_up",
            content_hash,
            job_id=application.job_id,
            application_id=application.id,
            profile=profile,
        )

    def send_daily_digest(
        self,
        jobs: Sequence[Job],
        applications: Sequence[Application],
        profile: UserProfile,
        now: datetime | None = None,
        status_changed_job_ids: set[int] | None = None,
    ) -> EmailResult:
        if not (profile.daily_digest and self.config.email_daily_digest):
            return EmailResult(False, "Daily digest is disabled.", self.provider.name)
        eligible_jobs = [
            job
            for job in jobs
            if _eligible_for_email(job, job.analysis, profile.email_minimum_score)
        ]
        if not eligible_jobs and not applications:
            return EmailResult(False, "The daily digest is empty.", self.provider.name)
        local_now = (_as_aware(now) or datetime.now(timezone.utc)).astimezone(
            ZoneInfo(self.config.user_timezone)
        )
        status_changed_job_ids = status_changed_job_ids or set()
        recipient = _recipient(profile, self.config)
        recent_cutoff = local_now.astimezone(timezone.utc) - timedelta(days=1)

        def job_line(job: Job) -> str:
            return (
                f"- {job.company}: {job.title} "
                f"({job.analysis.overall_score:.0f}%, {job.urgency})"
            )

        important_lines = [
            job_line(job)
            for job in eligible_jobs
            if job.is_priority_alert or job.company_importance == "Major company"
        ]
        recommended_lines = [
            job_line(job)
            for job in eligible_jobs
            if job.analysis and job.analysis.recommendation in {"Apply Now", "Apply Today", "Review"}
        ]
        new_lines = [
            job_line(job)
            for job in eligible_jobs
            if _as_aware(job.first_seen_at) and _as_aware(job.first_seen_at) >= recent_cutoff
        ]
        deadline_lines = [
            job_line(job)
            for job in eligible_jobs
            if _deadline_bucket(job, local_now) in {"under-7-days", "under-72-hours"}
        ]
        changed_lines = [
            job_line(job) for job in eligible_jobs if job.id in status_changed_job_ids
        ]
        application_lines = [
            f"- {application.job.company}: {application.job.title} — next action {_format_date(application.next_action_at)}"
            for application in applications
        ]
        body = "\n".join(
            [
                "Your Internship Radar daily digest is ready.",
                "",
                "New important opportunities:",
                *(important_lines or ["- None today"]),
                "",
                "New opportunities:",
                *(new_lines or ["- None today"]),
                "",
                "Recommended opportunities:",
                *(recommended_lines or ["- None today"]),
                "",
                "Closing soon:",
                *(deadline_lines or ["- None today"]),
                "",
                "Status changes:",
                *(changed_lines or ["- None today"]),
                "",
                "Applications needing follow-up:",
                *(application_lines or ["- None today"]),
                "",
                f"Open Internship Radar: {self.config.app_base_url.rstrip('/')}",
            ]
        )
        email = OutgoingEmail(
            recipient=recipient,
            subject=f"[Internship Radar] Daily digest — {local_now:%B %d, %Y}",
            body=body,
        )
        content_hash = _content_hash(
            {
                "type": "daily_digest",
                "local_date": local_now.date().isoformat(),
            }
        )
        return self._send(email, "daily_digest", content_hash, profile=profile)

    def send_test_email(self, profile: UserProfile) -> EmailResult:
        recipient = _recipient(profile, self.config)
        now = datetime.now(timezone.utc)
        email = OutgoingEmail(
            recipient=recipient,
            subject="[Internship Radar] Test email",
            body=(
                "Email notifications are configured correctly.\n\n"
                f"Recipient: {recipient}\n"
                f"Provider: {self.provider.name}\n"
                f"Internship Radar: {self.config.app_base_url.rstrip('/')}"
            ),
        )
        return self._send(
            email,
            "test_email",
            _content_hash({"type": "test_email", "sent_at": now.isoformat()}),
            profile=profile,
        )

    def dispatch_job_notifications(
        self,
        job: Job,
        profile: UserProfile,
        *,
        is_new: bool,
        previous_state: dict[str, str | None] | None = None,
    ) -> list[EmailResult]:
        if not job.analysis:
            return []
        results = []
        became_verified = bool(
            previous_state
            and previous_state.get("verification_status") != "verified"
            and job.verification_status == "verified"
        )
        became_apply_today = bool(
            previous_state
            and previous_state.get("recommendation") not in {"Apply Today", "Apply Now"}
            and job.analysis.recommendation in {"Apply Today", "Apply Now"}
        )
        opportunity_event = is_new or became_verified or became_apply_today
        sent_opportunity = False
        if opportunity_event:
            priority_candidate = bool(
                profile.priority_email_alerts
                and self.config.email_priority_alerts
                and job.is_priority_alert
            )
            if priority_candidate:
                result = self.send_priority_job_alert(job, job.analysis, profile)
            else:
                result = self.send_major_company_alert(job, job.analysis, profile)
            results.append(result)
            sent_opportunity = result.success
        if (
            self.config.email_status_change_alerts
            and not is_new
            and previous_state
            and not sent_opportunity
        ):
            results.append(
                self.send_status_change(job, job.analysis, profile, previous_state)
            )
        results.append(self.send_deadline_alert(job, job.analysis, profile))
        return results


def run_email_maintenance(config: Settings = settings) -> dict[str, int]:
    from app.db.session import SessionLocal
    from app.services.job_lifecycle import expire_due_jobs

    counts = {"deadline_alerts": 0, "follow_up_alerts": 0}
    with SessionLocal() as db:
        expire_due_jobs(db)
        profile = db.scalar(select(UserProfile).limit(1))
        if not profile:
            return counts
        service = EmailService(db, config)
        jobs = list(
            db.scalars(
                select(Job)
                .where(
                    Job.status.in_(("active", "saved")),
                    Job.is_active.is_(True),
                    Job.expires_at.is_not(None),
                )
                .options(joinedload(Job.analysis))
            ).unique()
        )
        for job in jobs:
            if job.analysis and service.send_deadline_alert(job, job.analysis, profile).success:
                counts["deadline_alerts"] += 1
        applications = list(
            db.scalars(
                select(Application)
                .where(Application.next_action_at.is_not(None))
                .options(joinedload(Application.job))
            ).unique()
        )
        for application in applications:
            if service.send_application_follow_up(application, profile).success:
                counts["follow_up_alerts"] += 1
    return counts


def run_daily_digest(config: Settings = settings) -> EmailResult | None:
    from app.db.session import SessionLocal
    from app.services.job_lifecycle import expire_due_jobs

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=1)
    with SessionLocal() as db:
        expire_due_jobs(db)
        profile = db.scalar(select(UserProfile).limit(1))
        if not profile:
            return None
        jobs = list(
            db.scalars(
                select(Job)
                .where(
                    Job.is_active.is_(True),
                    Job.status.in_(("active", "saved")),
                    (
                        (Job.first_seen_at >= cutoff)
                        | (Job.urgency.in_(["Apply Soon", "Urgent", "Closing Today"]))
                    ),
                )
                .options(joinedload(Job.analysis))
            ).unique()
        )
        applications = list(
            db.scalars(
                select(Application)
                .where(
                    Application.next_action_at.is_not(None),
                    Application.next_action_at >= now - timedelta(hours=24),
                    Application.next_action_at <= now + timedelta(days=1),
                )
                .options(joinedload(Application.job))
            ).unique()
        )
        changed_job_ids = set(
            db.scalars(
                select(Notification.job_id).where(
                    Notification.notification_type == "status_change",
                    Notification.created_at >= cutoff,
                    Notification.job_id.is_not(None),
                )
            )
        )
        known_job_ids = {job.id for job in jobs}
        missing_changed_ids = changed_job_ids - known_job_ids
        if missing_changed_ids:
            jobs.extend(
                db.scalars(
                    select(Job)
                    .where(
                        Job.id.in_(missing_changed_ids),
                        Job.status.in_(("active", "saved")),
                    )
                    .options(joinedload(Job.analysis))
                ).unique()
            )
        return EmailService(db, config).send_daily_digest(
            jobs,
            applications,
            profile,
            now,
            changed_job_ids,
        )
