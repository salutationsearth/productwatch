"""API for the local aisle computer-vision client (no server-side webcam)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import get_db
from backend.app.models import FaceEmbedding, Product, ProductZone, User
from backend.app.schemas import InterestOut, ZoneOut
from backend.app.services.discounts import refresh_offers_for_user
from backend.app.services.face import face_service
from backend.app.services.interest import bump_interest, list_interests

router = APIRouter(prefix="/api/aisle", tags=["aisle-client"])


def require_aisle_key(
    x_aisle_key: str | None = Header(default=None, alias="X-Aisle-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    expected = settings.aisle_api_key
    provided = x_aisle_key
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    if not expected or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid aisle API key")


class AisleProductOut(BaseModel):
    id: int
    name: str
    brand: str
    category: str
    price: float


class FaceEnrollmentOut(BaseModel):
    user_id: int
    name: str
    embedding: list[float]


class AisleBootstrapOut(BaseModel):
    camera_id: str
    zone_ref_width: float
    zone_ref_height: float
    dwell_seconds: float
    products: list[AisleProductOut]
    zones: list[ZoneOut]
    face_enrollments: list[FaceEnrollmentOut]


class InterestEventIn(BaseModel):
    user_id: int
    product_id: int
    dwell_seconds: float = Field(gt=0)
    camera_id: str = "webcam-0"
    gaze_x: float | None = None
    gaze_y: float | None = None
    proximity: float = 0.0


class InterestEventOut(BaseModel):
    user_id: int
    product_id: int
    weight: float
    product_name: str | None = None
    last_seen_at: str | None = None


class IdentifyOut(BaseModel):
    user_id: int | None
    distance: float | None
    matched: bool


@router.get("/bootstrap", response_model=AisleBootstrapOut, dependencies=[Depends(require_aisle_key)])
def aisle_bootstrap(camera_id: str = "webcam-0", db: Session = Depends(get_db)) -> AisleBootstrapOut:
    products = db.query(Product).order_by(Product.id).all()
    zones = (
        db.query(ProductZone)
        .filter(ProductZone.camera_id == camera_id)
        .order_by(ProductZone.id)
        .all()
    )
    enrollments: list[FaceEnrollmentOut] = []
    rows = (
        db.query(FaceEmbedding, User)
        .join(User, User.id == FaceEmbedding.user_id)
        .filter(User.face_enrolled.is_(True))
        .all()
    )
    # Latest embedding per user
    seen: set[int] = set()
    for emb, user in sorted(rows, key=lambda r: r[0].id, reverse=True):
        if user.id in seen:
            continue
        seen.add(user.id)
        enrollments.append(
            FaceEnrollmentOut(
                user_id=user.id,
                name=user.name,
                embedding=json.loads(emb.embedding),
            )
        )

    return AisleBootstrapOut(
        camera_id=camera_id,
        zone_ref_width=settings.zone_ref_width,
        zone_ref_height=settings.zone_ref_height,
        dwell_seconds=settings.dwell_seconds,
        products=[
            AisleProductOut(
                id=p.id, name=p.name, brand=p.brand, category=p.category, price=p.price
            )
            for p in products
        ],
        zones=zones,
        face_enrollments=enrollments,
    )


@router.post("/interest", response_model=InterestEventOut, dependencies=[Depends(require_aisle_key)])
def report_interest(payload: InterestEventIn, db: Session = Depends(get_db)) -> InterestEventOut:
    user = db.get(User, payload.user_id)
    product = db.get(Product, payload.product_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    interest = bump_interest(
        db,
        user_id=payload.user_id,
        product_id=payload.product_id,
        dwell_seconds=payload.dwell_seconds,
        camera_id=payload.camera_id,
        gaze_x=payload.gaze_x,
        gaze_y=payload.gaze_y,
        proximity=payload.proximity,
    )
    refresh_offers_for_user(db, payload.user_id)
    print(
        f"[aisle] interest user={payload.user_id} product={product.name} "
        f"weight={interest.weight:.1f} dwell={payload.dwell_seconds:.1f}s",
        flush=True,
    )
    return InterestEventOut(
        user_id=payload.user_id,
        product_id=payload.product_id,
        weight=interest.weight,
        product_name=product.name,
        last_seen_at=interest.last_seen_at.isoformat() if interest.last_seen_at else None,
    )


@router.post("/identify", response_model=IdentifyOut, dependencies=[Depends(require_aisle_key)])
async def identify_shopper(
    frame: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> IdentifyOut:
    """Optional server-side face match from one uploaded JPEG (no webcam on server)."""
    blob = await frame.read()
    try:
        image = face_service.decode_image_bytes(blob)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    emb = face_service.embed_largest(image)
    if emb is None:
        return IdentifyOut(user_id=None, distance=None, matched=False)
    uid, dist = face_service.match_user(db, emb)
    return IdentifyOut(user_id=uid, distance=dist, matched=uid is not None)


@router.get("/users/{user_id}/interests", response_model=list[InterestOut], dependencies=[Depends(require_aisle_key)])
def aisle_user_interests(user_id: int, db: Session = Depends(get_db)) -> list[InterestOut]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return list_interests(db, user_id)
