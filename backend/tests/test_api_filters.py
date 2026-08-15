from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import GeneratedResume, Job
from conftest import security_headers


def test_jobs_endpoint_filters_by_recommendation():
    with TestClient(app, headers=security_headers()) as client:
        response = client.get("/api/jobs", params={"recommendation": "Not Eligible", "page_size": 50})
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 3
        assert all(
            job["analysis"]["recommendation"] == "Not Eligible"
            for job in payload["items"]
        )


def test_jobs_endpoint_hides_hard_ineligible_by_default():
    with TestClient(app, headers=security_headers()) as client:
        hidden = client.get(
            "/api/jobs", params={"recommendation": "Not Eligible", "page_size": 100}
        ).json()["items"]
        assert hidden
        hidden_ids = {job["id"] for job in hidden}
        default_ids = {
            job["id"]
            for job in client.get("/api/jobs", params={"page_size": 100}).json()["items"]
        }
        assert hidden_ids.isdisjoint(default_ids)
        included_ids = {
            job["id"]
            for job in client.get(
                "/api/jobs", params={"include_ineligible": True, "page_size": 100}
            ).json()["items"]
        }
        assert hidden_ids & included_ids


def test_jobs_endpoint_filters_by_country_and_score():
    with TestClient(app, headers=security_headers()) as client:
        response = client.get("/api/jobs", params={"country": "Mexico", "min_score": 60})
        assert response.status_code == 200
        payload = response.json()
        assert payload["items"]
        assert all(job["country"] == "Mexico" for job in payload["items"])
        assert all(job["analysis"]["overall_score"] >= 60 for job in payload["items"])


def test_mark_applied_hides_job_and_undo_restores_it():
    with TestClient(app, headers=security_headers()) as client:
        headers = security_headers()
        available = client.get("/api/jobs", params={"page_size": 1}).json()["items"]
        assert available
        job_id = available[0]["id"]
        with SessionLocal() as db:
            next_version = (
                db.scalar(
                    select(func.max(GeneratedResume.version)).where(
                        GeneratedResume.user_id == settings.primary_user_id,
                        GeneratedResume.job_id == job_id,
                    )
                )
                or 0
            ) + 1
            resume = GeneratedResume(
                user_id=settings.primary_user_id,
                job_id=job_id,
                version=next_version,
                status="compiled",
                content_hash=f"lifecycle-{job_id}-{next_version}",
            )
            db.add(resume)
            db.commit()
            submitted_resume_id = resume.id

        marked = client.post(f"/api/jobs/{job_id}/mark-applied", headers=headers)
        assert marked.status_code == 200
        payload = marked.json()
        assert payload["job"]["status"] == "applied"
        assert payload["job"]["applied_at"]
        assert payload["job"]["submitted_resume_id"] == submitted_resume_id
        assert payload["application"]["submitted_resume_id"] == submitted_resume_id
        assert payload["message"] == "Application marked as submitted and moved to Applied."
        application_count = len(client.get("/api/applications").json())
        marked_again = client.post(f"/api/jobs/{job_id}/mark-applied", headers=headers)
        assert marked_again.status_code == 200
        assert len(client.get("/api/applications").json()) == application_count

        active_ids = {
            item["id"]
            for item in client.get("/api/jobs", params={"page_size": 100}).json()["items"]
        }
        assert job_id not in active_ids
        applied_ids = {
            item["id"]
            for item in client.get(
                "/api/jobs",
                params={"job_status": "applied", "page_size": 100},
            ).json()["items"]
        }
        assert job_id in applied_ids

        undone = client.post(
            f"/api/jobs/{job_id}/undo-applied",
            json={"previous_status": payload["previous_status"]},
            headers=headers,
        )
        assert undone.status_code == 200
        assert undone.json()["job"]["status"] == payload["previous_status"]
        with SessionLocal() as db:
            assert db.get(Job, job_id) is not None
            assert db.get(GeneratedResume, submitted_resume_id) is not None


def test_expired_job_is_hidden_from_active_and_recommendations():
    headers = security_headers()
    with TestClient(app, headers=headers) as client:
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.status == "active"))
            assert job
            job.application_deadline = date.today() - timedelta(days=2)
            job.deadline_source = "test"
            job.deadline_confidence = 1.0
            job_id = job.id
            db.commit()

        active = client.get("/api/jobs", params={"job_status": "active", "page_size": 100}).json()
        assert job_id not in {item["id"] for item in active["items"]}
        recommended = client.get(
            "/api/jobs",
            params={"recommendation": "Apply Today", "page_size": 100},
        ).json()
        assert job_id not in {item["id"] for item in recommended["items"]}
        expired = client.get(
            "/api/jobs",
            params={"job_status": "expired", "page_size": 100},
        ).json()
        assert job_id in {item["id"] for item in expired["items"]}

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.application_deadline = None
            db.commit()
        restored = client.post(f"/api/jobs/{job_id}/restore", headers=headers)
        assert restored.status_code == 200


def test_target_company_group_filters_work():
    with TestClient(app, headers=security_headers()) as client:
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.status == "active"))
            assert job
            job.is_target_company = True
            job.target_company_category = "Cloud and data"
            job.company_priority = "high"
            job.company_priority_bonus = 12
            job_id = job.id
            db.commit()

        target = client.get(
            "/api/jobs",
            params={"target_group": "Target companies", "page_size": 100},
        )
        assert target.status_code == 200
        assert job_id in {item["id"] for item in target.json()["items"]}

        cloud = client.get(
            "/api/jobs",
            params={"target_group": "Cloud and data", "page_size": 100},
        )
        assert cloud.status_code == 200
        assert job_id in {item["id"] for item in cloud.json()["items"]}
