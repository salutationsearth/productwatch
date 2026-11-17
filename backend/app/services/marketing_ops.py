"""Operations used by the WatcherMart MCP server (external OpenAI marketing agent)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import MarketingEmail, Product, User, UserOffer, UserProductInterest
from backend.app.services.discounts import refresh_offers_for_user


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _hours_since(dt: datetime | None, now: datetime) -> float | None:
    dt = _aware(dt)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 3600.0


def list_customer_interests(
    db: Session,
    *,
    min_weight: float = 0.0,
    limit: int = 50,
    face_enrolled_only: bool = True,
) -> list[dict]:
    """Interest opportunities for the external marketing agent (includes PII for sending)."""
    now = datetime.now(timezone.utc)
    q = (
        db.query(UserProductInterest, User, Product)
        .join(User, User.id == UserProductInterest.user_id)
        .join(Product, Product.id == UserProductInterest.product_id)
        .filter(UserProductInterest.weight >= min_weight)
        .filter(User.email.isnot(None))
        .filter(User.is_rewards_member.is_(True))
    )
    if face_enrolled_only:
        q = q.filter(User.face_enrolled.is_(True))
    rows = q.order_by(UserProductInterest.weight.desc()).limit(limit).all()

    out: list[dict] = []
    for interest, user, product in rows:
        hours = _hours_since(interest.last_seen_at, now)
        recent_email = (
            db.query(MarketingEmail)
            .filter(
                MarketingEmail.user_id == user.id,
                MarketingEmail.product_id == product.id,
                MarketingEmail.status.like("sent%"),
            )
            .order_by(MarketingEmail.sent_at.desc())
            .first()
        )
        out.append(
            {
                "user_id": user.id,
                "customer_name": user.name,
                "customer_email": user.email,
                "face_enrolled": user.face_enrolled,
                "product_id": product.id,
                "product_name": product.name,
                "product_brand": product.brand,
                "product_category": product.category,
                "product_price": product.price,
                "competitor_group": product.competitor_group,
                "interest_weight": interest.weight,
                "first_seen_at": interest.first_seen_at.isoformat() if interest.first_seen_at else None,
                "last_seen_at": interest.last_seen_at.isoformat() if interest.last_seen_at else None,
                "hours_since_interest": round(hours, 3) if hours is not None else None,
                "last_emailed_at": user.last_marketing_email_at.isoformat()
                if user.last_marketing_email_at
                else None,
                "last_email_for_product_at": recent_email.sent_at.isoformat()
                if recent_email and recent_email.sent_at
                else None,
                "suggested_percent_off": settings.personalized_offer_percent,
            }
        )
    return out


def create_discount_link(
    db: Session,
    *,
    user_id: int,
    product_id: int,
    percent_off: float | None = None,
) -> dict:
    """
    Create a tracked discount claim link for a customer+product.
    Conversion/open/click are tracked via /t/* using the returned token.
    """
    user = db.get(User, user_id)
    product = db.get(Product, product_id)
    if not user:
        raise ValueError(f"Unknown user_id={user_id}")
    if not product:
        raise ValueError(f"Unknown product_id={product_id}")
    if not user.email:
        raise ValueError("User has no email on file")

    percent = float(percent_off if percent_off is not None else settings.personalized_offer_percent)
    refresh_offers_for_user(db, user.id)
    offer = (
        db.query(UserOffer)
        .filter(
            UserOffer.user_id == user.id,
            UserOffer.product_id == product.id,
            UserOffer.active.is_(True),
        )
        .order_by(UserOffer.percent_off.desc())
        .first()
    )
    if offer:
        offer.percent_off = max(offer.percent_off, percent)
        percent = offer.percent_off
    else:
        offer = UserOffer(
            user_id=user.id,
            product_id=product.id,
            percent_off=percent,
            scope="personalized",
            reason="External marketing agent offer",
            active=True,
        )
        db.add(offer)
        db.flush()

    interest = (
        db.query(UserProductInterest)
        .filter(
            UserProductInterest.user_id == user.id,
            UserProductInterest.product_id == product.id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    hours = _hours_since(interest.last_seen_at, now) if interest else None
    token = secrets.token_urlsafe(24)
    base = settings.public_base_url.rstrip("/")

    row = MarketingEmail(
        tracking_token=token,
        user_id=user.id,
        product_id=product.id,
        offer_id=offer.id,
        subject="(pending send)",
        body_text="",
        body_html="",
        percent_off=percent,
        agent_rationale="discount_link_created",
        interest_weight_at_send=interest.weight if interest else 0.0,
        interest_last_seen_at=_aware(interest.last_seen_at) if interest else None,
        hours_since_interest=hours,
        status="link_created",
        sent_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "token": token,
        "email_record_id": row.id,
        "user_id": user.id,
        "customer_email": user.email,
        "customer_name": user.name,
        "product_id": product.id,
        "product_name": product.name,
        "percent_off": percent,
        "claim_url": f"{base}/t/click/{token}",
        "offer_page_url": f"{base}/offer/{token}",
        "convert_url": f"{base}/t/convert/{token}",
        "open_pixel_url": f"{base}/t/open/{token}.gif",
        "status": row.status,
    }


def report_email_sent(
    db: Session,
    *,
    token: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    rationale: str | None = None,
) -> dict:
    """Mark a discount-link email as sent by the external agent (shows on manager dashboard)."""
    row = db.query(MarketingEmail).filter(MarketingEmail.tracking_token == token).first()
    if not row:
        raise ValueError(f"Unknown discount token={token}")

    user = db.get(User, row.user_id)
    product = db.get(Product, row.product_id)
    now = datetime.now(timezone.utc)

    row.subject = subject.strip()
    row.body_text = body_text.strip()
    if body_html and body_html.strip():
        row.body_html = body_html.strip()
    else:
        # Minimal HTML wrapper so offer page / outbox still render.
        paras = "".join(f"<p>{p}</p>" for p in body_text.strip().split("\n\n") if p.strip())
        claim = f"{settings.public_base_url.rstrip('/')}/t/click/{token}"
        row.body_html = (
            f"<div><p><strong>{subject}</strong></p>{paras}"
            f'<p><a href="{claim}">Claim your {row.percent_off:.0f}% off offer</a></p></div>'
        )
    row.agent_rationale = rationale or "reported_by_external_agent"
    row.status = "sent"
    row.sent_at = now
    if user:
        user.last_marketing_email_at = now
    db.commit()
    db.refresh(row)

    outbox = settings.outbox_dir / f"email_{row.id}_{token[:8]}.html"
    outbox.write_text(
        f"To: {user.email if user else '?'}\nSubject: {subject}\n\n{row.body_html}",
        encoding="utf-8",
    )

    print(
        f"\n===== EMAIL REPORTED (MCP) =====\n"
        f"To: {user.email if user else '?'}\n"
        f"Subject: {subject}\n"
        f"Product: {product.name if product else row.product_id} ({row.percent_off:.0f}% off)\n"
        f"Token: {token}\n"
        f"Outbox: {outbox}\n"
        f"================================\n",
        flush=True,
    )

    return {
        "email_record_id": row.id,
        "token": token,
        "status": row.status,
        "subject": row.subject,
        "customer_email": user.email if user else None,
        "product_name": product.name if product else None,
        "percent_off": row.percent_off,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "claim_url": f"{settings.public_base_url.rstrip('/')}/t/click/{token}",
        "offer_page_url": f"{settings.public_base_url.rstrip('/')}/offer/{token}",
    }


def list_sent_emails(db: Session, *, limit: int = 30) -> list[dict]:
    rows = (
        db.query(MarketingEmail, User, Product)
        .join(User, User.id == MarketingEmail.user_id)
        .join(Product, Product.id == MarketingEmail.product_id)
        .filter(MarketingEmail.status.like("sent%"))
        .order_by(MarketingEmail.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "email_record_id": email.id,
            "token": email.tracking_token,
            "subject": email.subject,
            "customer_email": user.email,
            "product_name": product.name,
            "percent_off": email.percent_off,
            "sent_at": email.sent_at.isoformat() if email.sent_at else None,
            "opened": email.opened_at is not None,
            "clicked": email.clicked_at is not None,
            "converted": email.converted_at is not None,
            "status": email.status,
        }
        for email, user, product in rows
    ]


def get_link_conversion(db: Session, token: str) -> dict:
    row = db.query(MarketingEmail).filter(MarketingEmail.tracking_token == token).first()
    if not row:
        raise ValueError(f"Unknown token={token}")
    product = db.get(Product, row.product_id)
    return {
        "token": token,
        "status": row.status,
        "product_name": product.name if product else None,
        "percent_off": row.percent_off,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "clicked_at": row.clicked_at.isoformat() if row.clicked_at else None,
        "converted_at": row.converted_at.isoformat() if row.converted_at else None,
        "opened": row.opened_at is not None,
        "clicked": row.clicked_at is not None,
        "converted": row.converted_at is not None,
    }
