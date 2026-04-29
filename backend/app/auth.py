"""Supabase JWT verification.

Supabase issues HS256-signed JWTs containing the user's UUID in the ``sub``
claim. We verify every protected request by checking the signature against
``SUPABASE_JWT_SECRET`` (HMAC), checking the audience claim, and extracting
the user's ID and email.

Two interfaces are exposed:

* ``get_current_user`` — FastAPI dependency for routes that take an
  ``Authorization: Bearer <jwt>`` header.
* ``user_from_token`` — direct verification helper used by the SSE route,
  which can't take headers via ``EventSource`` and falls back to a query
  parameter.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from jose import JWTError, jwt


@dataclass(frozen=True)
class AuthUser:
    user_id: str  # UUID string from JWT `sub`
    email: str | None
    raw_token: str


def _jwt_secret() -> str:
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "SUPABASE_JWT_SECRET is not set. Add it to backend/.env."
        )
    return secret


def user_from_token(token: str) -> AuthUser:
    """Verify a JWT and return the authenticated user.

    Raises ``HTTPException(401)`` on any failure — invalid signature,
    expired token, missing required claims, etc.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing auth token",
        )

    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            # Supabase tokens have aud="authenticated" by default.
            audience="authenticated",
            options={"verify_aud": True, "verify_exp": True},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
        ) from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing sub claim",
        )

    return AuthUser(
        user_id=user_id,
        email=payload.get("email"),
        raw_token=token,
    )


def _strip_bearer(value: str) -> str:
    parts = value.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return value


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """FastAPI dependency for routes that require auth via Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
        )
    return user_from_token(_strip_bearer(authorization))


async def get_current_user_from_query(
    token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """Auth for SSE: accepts ?token=... since EventSource can't set headers.

    Header is preferred when both are present; the query fallback exists
    purely so the SSE EventSource API works.
    """
    if authorization:
        return user_from_token(_strip_bearer(authorization))
    if token:
        return user_from_token(token)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing token (Authorization header or ?token query param)",
    )


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
CurrentUserFromQuery = Annotated[AuthUser, Depends(get_current_user_from_query)]
