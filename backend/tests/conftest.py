import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEST_DB = Path(__file__).parent / "_internship_radar_test.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SEARCH_SCHEDULER_ENABLED"] = "false"
os.environ["SOURCE_RATE_LIMIT_SECONDS"] = "0"
os.environ["DEMO_FEED_ENABLED"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["APP_ACCESS_ENABLED"] = "true"
os.environ["INTERNAL_API_SECRET"] = "test-internal-api-secret"
os.environ["USER_IDENTITY_SIGNING_SECRET"] = "test-user-identity-signing-secret"
os.environ["PRIMARY_USER_ID"] = "internship-radar-primary"
os.environ["AUTHORIZED_USER_EMAILS"] = (
    "candidate@example.com,alerts@example.com,alternate@example.com"
)
os.environ["EMAIL_RECIPIENT"] = "alerts@example.com"
os.environ["RESUME_EMAIL"] = "candidate@example.com"
os.environ["NOTIFICATION_EMAIL"] = "alerts@example.com"
os.environ["CANDIDATE_ACCOUNT_IDS"] = json.dumps({
    "secondary@example.com": "00000000-0000-5000-8000-000000000001",
    "tertiary@example.com": "00000000-0000-5000-8000-000000000002",
})


def security_headers(
    email: str = "candidate@example.com",
    *,
    subject: str = "internship-radar-primary",
    expires_offset: int = 60,
    signing_secret: str = "test-user-identity-signing-secret",
) -> dict[str, str]:
    now = int(time.time())
    payload = {
        "v": 1,
        "sub": subject,
        "email": email,
        "iat": now,
        "exp": now + expires_offset,
        "aud": "internship-radar-api",
        "purpose": "user_request",
        "nonce": str(uuid.uuid4()),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(signing_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {
        "x-internal-api-secret": "test-internal-api-secret",
        "x-user-identity": f"{encoded}.{signature}",
    }


@pytest.fixture
def profile():
    return {
        "graduation_year": 2028,
        "graduation_date": "2028-06-30",
        "degree_level_current": "BACHELORS",
        "degree_status": "IN_PROGRESS",
        "expected_graduation_date": "2028-06-30",
        "degree_field": "Robotics and Digital Systems Engineering",
        "veteran_status": "NOT_VETERAN",
        "military_status": "NONE",
        "military_spouse": False,
        "disability_status": "NO_DISABILITY",
        "current_service_member": False,
        "citizenship_country": "Mexico",
        "work_authorized_countries": ["Mexico"],
        "us_work_authorized": False,
        "requires_us_employment_sponsorship": True,
        "countries_to_search": ["Mexico", "United States", "Canada"],
        "include_remote": True,
        "only_remote": False,
        "remote_from_mexico_only": False,
        "include_hybrid": True,
        "include_onsite": True,
        "priority_alerts": True,
        "priority_minimum_score": 80,
        "alert_for_major_companies": True,
        "major_company_minimum_score": 70,
        "skills": [
            "C",
            "C++",
            "Python",
            "Java",
            "Linux",
            "Git",
            "Embedded Systems",
            "Firmware",
            "FPGA",
            "Verilog",
            "Digital Design",
            "Robotics",
            "Controls",
            "Testing",
        ],
        "skills_json": [
            "C", "C++", "Python", "Linux", "Git", "Embedded Systems",
            "Firmware", "FPGA", "Verilog", "Digital Design", "Robotics",
            "Controls", "Testing",
        ],
    }


@pytest.fixture
def base_job():
    return {
        "title": "Firmware Intern",
        "company": "Example",
        "location": "Guadalajara, Mexico",
        "country": "Mexico",
        "remote_type": "Hybrid",
        "employment_type": "Internship",
        "duration": "12 weeks",
        "description": "Build embedded firmware and test hardware.",
        "requirements": "Required: C, embedded systems, Linux, and Git.",
        "preferred_qualifications": "Preferred: Python and RTOS.",
        "posted_at": "2026-07-20T12:00:00Z",
        "first_seen_at": "2026-07-23T12:00:00Z",
        "official_status": "open",
        "verification_status": "verified",
        "last_verified_at": "2026-07-23T12:00:00Z",
        "area": "Firmware / Embedded",
        "company_importance": "Unknown",
        "remote_from_mexico_allowed": False,
        "is_active": True,
    }
