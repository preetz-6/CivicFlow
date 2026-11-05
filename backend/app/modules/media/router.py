from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.adapters.storage import storage, verify
from app.core.db import get_db
from app.models import Attachment

router = APIRouter(tags=["media"])


@router.get("/media/{att_id}")
def get_media(att_id: int, exp: int, sig: str, db: Session = Depends(get_db)):
    """Signed, short-lived URL. Signature is minted only by endpoints that already checked access."""
    if not verify(att_id, exp, sig):
        raise HTTPException(403, "Link expired")
    a = db.get(Attachment, att_id)
    if a is None:
        raise HTTPException(404)
    return FileResponse(storage.path(a.path), media_type=a.content_type,
                        headers={"Cache-Control": "private, max-age=300"})
