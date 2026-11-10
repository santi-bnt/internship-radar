"""Small per-host request pacing, shared across clients and event loops."""
import asyncio
from threading import Lock
from time import monotonic
from app.core.config import settings
from app.services.source_catalog import SOURCE_CATALOG

_guard = Lock()
_next_request = {}


async def pace_request(request):
    if settings.source_rate_limit_seconds <= 0:
        return  # Deterministic offline tests explicitly disable network waits.
    host = (request.headers.get("Host") or request.url.host or "").lower()
    kind = "freehire" if "freehire.me" in host else "web_search" if "tavily.com" in host else "workday" if "myworkday" in host else "greenhouse"
    interval = max(settings.source_rate_limit_seconds, SOURCE_CATALOG[kind]["minimum_interval_seconds"])
    with _guard:
        current = monotonic()
        due = max(current, _next_request.get(host, current))
        _next_request[host] = due + interval
    if due > current:
        await asyncio.sleep(due - current)


def request_hooks():
    return {"request": [pace_request]}
