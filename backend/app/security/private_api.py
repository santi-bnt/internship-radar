from fastapi import HTTPException, Request
from app.security.identity import AuthenticatedIdentity


def require_private_api(request: Request) -> str:
    identity = getattr(request.state, "authenticated_identity", None)
    if not isinstance(identity, AuthenticatedIdentity):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return identity.primary_user_id
