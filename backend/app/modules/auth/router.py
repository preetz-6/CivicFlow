from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.db import get_db
from app.core.security import (
    COOKIE, SESSION_MAX_AGE, check_otp, current_user, issue_otp, make_session_token,
)
from app.models import User
from app.schemas.common import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str


class LoginOut(BaseModel):
    sent_to: str
    otp_demo: str | None  # shown on screen in demo mode only


class VerifyIn(BaseModel):
    username: str
    otp: str


class DemoUser(BaseModel):
    username: str
    name: str
    role: str
    designation: str | None
    ward_id: str | None


@router.get("/demo-users", response_model=list[DemoUser])
def demo_users(db: Session = Depends(get_db)):
    """Listed on the login page (demo only)."""
    if not settings.demo_mode:
        return []
    return db.scalars(select(User).order_by(User.role, User.username)).all()


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    # No self-registration: only seeded roster users can log in.
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None:
        raise HTTPException(404, "No such user. Accounts are created by the Corporation, not by sign-up.")
    otp = issue_otp(user.username)
    masked = f"******{user.phone[-4:]}" if user.phone else "registered mobile"
    return LoginOut(sent_to=masked, otp_demo=otp if settings.demo_mode else None)


@router.post("/verify", response_model=UserOut)
def verify(body: VerifyIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None or not check_otp(user.username, body.otp.strip()):
        raise HTTPException(401, "Invalid or expired OTP")
    # Set the cookie on the response object we return through.
    response.set_cookie(
        COOKIE, make_session_token(user.id), max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", path="/",
    )
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
