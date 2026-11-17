from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import InterestEvent, Product, UserProductInterest
from backend.app.schemas import InterestOut


def get_or_create_interest(db: Session, user_id: int, product_id: int) -> UserProductInterest:
    row = (
        db.query(UserProductInterest)
        .filter(
            UserProductInterest.user_id == user_id,
            UserProductInterest.product_id == product_id,
        )
        .first()
    )
    if row:
        return row
    now = datetime.now(timezone.utc)
    row = UserProductInterest(
        user_id=user_id,
        product_id=product_id,
        weight=0.0,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row


def bump_interest(
    db: Session,
    user_id: int,
    product_id: int,
    dwell_seconds: float,
    camera_id: str,
    gaze_x: float | None = None,
    gaze_y: float | None = None,
    proximity: float = 0.0,
) -> UserProductInterest:
    """
    Additive capped weight update with diminishing returns for long stares.
    Timestamps every dwell so the marketing agent knows how fresh the interest is.
    """
    base = settings.weight_bump
    dwell_factor = min(dwell_seconds / settings.dwell_seconds, 3.0)
    prox_factor = 1.0 + min(max(proximity, 0.0), 0.15) * 2.0
    delta = base * dwell_factor * prox_factor
    now = datetime.now(timezone.utc)
    interest = get_or_create_interest(db, user_id, product_id)
    scale = 1.0 - (interest.weight / settings.weight_cap) * 0.7
    interest.weight = min(settings.weight_cap, interest.weight + delta * max(scale, 0.2))
    interest.updated_at = now
    interest.last_seen_at = now
    if interest.first_seen_at is None:
        interest.first_seen_at = now

    db.add(
        InterestEvent(
            user_id=user_id,
            product_id=product_id,
            camera_id=camera_id,
            dwell_seconds=dwell_seconds,
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(interest)
    return interest


def list_interests(db: Session, user_id: int) -> list[InterestOut]:
    rows = (
        db.query(UserProductInterest, Product)
        .join(Product, Product.id == UserProductInterest.product_id)
        .filter(UserProductInterest.user_id == user_id)
        .order_by(UserProductInterest.weight.desc())
        .all()
    )
    return [
        InterestOut(
            product_id=interest.product_id,
            weight=interest.weight,
            updated_at=interest.updated_at,
            first_seen_at=interest.first_seen_at,
            last_seen_at=interest.last_seen_at,
            product_name=product.name,
        )
        for interest, product in rows
    ]
