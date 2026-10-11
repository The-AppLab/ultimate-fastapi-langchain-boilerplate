"""Verify Supabase access tokens in FastAPI.

Supabase signs access tokens either with the project's legacy shared secret (HS256) or with
asymmetric signing keys published at {SUPABASE_URL}/auth/v1/.well-known/jwks.json (RS256/ES256).
Both are handled here. Send the token from your frontend as `Authorization: Bearer <access_token>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request, status

from app.config import Settings


@dataclass
class User:
    id: str
    email: str | None
    claims: dict[str, Any]


ANONYMOUS = User(id="anonymous", email=None, claims={})


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600)


def decode_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        alg = jwt.get_unverified_header(token).get("alg", "HS256")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise jwt.InvalidTokenError("HS256 token but SUPABASE_JWT_SECRET is not set")
            key: Any = settings.supabase_jwt_secret
        else:
            if not settings.supabase_url:
                raise jwt.InvalidTokenError(f"{alg} token but SUPABASE_URL is not set")
            jwks_url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["HS256", "RS256", "ES256"],
            audience=settings.jwt_audience,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    """FastAPI dependency: the signed-in Supabase user.

    With no Supabase settings in .env, auth is off and every request runs as "anonymous",
    so the quickstart works with only an OpenAI key. Set SUPABASE_URL and/or
    SUPABASE_JWT_SECRET before you put this on the internet.
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return ANONYMOUS
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    claims = decode_supabase_jwt(authorization.split(" ", 1)[1].strip(), settings)
    if claims.get("role") != "authenticated":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token is not for a signed-in user")
    return User(id=claims["sub"], email=claims.get("email"), claims=claims)
