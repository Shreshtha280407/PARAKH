"""Assessor/admin authentication only. Workers never log in -- see
docs/worker_capability_tokens.md for how worker-side requests are
authorised instead (an opaque per-assessment capability token, not a
username/password account).

Never log a password, a password hash, or a JWT. No code in this module
(or its callers) should ever pass one of those three to a logger/print.
"""
import datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-login-shape")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(user: models.User) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "sub": str(user.id),
        "role": user.role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid or expired token: {e}") from e


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(creds.credentials)
    user = db.get(models.User, int(claims["sub"]))
    if user is None or user.role != claims.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token no longer valid for this user")
    return user


def require_role(*roles: str):
    def _check(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{user.role}' cannot access this endpoint")
        return user

    return _check


require_assessor = require_role("assessor", "admin")
require_admin = require_role("admin")
