import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import (
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    _DUMMY_HASH,
    create_access_token,
    get_current_user,
    verify_password,
)
from ..config import settings
from ..db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Secure=False only makes sense for plain-HTTP local dev; anything else
# must be served over TLS for a cookie-based session to be meaningful.
_COOKIE_SECURE = settings.app_env != "development"

# P10: naive per-process login throttle -- not a distributed rate limiter
# (a multi-replica deployment would need a shared store, e.g. Redis; this
# intentionally stays dependency-free for the single-process demo/pilot
# deployment this project actually ships). Keyed by lowercased email, not
# IP: the worker app never logs in, so only a small, known set of assessor
# emails exists, and this protects each account rather than each network
# path. Cleared on a successful login for that email.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 15 * 60
_failed_login_attempts: dict[str, list[float]] = {}


def _login_locked_out(email_key: str) -> bool:
    now = time.monotonic()
    attempts = [t for t in _failed_login_attempts.get(email_key, []) if now - t < _LOGIN_WINDOW_SECONDS]
    _failed_login_attempts[email_key] = attempts
    return len(attempts) >= _LOGIN_MAX_ATTEMPTS


def _record_failed_login(email_key: str) -> None:
    _failed_login_attempts.setdefault(email_key, []).append(time.monotonic())


def _set_session_cookies(response: Response, token: str) -> None:
    max_age = settings.jwt_expire_minutes * 60
    response.set_cookie(
        ACCESS_TOKEN_COOKIE, token, max_age=max_age, httponly=True, secure=_COOKIE_SECURE,
        samesite="lax", path="/", domain=settings.cookie_domain,
    )
    # NOT httponly -- the dashboard's JS must read this to echo it back as
    # the X-CSRF-Token header on mutating requests (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE, secrets.token_urlsafe(32), max_age=max_age, httponly=False, secure=_COOKIE_SECURE,
        samesite="lax", path="/", domain=settings.cookie_domain,
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)) -> schemas.TokenOut:
    email_key = body.email.strip().lower()
    if _login_locked_out(email_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in up to {_LOGIN_WINDOW_SECONDS // 60} minutes.",
        )
    user = db.query(models.User).filter_by(email=body.email).one_or_none()
    # Constant-shape failure: a missing user and a wrong password both reach
    # verify_password (against a real, pre-computed dummy hash) so the
    # response doesn't leak which case occurred via timing or an early return.
    password_hash = user.password_hash if user and user.password_hash else _DUMMY_HASH
    ok = verify_password(body.password, password_hash)
    if not user or not user.password_hash or user.role not in ("assessor", "admin") or not ok:
        _record_failed_login(email_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
    _failed_login_attempts.pop(email_key, None)
    token = create_access_token(user)
    # Cookies for the dashboard (browser auto-attaches them, no JS storage
    # needed); the body still carries the bearer token too, for API
    # clients/scripts/CI that don't want cookie-jar handling at all.
    _set_session_cookies(response, token)
    return schemas.TokenOut(access_token=token, expires_in_minutes=settings.jwt_expire_minutes)


@router.post("/logout")
def logout(response: Response) -> dict:
    # An HttpOnly cookie can't be cleared by JS -- the dashboard calling
    # this endpoint is the only way to actually end a cookie-based session.
    # domain must match what was set at login, or the browser won't drop it.
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/", domain=settings.cookie_domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=settings.cookie_domain)
    return {"status": "logged_out"}


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user)) -> models.User:
    return user
