import asyncio

from app.services.search_runs import run_managed_search


def main() -> None:
    run = asyncio.run(run_managed_search("high_priority", "cron"))
    print("High-priority search skipped because another search is running." if run is None else
          f"High-priority search {run.status}: {run.jobs_added} added, {run.error_count} errors.")


if __name__ == "__main__":
    main()
