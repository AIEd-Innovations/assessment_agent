"""Checks that a request comes from a signed-in Cal Poly instructor.

The instructor UI signs in with Microsoft and sends the ID token as `Authorization: Bearer <token>`.
It is verified against Microsoft's published signing keys: signature, audience (our app's client ID),
issuer and tenant (Cal Poly's), expiry, and the email domain.

Off while AUTH_MS_CLIENT_ID is unset, so local development and the tests need no sign-in.
"""
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from assessment_agent import config


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Instructor:
    email: str
    name: str
    oid: str  # Microsoft's stable ID for the user (users.sso_subject in the shared database)


_key_clients: dict[str, jwt.PyJWKClient] = {}


def _signing_key(token: str, tenant: str):
    """Microsoft's public key for this token, fetched from the tenant's key set and cached."""
    client = _key_clients.setdefault(
        tenant, jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True)
    )
    return client.get_signing_key_from_jwt(token).key


def verify_id_token(token: str) -> Instructor:
    tenant = config.AUTH_MS_TENANT_ID
    try:
        claims = jwt.decode(
            token,
            _signing_key(token, tenant),
            algorithms=["RS256"],
            audience=config.AUTH_MS_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss"]},
            leeway=60,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid sign-in token: {exc}") from exc
    if claims.get("tid") != tenant:
        raise AuthError("This account is not from the allowed Microsoft directory")

    email = str(claims.get("preferred_username") or claims.get("email") or "").strip().lower()
    domain = config.AUTH_ALLOWED_EMAIL_DOMAIN
    local, _, host = email.rpartition("@")
    if not local or host != domain:
        raise AuthError(f"Only @{domain} accounts can use this service")
    return Instructor(email=email, name=str(claims.get("name") or email), oid=str(claims.get("oid") or ""))


def require_instructor(authorization: str | None = Header(None)) -> Instructor | None:
    """FastAPI dependency. None when sign-in is not configured; otherwise the verified instructor, or 401."""
    if not config.AUTH_MS_CLIENT_ID:
        return None
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return verify_id_token(token.strip())
    except AuthError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "Bearer"})
