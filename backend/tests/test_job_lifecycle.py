from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Job
from app.services.job_lifecycle import expire_past_deadline_jobs


def make_job(**changes) -> Job:
    values = {
        "source_name": "test",
        "source_url": "https://example.test/source",
        "company": "Example",
        "title": "Engineering Intern",
        "apply_url": "https://example.test/apply",
        "raw_data_hash": "test-hash",
        "status": "active",
        "application_deadline": None,
        "deadline_confidence": None,
    }
    values.update(changes)
    return Job(**values)


def lifecycle_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_deadline_remains_active_during_its_local_day():
    with lifecycle_session() as db:
        job = make_job(
            application_deadline=date(2026, 9, 10),
            deadline_confidence=1.0,
        )
        db.add(job)
        db.commit()

        changed = expire_past_deadline_jobs(
            db,
            now=datetime(2026, 9, 11, 4, 59, 59, tzinfo=timezone.utc),
        )

        assert changed == 0
        assert job.status == "active"


def test_deadline_expires_after_local_midnight():
    with lifecycle_session() as db:
        job = make_job(
            application_deadline=date(2026, 9, 10),
            deadline_confidence=1.0,
        )
        db.add(job)
        db.commit()
        now = datetime(2026, 9, 11, 6, 0, 0, tzinfo=timezone.utc)

        changed = expire_past_deadline_jobs(db, now=now)

        assert changed == 1
        assert job.status == "expired"
        assert job.expired_at is not None


def test_applied_missing_future_and_low_confidence_jobs_do_not_expire():
    with lifecycle_session() as db:
        today = date(2026, 9, 11)
        jobs = [
            make_job(
                status="applied",
                application_deadline=today - timedelta(days=1),
                deadline_confidence=1.0,
                raw_data_hash="applied",
            ),
            make_job(application_deadline=None, raw_data_hash="missing"),
            make_job(
                application_deadline=today + timedelta(days=1),
                deadline_confidence=1.0,
                raw_data_hash="future",
            ),
            make_job(
                application_deadline=today - timedelta(days=1),
                deadline_confidence=0.4,
                raw_data_hash="low-confidence",
            ),
        ]
        db.add_all(jobs)
        db.commit()

        changed = expire_past_deadline_jobs(
            db,
            now=datetime(2026, 9, 11, 18, 0, tzinfo=timezone.utc),
        )

        assert changed == 0
        assert [job.status for job in jobs] == ["applied", "active", "active", "active"]
