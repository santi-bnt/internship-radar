from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitRule:
    key: str
    limit: int
    window_seconds: int


_buckets: dict[tuple[str, str], tuple[int, float]] = {}
_lock = threading.Lock()


def sensitive_operation(path: str, method: str) -> RateLimitRule | None:
    if path == "/api/extension/application-session/resume.pdf" and method == "GET":
        return RateLimitRule("extension-resume-download", 10, 60)
    if path.startswith("/api/extension/application-session/confirm-") and method == "POST":
        return RateLimitRule("extension-confirmation", 120, 3600)
    if path.startswith("/api/extension/application-session"):
        return RateLimitRule("extension-session", 600, 3600)
    if method == "POST" and path in {"/api/jobs/search", "/api/search-runs"}:
        return RateLimitRule("search", 5, 3600)
    if method == "POST" and path == "/api/jobs/import-url":
        return RateLimitRule("job-url-import", 20, 3600)
    if method == "POST" and (
        re.fullmatch(r"/api/jobs/\d+/resume/generate", path)
        or re.fullmatch(r"/api/talent-communities/[a-z0-9-]+/resumes", path)
        or path in {"/api/resume-studio/resumes", "/api/best-resume/versions", "/api/kospie/resumes"}
    ):
        return RateLimitRule("resume", settings.resume_generation_limit_per_hour, 3600)
    if method == "POST" and re.fullmatch(r"/api/talent-communities/[a-z0-9-]+/preview", path):
        return RateLimitRule("resume-preview", 60, 3600)
    if method == "POST" and path.startswith("/api/notifications/test-"):
        return RateLimitRule("test-email", 5, 3600)
    if method == "GET" and re.fullmatch(r"/api/generated-resumes/\d+/(pdf|tex)", path):
        return RateLimitRule("resume-download", 30, 60)
    if method in {"PUT", "POST", "DELETE", "PATCH"} and (
        path in {"/api/profile", "/api/resume-profile"}
        or path.startswith("/api/target-companies")
    ):
        return RateLimitRule("settings", 30, 3600)
    return None


def check_rate_limit(
    primary_user_id: str,
    rule: RateLimitRule,
    *,
    current_time: float | None = None,
) -> tuple[bool, int]:
    now = time.monotonic() if current_time is None else current_time
    key = (primary_user_id, rule.key)
    with _lock:
        count, reset_at = _buckets.get(key, (0, now + rule.window_seconds))
        if reset_at <= now:
            count, reset_at = 0, now + rule.window_seconds
        if count >= rule.limit:
            return False, max(1, int(reset_at - now))
        _buckets[key] = (count + 1, reset_at)
    return True, 0
