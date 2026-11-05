from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import COOKIE, SESSION_MAX_AGE, _DUMMY_HASH, current_user, make_session_token, verify_password
from app.models import User
from app.schemas.common import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    """Accounts are created by the Corporation (no self-registration)."""
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok:
        raise HTTPException(401, "Invalid user ID or password")
    # Route Handler: the cookie is set on the response object we return through.
    response.set_cookie(COOKIE, make_session_token(user.id), max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
                        path="/")
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
