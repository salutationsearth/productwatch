"""Discount / offer materialization (stub filled in discount commit)."""

from sqlalchemy.orm import Session

from backend.app.schemas import OfferOut


def list_user_offers(db: Session, user_id: int) -> list[OfferOut]:
    from backend.app.models import Product, UserOffer

    rows = (
        db.query(UserOffer, Product)
        .join(Product, Product.id == UserOffer.product_id)
        .filter(UserOffer.user_id == user_id, UserOffer.active.is_(True))
        .order_by(UserOffer.created_at.desc())
        .all()
    )
    return [
        OfferOut(
            id=offer.id,
            product_id=offer.product_id,
            percent_off=offer.percent_off,
            scope=offer.scope,
            reason=offer.reason,
            active=offer.active,
            product_name=product.name,
        )
        for offer, product in rows
    ]


def refresh_offers_for_user(db: Session, user_id: int) -> list[OfferOut]:
    """Placeholder — implemented with the discount engine."""
    return list_user_offers(db, user_id)
