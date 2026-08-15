from __future__ import annotations

import json
import logging


logger = logging.getLogger("app.security.audit")


def mask_email(email: str | None) -> str:
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        return "unknown"
    local, domain = normalized.split("@", 1)
    return f"{local[:1]}***@{domain}" if local and domain else "unknown"


def audit_event(
    event: str,
    *,
    email: str | None = None,
    resource: str | None = None,
    outcome: str = "accepted",
) -> None:
    payload = {
        "event": event[:80],
        "email": mask_email(email) if email else None,
        "resource": resource[:160] if resource else None,
        "outcome": outcome[:40],
    }
    logger.info("security_audit %s", json.dumps(payload, separators=(",", ":")))
