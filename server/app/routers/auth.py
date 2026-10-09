from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import _DUMMY_HASH, create_access_token, get_current_user, verify_password
from ..config import settings
from ..db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)) -> schemas.TokenOut:
    user = db.query(models.User).filter_by(email=body.email).one_or_none()
    # Constant-shape failure: a missing user and a wrong password both reach
    # verify_password (against a real, pre-computed dummy hash) so the
    # response doesn't leak which case occurred via timing or an early return.
    password_hash = user.password_hash if user and user.password_hash else _DUMMY_HASH
    ok = verify_password(body.password, password_hash)
    if not user or not user.password_hash or user.role not in ("assessor", "admin") or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect email or password")
    token = create_access_token(user)
    return schemas.TokenOut(access_token=token, expires_in_minutes=settings.jwt_expire_minutes)


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user)) -> models.User:
    return user
