from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.config import settings


AUDIENCE = "internship-radar-extension"
PURPOSE = "application_session"
DEFAULT_LIFETIME_SECONDS = 30 * 60
MAX_LIFETIME_SECONDS = 60 * 60
CLOCK_SKEW_SECONDS = 30
ALLOWED_SCOPES = frozenset(
    {
        "read_application_profile",
        "read_resume_version",
        "write_application_progress",
    }
)


class ApplicationTokenError(ValueError):
    pass


@dataclass(frozen=True)
class ApplicationSessionClaims:
    session_id: int
    owner_user_id: str
    scopes: frozenset[str]
    nonce: str
    issued_at: int
    expires_at: int

    def requires(self, scope: str) -> None:
        if scope not in self.scopes:
            raise ApplicationTokenError("Application session token lacks the required scope.")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}".encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ApplicationTokenError("Malformed application session token.") from exc


def _secret() -> bytes:
    secret = settings.user_identity_signing_secret.strip()
    if not secret:
        raise ApplicationTokenError("Application session token signing is not configured.")
    return secret.encode("utf-8")


def create_application_session_token(
    *,
    session_id: int,
    owner_user_id: str,
    nonce: str,
    scopes: Iterable[str] = ALLOWED_SCOPES,
    lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS,
    now: int | None = None,
) -> tuple[str, int]:
    normalized_scopes = sorted(set(scopes))
    if not normalized_scopes or not set(normalized_scopes).issubset(ALLOWED_SCOPES):
        raise ApplicationTokenError("Invalid application session token scopes.")
    if not 1 <= lifetime_seconds <= MAX_LIFETIME_SECONDS:
        raise ApplicationTokenError("Invalid application session token lifetime.")
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + lifetime_seconds
    payload = {
        "v": 1,
        "sub": owner_user_id,
        "sid": session_id,
        "iat": issued_at,
        "exp": expires_at,
        "aud": AUDIENCE,
        "purpose": PURPOSE,
        "nonce": nonce,
        "scopes": normalized_scopes,
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}", expires_at


def validate_application_session_token(
    token: str | None,
    *,
    required_scope: str | None = None,
    now: int | None = None,
) -> ApplicationSessionClaims:
    if not token or token.count(".") != 1:
        raise ApplicationTokenError("Missing application session token.")
    encoded, supplied_signature = token.split(".", 1)
    expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    supplied = _decode(supplied_signature)
    if not hmac.compare_digest(expected, supplied):
        raise ApplicationTokenError("Invalid application session token signature.")
    try:
        payload: dict[str, Any] = json.loads(_decode(encoded).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ApplicationTokenError("Malformed application session token.") from exc
    required = {"v", "sub", "sid", "iat", "exp", "aud", "purpose", "nonce", "scopes"}
    if not required.issubset(payload):
        raise ApplicationTokenError("Incomplete application session token.")
    if payload["v"] != 1 or payload["aud"] != AUDIENCE or payload["purpose"] != PURPOSE:
        raise ApplicationTokenError("Invalid application session token scope.")
    if not isinstance(payload["sid"], int) or payload["sid"] < 1:
        raise ApplicationTokenError("Invalid application session identifier.")
    if not isinstance(payload["sub"], str) or not payload["sub"]:
        raise ApplicationTokenError("Invalid application session owner.")
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        raise ApplicationTokenError("Invalid application session timestamps.")
    current = int(time.time()) if now is None else now
    if payload["iat"] > current + CLOCK_SKEW_SECONDS:
        raise ApplicationTokenError("Application session token issued in the future.")
    if payload["exp"] <= current or payload["exp"] <= payload["iat"]:
        raise ApplicationTokenError("Application session token expired.")
    if payload["exp"] - payload["iat"] > MAX_LIFETIME_SECONDS:
        raise ApplicationTokenError("Application session token lifetime is too long.")
    scopes = payload["scopes"]
    if not isinstance(scopes, list) or not scopes or not set(scopes).issubset(ALLOWED_SCOPES):
        raise ApplicationTokenError("Invalid application session token scopes.")
    nonce = payload["nonce"]
    if not isinstance(nonce, str) or not 16 <= len(nonce) <= 128:
        raise ApplicationTokenError("Invalid application session token nonce.")
    claims = ApplicationSessionClaims(
        session_id=payload["sid"],
        owner_user_id=payload["sub"],
        scopes=frozenset(scopes),
        nonce=nonce,
        issued_at=payload["iat"],
        expires_at=payload["exp"],
    )
    if required_scope:
        claims.requires(required_scope)
    return claims
