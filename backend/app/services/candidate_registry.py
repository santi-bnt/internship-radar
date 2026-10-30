"""Generic candidate seed schema; no personal account records are bundled."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class CandidateSeed:
    user_id: str
    email: str
    user_profile: dict[str, Any]
    resume_profile: dict[str, Any]
    application_profile: dict[str, Any]

INDEPENDENT_CANDIDATE_SEEDS: tuple[CandidateSeed, ...] = ()
