from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.session import SessionLocal
from app.models import Job
from conftest import security_headers


def test_manual_recheck_endpoint_revalidates_the_current_users_saved_job(monkeypatch):
    called: dict[str, object] = {}

    async def recheck(db, *, owner_user_id, job_id, force):
        called.update({"owner_user_id": owner_user_id, "job_id": job_id, "force": force})
        current = db.get(Job, job_id)
        current.last_verified_at = datetime.now(timezone.utc)
        current.official_status = "open"
        current.verification_status = "verified"
        current.application_url_status = "VERIFIED"
        db.commit()
        return {"checked": 1, "open": 1, "expired": 0, "needs_verification": 0, "skipped": 0}

    monkeypatch.setattr("app.main.revalidate_existing_jobs", recheck)
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.status.in_(("active", "saved"))))
            assert job is not None
            job_id = job.id
        response = client.post(f"/api/jobs/{job_id}/recheck")

    assert response.status_code == 200
    assert response.json()["last_verified_at"] is not None
    assert called == {
        "owner_user_id": "internship-radar-primary",
        "job_id": job_id,
        "force": True,
    }
