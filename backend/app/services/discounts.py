"""Discount / offer materialization from interest weights + member deals."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import Discount, DiscountScope, Product, User, UserOffer, UserProductInterest
from backend.app.schemas import OfferOut


def list_user_offers(db: Session, user_id: int) -> list[OfferOut]:
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


def _upsert_offer(
    db: Session,
    user_id: int,
    product_id: int,
    percent_off: float,
    scope: str,
    reason: str,
) -> UserOffer:
    existing = (
        db.query(UserOffer)
        .filter(
            UserOffer.user_id == user_id,
            UserOffer.product_id == product_id,
            UserOffer.scope == scope,
        )
        .first()
    )
    if existing:
        existing.percent_off = percent_off
        existing.reason = reason
        existing.active = True
        return existing
    offer = UserOffer(
        user_id=user_id,
        product_id=product_id,
        percent_off=percent_off,
        scope=scope,
        reason=reason,
        active=True,
    )
    db.add(offer)
    return offer


def refresh_offers_for_user(db: Session, user_id: int) -> list[OfferOut]:
    """
    Materialize offers:
    - personalized: products with interest weight >= threshold
    - competitor: sibling in same competitor_group (steal share)
    - member_general: active catalog discounts for rewards members
    """
    user = db.get(User, user_id)
    if not user:
        return []

    interests = (
        db.query(UserProductInterest)
        .filter(UserProductInterest.user_id == user_id)
        .all()
    )
    interest_by_product = {i.product_id: i.weight for i in interests}

    # Personalized + competitor from interest.
    for interest in interests:
        if interest.weight < settings.personalized_min_weight:
            continue
        product = db.get(Product, interest.product_id)
        if not product:
            continue

        catalog = (
            db.query(Discount)
            .filter(
                Discount.product_id == product.id,
                Discount.scope == DiscountScope.PERSONALIZED.value,
                Discount.active.is_(True),
                Discount.min_interest_weight <= interest.weight,
            )
            .order_by(Discount.percent_off.desc())
            .first()
        )
        percent = catalog.percent_off if catalog else settings.personalized_offer_percent
        _upsert_offer(
            db,
            user_id=user_id,
            product_id=product.id,
            percent_off=percent,
            scope=DiscountScope.PERSONALIZED.value,
            reason=f"Shown interest (weight={interest.weight:.1f})",
        )

        if product.competitor_group:
            competitors = (
                db.query(Product)
                .filter(
                    Product.competitor_group == product.competitor_group,
                    Product.id != product.id,
                )
                .all()
            )
            # Prefer competitor the shopper likes least (or unseen).
            competitors.sort(key=lambda p: interest_by_product.get(p.id, 0.0))
            if competitors:
                rival = competitors[0]
                rival_deal = (
                    db.query(Discount)
                    .filter(
                        Discount.product_id == rival.id,
                        Discount.scope == DiscountScope.COMPETITOR.value,
                        Discount.active.is_(True),
                    )
                    .order_by(Discount.percent_off.desc())
                    .first()
                )
                rival_pct = rival_deal.percent_off if rival_deal else settings.competitor_offer_percent
                _upsert_offer(
                    db,
                    user_id=user_id,
                    product_id=rival.id,
                    percent_off=rival_pct,
                    scope=DiscountScope.COMPETITOR.value,
                    reason=f"Competitor of {product.name}",
                )

    # General member discounts.
    if user.is_rewards_member:
        general = (
            db.query(Discount)
            .filter(
                Discount.scope == DiscountScope.MEMBER_GENERAL.value,
                Discount.active.is_(True),
            )
            .all()
        )
        for deal in general:
            _upsert_offer(
                db,
                user_id=user_id,
                product_id=deal.product_id,
                percent_off=deal.percent_off,
                scope=DiscountScope.MEMBER_GENERAL.value,
                reason=deal.title or "Rewards member discount",
            )

    db.commit()
    return list_user_offers(db, user_id)
