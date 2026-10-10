import secrets

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


def _set_session_cookies(response: Response, token: str) -> None:
    max_age = settings.jwt_expire_minutes * 60
    response.set_cookie(
        ACCESS_TOKEN_COOKIE, token, max_age=max_age, httponly=True, secure=_COOKIE_SECURE,
        samesite="lax", path="/",
    )
    # NOT httponly -- the dashboard's JS must read this to echo it back as
    # the X-CSRF-Token header on mutating requests (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE, secrets.token_urlsafe(32), max_age=max_age, httponly=False, secure=_COOKIE_SECURE,
        samesite="lax", path="/",
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)) -> schemas.TokenOut:
    user = db.query(models.User).filter_by(email=body.email).one_or_none()
    # Constant-shape failure: a missing user and a wrong password both reach
    # verify_password (against a real, pre-computed dummy hash) so the
    # response doesn't leak which case occurred via timing or an early return.
    password_hash = user.password_hash if user and user.password_hash else _DUMMY_HASH
    ok = verify_password(body.password, password_hash)
    if not user or not user.password_hash or user.role not in ("assessor", "admin") or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
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
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user)) -> models.User:
    return user
