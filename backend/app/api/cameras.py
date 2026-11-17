from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Product, ProductZone
from backend.app.schemas import ZoneOut, ZonesReplace

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("/{camera_id}/zones", response_model=list[ZoneOut])
def get_zones(camera_id: str, db: Session = Depends(get_db)) -> list[ProductZone]:
    return (
        db.query(ProductZone)
        .filter(ProductZone.camera_id == camera_id)
        .order_by(ProductZone.id)
        .all()
    )


@router.put("/{camera_id}/zones", response_model=list[ZoneOut])
def replace_zones(camera_id: str, payload: ZonesReplace, db: Session = Depends(get_db)) -> list[ProductZone]:
    product_ids = {z.product_id for z in payload.zones}
    if product_ids:
        found = {p.id for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
        missing = product_ids - found
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown product_ids: {sorted(missing)}")

    db.query(ProductZone).filter(ProductZone.camera_id == camera_id).delete()
    zones: list[ProductZone] = []
    for zone in payload.zones:
        row = ProductZone(
            product_id=zone.product_id,
            camera_id=camera_id,
            x1=min(zone.x1, zone.x2),
            y1=min(zone.y1, zone.y2),
            x2=max(zone.x1, zone.x2),
            y2=max(zone.y1, zone.y2),
            label=zone.label,
        )
        db.add(row)
        zones.append(row)
    db.commit()
    for row in zones:
        db.refresh(row)
    return zones
