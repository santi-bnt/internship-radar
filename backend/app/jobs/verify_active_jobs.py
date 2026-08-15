import asyncio

from app.services.search_runs import run_managed_search


def main() -> None:
    run = asyncio.run(run_managed_search("verification", "cron"))
    print("Verification skipped because another search is running." if run is None else
          f"Verification {run.status}: {run.jobs_updated} updated, {run.error_count} errors.")


if __name__ == "__main__":
    main()
