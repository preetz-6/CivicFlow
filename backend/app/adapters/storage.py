"""StorageAdapter: local /media folder + short-lived HMAC-signed URLs."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from pathlib import Path

from app.config import settings


class LocalStorageAdapter:
    def __init__(self, root: str):
        self.root = Path(root)

    def save(self, data: bytes, ext: str = ".jpg") -> str:
        rel = f"{time.strftime('%Y%m')}/{uuid.uuid4().hex}{ext}"
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return rel

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("bad path")
        return p

    def read(self, rel: str) -> bytes:
        return self.path(rel).read_bytes()


storage = LocalStorageAdapter(settings.media_root)


def _sig(att_id: int, exp: int) -> str:
    msg = f"{att_id}:{exp}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()[:32]


def signed_url(att_id: int, ttl: int | None = None) -> str:
    exp = int(time.time()) + (ttl or settings.media_url_ttl_s)
    return f"/api/v1/media/{att_id}?exp={exp}&sig={_sig(att_id, exp)}"


def verify(att_id: int, exp: int, sig: str) -> bool:
    return exp >= time.time() and hmac.compare_digest(_sig(att_id, exp), sig)


os.makedirs(settings.media_root, exist_ok=True)
