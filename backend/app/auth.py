"""Supabase JWT verification — supports both the legacy HS256 secret and
the newer asymmetric JWT Signing Keys (ES256/RS256 via JWKS).

Supabase has been migrating projects from a shared HS256 secret to per-
project asymmetric signing keys. The token's header tells us which is in
use:

* ``alg=HS256`` (no ``kid``) — verify with ``SUPABASE_JWT_SECRET``.
* ``alg=ES256`` or ``alg=RS256`` (with ``kid``) — fetch the public key
  from ``${SUPABASE_URL}/auth/v1/.well-known/jwks.json`` and verify with
  the key whose ``kid`` matches the token header.

The JWKS document is cached for an hour and re-fetched on cache miss
(e.g. after a key rotation).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Query, status
from jose import JWTError, jwt


# Algorithms we accept on incoming tokens. Supabase projects use one of
# these depending on whether they've been migrated to JWT Signing Keys.
_ALLOWED_ASYMMETRIC = ("ES256", "RS256")
_ALLOWED_SYMMETRIC = ("HS256",)
_JWKS_TTL_SECONDS = 3600


@dataclass(frozen=True)
class AuthUser:
    user_id: str  # UUID string from JWT `sub`
    email: str | None
    raw_token: str


def _jwt_secret() -> str | None:
    """Legacy HS256 secret, optional now that Signing Keys exist."""
    return os.getenv("SUPABASE_JWT_SECRET") or None


def _supabase_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set. Add it to backend/.env.")
    return url.rstrip("/")


# ── JWKS cache (process-local, thread-safe) ─────────────────────────────
_jwks_lock = threading.Lock()
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_at: float = 0.0


def _fetch_jwks(force: bool = False) -> dict[str, Any]:
    """Get Supabase's JWKS, cached for an hour. Thread-safe."""
    global _jwks_cache, _jwks_cache_at
    now = time.time()
    if not force and _jwks_cache and (now - _jwks_cache_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache

    with _jwks_lock:
        # Re-check inside the lock so concurrent callers don't all fetch.
        if not force and _jwks_cache and (time.time() - _jwks_cache_at) < _JWKS_TTL_SECONDS:
            return _jwks_cache
        url = f"{_supabase_url()}/auth/v1/.well-known/jwks.json"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"failed to fetch Supabase JWKS: {exc}",
            ) from exc
        _jwks_cache = payload
        _jwks_cache_at = time.time()
        return payload


def _find_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    keys = jwks.get("keys") or []
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
    # Fallback: if the JWKS only has one key and no kid was provided.
    return keys[0] if len(keys) == 1 else None


# ── Token verification ──────────────────────────────────────────────────


def _decode_with_retry(token: str, algorithms: list[str], key: Any) -> dict[str, Any]:
    return jwt.decode(
        token,
        key,
        algorithms=algorithms,
        audience="authenticated",
        options={"verify_aud": True, "verify_exp": True},
    )


def user_from_token(token: str) -> AuthUser:
    """Verify a JWT and return the authenticated user.

    Picks HS256 vs JWKS path based on the token header.
    Raises ``HTTPException(401)`` on any failure.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing auth token",
        )

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token header: {exc}",
        ) from exc

    alg = header.get("alg")
    kid = header.get("kid")

    payload: dict[str, Any]
    try:
        if alg in _ALLOWED_SYMMETRIC:
            secret = _jwt_secret()
            if not secret:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="server missing SUPABASE_JWT_SECRET for HS256 token",
                )
            payload = _decode_with_retry(token, list(_ALLOWED_SYMMETRIC), secret)
        elif alg in _ALLOWED_ASYMMETRIC:
            jwks = _fetch_jwks()
            jwk_data = _find_jwk(jwks, kid)
            if jwk_data is None:
                # Bust cache — possible key rotation since last fetch.
                jwks = _fetch_jwks(force=True)
                jwk_data = _find_jwk(jwks, kid)
            if jwk_data is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"no JWKS key matching kid={kid!r}",
                )
            payload = _decode_with_retry(token, [alg], jwk_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"unsupported alg: {alg!r}",
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
    """Auth for SSE / browser <a download>: accepts ?token=... since
    EventSource and download links can't set Authorization headers."""
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
