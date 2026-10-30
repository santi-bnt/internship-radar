from typing import Any


def is_user_priority_pinned(job: Any) -> bool:
    raw = getattr(job, "raw_data", None)
    pin = raw.get("_radar_user_priority") if isinstance(raw, dict) else None
    return isinstance(pin, dict) and pin.get("owner_user_id") == getattr(job, "owner_user_id", None) and bool(pin.get("owner_user_id"))
