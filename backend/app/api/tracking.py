from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import get_db
from backend.app.models import MarketingEmail

router = APIRouter(prefix="/t", tags=["tracking"])

# 1x1 transparent GIF
_PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00"
    b"\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _get_email(db: Session, token: str) -> MarketingEmail:
    row = db.query(MarketingEmail).filter(MarketingEmail.tracking_token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown tracking token")
    return row


@router.get("/open/{token}.gif")
def track_open(token: str, db: Session = Depends(get_db)) -> Response:
    token = token.removesuffix(".gif")
    row = _get_email(db, token)
    if row.opened_at is None:
        row.opened_at = datetime.now(timezone.utc)
        db.commit()
    return Response(content=_PIXEL, media_type="image/gif")


@router.get("/click/{token}")
def track_click(token: str, db: Session = Depends(get_db)) -> RedirectResponse:
    row = _get_email(db, token)
    now = datetime.now(timezone.utc)
    if row.opened_at is None:
        row.opened_at = now
    if row.clicked_at is None:
        row.clicked_at = now
    db.commit()
    # Demo landing: outbox preview page
    return RedirectResponse(url=f"{settings.public_base_url}/offer/{token}", status_code=302)


@router.get("/convert/{token}")
def track_convert(token: str, db: Session = Depends(get_db)) -> RedirectResponse:
    row = _get_email(db, token)
    now = datetime.now(timezone.utc)
    if row.opened_at is None:
        row.opened_at = now
    if row.clicked_at is None:
        row.clicked_at = now
    if row.converted_at is None:
        row.converted_at = now
        row.status = "converted"
    db.commit()
    return RedirectResponse(url=f"{settings.public_base_url}/offer/{token}?redeemed=1", status_code=302)
