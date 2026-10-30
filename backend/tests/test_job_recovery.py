"""Reversible application states and exact, owner-scoped job recovery."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs.restore_five_rings import EXTERNAL_ID, OFFICIAL_URL, restore_official_job
from app.main import app
from app.models import Application, Job, UserProfile
from app.security.identity import JOSHUA_USER_ID
from app.sources.greenhouse import GreenhouseAdapter
from conftest import security_headers


def _official_five_rings():
    adapter = GreenhouseAdapter("Five Rings", "fiveringsllc", "https://job-boards.greenhouse.io/fiveringsllc")
    return adapter.normalize_job({
        "id": int(EXTERNAL_ID),
        "title": "LINK 2027: Software Development Intensive Program",
        "absolute_url": OFFICIAL_URL,
        "location": {"name": "New York, NY"},
        "content": "Software development in C++, Python and Linux, networking and distributed systems.",
        "updated_at": "2026-09-20T00:00:00Z",
    })


def test_applied_can_be_removed_without_erasing_history_or_job():
    with TestClient(app, headers=security_headers()) as client:
        job_id = client.get("/api/jobs", params={"page_size": 1}).json()["items"][0]["id"]
        marked = client.post(f"/api/jobs/{job_id}/mark-applied")
        assert marked.status_code == 200
        application_id = marked.json()["application"]["id"]
        original_applied_at = marked.json()["application"]["applied_at"]
        removed = client.post(f"/api/jobs/{job_id}/undo-applied")
        assert removed.status_code == 200
        assert removed.json()["job"]["status"] in {"active", "saved"}
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            application = db.get(Application, application_id)
            assert job and application
            assert application.applied_at.isoformat().startswith(original_applied_at[:19])
            transitions = [(entry["from"], entry["to"]) for entry in application.status_history]
            assert ("Applied", "Draft" if job.status == "active" else "Saved") == transitions[-1]
            assert any(to == "Applied" for _, to in transitions)
        # A second application cycle is safe and leaves the fixture available
        # for unrelated dashboard tests.
        assert client.post(f"/api/jobs/{job_id}/mark-applied").status_code == 200
        assert client.post(f"/api/jobs/{job_id}/undo-applied").status_code == 200


def test_application_process_transitions_and_archive_keep_metadata():
    with TestClient(app, headers=security_headers()) as client:
        job_id = client.get("/api/jobs", params={"page_size": 1}).json()["items"][0]["id"]
        original = client.get(f"/api/jobs/{job_id}").json()
        marked = client.post(f"/api/jobs/{job_id}/mark-applied").json()
        application_id = marked["application"]["id"]
        with SessionLocal() as db:
            stored = db.get(Application, application_id)
            stored.notes = "Original application notes"
            db.commit()
        assert client.put(f"/api/applications/{application_id}", json={"status": "Interview"}).status_code == 200
        assert client.put(f"/api/applications/{application_id}", json={"status": "Applied"}).status_code == 200
        assert client.put(f"/api/applications/{application_id}", json={"status": "Rejected"}).status_code == 200
        archived = client.post(f"/api/jobs/{job_id}/archive").json()
        assert archived["status"] == "archived"
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        restored = client.post(f"/api/jobs/{job_id}/restore").json()
        assert restored["status"] == "applied"
        assert restored["source_url"] == original["source_url"]
        with SessionLocal() as db:
            application = db.get(Application, application_id)
            assert application.notes == "Original application notes"
            assert [event["to"] for event in application.status_history][-4:] == [
                "Applied", "Interview", "Applied", "Rejected"
            ]
        # Leave the shared dashboard fixture in the active lifecycle.
        assert client.put(f"/api/applications/{application_id}", json={"status": "Draft"}).status_code == 200


def test_five_rings_restores_exact_record_and_preserves_official_url():
    with TestClient(app, headers=security_headers()):
        normalized = _official_five_rings()
        with SessionLocal() as db:
            job, reused = restore_official_job(db, normalized, settings.primary_user_id)
            assert not reused
            job_id = job.id
            job.status = "archived"
            db.commit()
            restored, reused = restore_official_job(db, normalized, settings.primary_user_id)
            assert reused and restored.id == job_id
            assert restored.status == "active"
            assert restored.original_source_url == OFFICIAL_URL
            assert restored.source_name == "Greenhouse"
            assert restored.official_status == "open"
            assert len(list(db.scalars(select(Job).where(
                Job.owner_user_id == settings.primary_user_id,
                Job.external_id == EXTERNAL_ID,
            )))) == 1


def test_one_owner_archive_does_not_change_another_owners_job():
    with TestClient(app, headers=security_headers()) as client:
        normalized = _official_five_rings()
        with SessionLocal() as db:
            if db.scalar(select(UserProfile.id).where(UserProfile.owner_user_id == JOSHUA_USER_ID)) is None:
                db.add(UserProfile(owner_user_id=JOSHUA_USER_ID, full_name="Joshua"))
                db.commit()
            santi_job, _ = restore_official_job(db, normalized, settings.primary_user_id)
            joshua_job, _ = restore_official_job(db, normalized, JOSHUA_USER_ID)
            santi_id, joshua_id = santi_job.id, joshua_job.id
        assert client.post(f"/api/jobs/{santi_id}/archive").status_code == 200
        with SessionLocal() as db:
            assert db.get(Job, santi_id).status == "archived"
            assert db.get(Job, joshua_id).status == "active"
        assert client.post(f"/api/jobs/{joshua_id}/restore").status_code == 404


def test_permanent_application_deletion_requires_explicit_confirmation():
    with TestClient(app, headers=security_headers()) as client:
        job_id = client.get("/api/jobs", params={"page_size": 1}).json()["items"][0]["id"]
        application_id = client.post(f"/api/jobs/{job_id}/mark-applied").json()["application"]["id"]
        assert client.delete(f"/api/applications/{application_id}").status_code == 409
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert client.delete(f"/api/applications/{application_id}?confirm=true").status_code == 204
        # An explicitly deleted application still never deletes the job itself.
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert client.post(f"/api/jobs/{job_id}/undo-applied").status_code == 200
