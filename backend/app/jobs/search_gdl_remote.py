import asyncio

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import SearchRun, UserProfile
from app.security.identity import JOSHUA_USER_ID
from app.services.search_runs import create_search_run, execute_search_run
from sqlalchemy import select


CRITERIA = {
    "cities": ["Guadalajara Metro"],
    "countries": ["Mexico"],
    "work_models": ["ON_SITE", "HYBRID", "REMOTE"],
    "remote_scopes": ["MEXICO", "LATAM", "GLOBAL", "COUNTRY_LIST"],
    "role_categories": [
        "SOFTWARE_ENGINEERING", "EMBEDDED_FIRMWARE", "ROBOTICS",
        "FPGA_DIGITAL_DESIGN", "HARDWARE_VALIDATION", "AI_MACHINE_LEARNING",
        "BACKEND", "FULL_STACK",
    ],
    "include_keywords": [
        "automation", "software validation", "debug", "semiconductor", "Verilog", "RTL",
    ],
    "posted_within_days": 30,
    "source_mode": "OFFICIAL_AND_COMMUNITY",
    "only_realistically_eligible": False,
    "include_unknown_eligibility": True,
    "limit": 100,
}


async def run() -> None:
    init_db()
    with SessionLocal() as db:
        owner_user_id = db.scalar(
            select(UserProfile.owner_user_id)
            .where(UserProfile.owner_user_id != JOSHUA_USER_ID)
            .order_by(UserProfile.id)
            .limit(1)
            .execution_options(skip_owner_scope=True)
        ) or settings.effective_primary_user_id
        search = create_search_run(
            db, search_type="criteria", trigger="gdl_remote_audit",
            criteria=CRITERIA, owner_user_id=owner_user_id,
        )
        run_id = search.id if search else None
    if run_id is None:
        print("Guadalajara / remote search skipped because another search is running.")
        return
    await execute_search_run(run_id)
    with SessionLocal() as db:
        result = db.get(SearchRun, run_id)
        print(
            f"SearchRun #{run_id}: {result.status}; {result.result_count} results; "
            f"{result.verified_count} verified; {result.error_count} source warnings."
        )


if __name__ == "__main__":
    asyncio.run(run())
