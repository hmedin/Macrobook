"""Verify Supabase Auth JWTs using the project's public signing keys (JWKS)."""
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

_bearer = HTTPBearer()
_jwks_client: jwt.PyJWKClient | None = None


def _client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(get_settings().jwks_url, cache_keys=True)
    return _jwks_client


def current_user_id(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    token = creds.credentials
    try:
        key = _client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{get_settings().supabase_url}/auth/v1",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return claims["sub"]
