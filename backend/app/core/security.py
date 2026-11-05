"""Authentication: roster users only (no self-registration), username + password, signed session cookie."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.actor import Actor
from app.core.db import get_db
from app.models import User
from app.models.enums import Role

COOKIE = "cf_session"
SESSION_MAX_AGE = 60 * 60 * 12
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="cf-session")
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        algo, iterations, salt, digest = (stored or "").split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(calc, digest)


# A real hash to compare against when the user does not exist, so timing does not reveal valid user IDs.
_DUMMY_HASH = hash_password(secrets.token_hex(8), iterations=PBKDF2_ITERATIONS)


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
            raise HTTPException(403, "You do not have access to this page")
        return actor

    return dep


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
