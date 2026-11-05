"""Demo auth: seeded users only (no self-registration). OTP is shown on screen in demo mode."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.actor import Actor
from app.core.db import get_db
from app.models import User
from app.models.enums import Role

COOKIE = "cf_session"
SESSION_MAX_AGE = 60 * 60 * 24
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="cf-session")
_otps: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def issue_otp(username: str) -> str:
    otp = f"{secrets.randbelow(1_000_000):06d}"
    with _lock:
        _otps[username] = (otp, time.time() + 300)
    return otp


def check_otp(username: str, otp: str) -> bool:
    with _lock:
        rec = _otps.get(username)
        if not rec or rec[1] < time.time() or not hmac.compare_digest(rec[0], otp):
            return False
        _otps.pop(username, None)
    return True


def make_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        return int(_serializer.loads(token, max_age=SESSION_MAX_AGE)["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    tok = request.cookies.get(COOKIE)
    uid = read_session_token(tok) if tok else None
    return db.get(User, uid) if uid else None


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(401, "Please log in")
    return user


def current_actor(user: User = Depends(current_user)) -> Actor:
    return Actor.from_user(user)


def require_roles(*roles: Role):
    def dep(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(403, f"This page is for {', '.join(r.value for r in roles)}")
        return actor

    return dep


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
