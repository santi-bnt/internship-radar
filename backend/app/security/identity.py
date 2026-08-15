from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


AUDIENCE = "internship-radar-api"
PURPOSE = "user_request"
MAX_TOKEN_LIFETIME_SECONDS = 120
CLOCK_SKEW_SECONDS = 30


class IdentityValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedIdentity:
    primary_user_id: str
    authenticated_email: str
    issued_at: int
    expires_at: int
    nonce: str


def normalize_email(email: Any) -> str:
    return email.strip().lower() if isinstance(email, str) else ""


def is_authorized_email(email: Any) -> bool:
    normalized = normalize_email(email)
    return bool(normalized) and normalized in settings.authorized_email_set


def resolve_primary_user(email: Any) -> str | None:
    primary_user_id = settings.primary_user_id.strip()
    return primary_user_id if primary_user_id and is_authorized_email(email) else None


def _decode_payload(encoded: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(f"{encoded}{padding}".encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityValidationError("Malformed identity token.") from exc
    if not isinstance(payload, dict):
        raise IdentityValidationError("Malformed identity token.")
    return payload


def validate_user_identity(token: str | None, *, now: int | None = None) -> AuthenticatedIdentity:
    signing_secret = settings.user_identity_signing_secret.strip()
    if not signing_secret or not settings.primary_user_id.strip():
        raise IdentityValidationError("Identity verification is not configured.")
    if not token or token.count(".") != 1:
        raise IdentityValidationError("Missing identity token.")

    encoded_payload, supplied_signature = token.split(".", 1)
    expected_signature = hmac.new(
        signing_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        padding = "=" * (-len(supplied_signature) % 4)
        decoded_signature = base64.urlsafe_b64decode(
            f"{supplied_signature}{padding}".encode("ascii")
        )
    except (ValueError, UnicodeError) as exc:
        raise IdentityValidationError("Invalid identity signature.") from exc
    if not hmac.compare_digest(expected_signature, decoded_signature):
        raise IdentityValidationError("Invalid identity signature.")

    payload = _decode_payload(encoded_payload)
    required = {"v", "sub", "email", "iat", "exp", "aud", "purpose", "nonce"}
    if not required.issubset(payload):
        raise IdentityValidationError("Incomplete identity token.")
    if payload["v"] != 1 or payload["aud"] != AUDIENCE or payload["purpose"] != PURPOSE:
        raise IdentityValidationError("Invalid identity token scope.")
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        raise IdentityValidationError("Invalid identity timestamps.")

    current_time = int(time.time()) if now is None else now
    issued_at = payload["iat"]
    expires_at = payload["exp"]
    if issued_at > current_time + CLOCK_SKEW_SECONDS:
        raise IdentityValidationError("Identity token issued in the future.")
    if expires_at <= current_time or expires_at <= issued_at:
        raise IdentityValidationError("Identity token expired.")
    if expires_at - issued_at > MAX_TOKEN_LIFETIME_SECONDS:
        raise IdentityValidationError("Identity token lifetime is too long.")

    email = normalize_email(payload["email"])
    primary_user_id = resolve_primary_user(email)
    if not primary_user_id or payload["sub"] != primary_user_id:
        raise IdentityValidationError("Identity is not authorized.")
    nonce = payload["nonce"]
    if not isinstance(nonce, str) or not 8 <= len(nonce) <= 128:
        raise IdentityValidationError("Invalid identity nonce.")

    return AuthenticatedIdentity(
        primary_user_id=primary_user_id,
        authenticated_email=email,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
