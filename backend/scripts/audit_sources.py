"""Read-only live audit for every configured official source."""

from __future__ import annotations

import asyncio
import json

from app.jobs.refresh import classify_source_failure
from app.sources.company_sources import OFFICIAL_COMPANY_SOURCES
from app.sources.registry import ADAPTERS


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
}


async def main() -> None:
    for source in OFFICIAL_COMPANY_SOURCES:
        try:
            adapter = ADAPTERS[source["source_type"]](
                source["company"], source["source_identifier"], source["source_url"],
                search_criteria=CRITERIA,
            )
            jobs = await adapter.collect()
            result = {
                "company": source["company"], "state": "HEALTHY",
                "jobs": len(jobs), "ids": [job.external_id for job in jobs[:10]],
            }
        except Exception as exc:
            state, status, message = classify_source_failure(exc)
            result = {
                "company": source["company"], "state": state,
                "http_status": status, "safe_error": message, "jobs": 0,
            }
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
