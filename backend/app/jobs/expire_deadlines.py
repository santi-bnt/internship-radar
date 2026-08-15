import asyncio

from app.services.search_runs import run_managed_search


def main() -> int:
    run = asyncio.run(run_managed_search("expire_deadlines", "cron"))
    print(
        "Expiration skipped because another search is running."
        if run is None
        else f"Expired {run.jobs_expired} past-deadline jobs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
