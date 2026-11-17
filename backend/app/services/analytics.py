"""Anonymous aggregate analytics for the marketing dashboard."""

from __future__ import annotations

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from backend.app.models import (
    InterestEvent,
    MarketingEmail,
    Product,
    User,
    UserProductInterest,
)
from backend.app.schemas import DashboardSummary, EmailFunnelAgg, ProductInterestAgg


def dashboard_summary(db: Session) -> DashboardSummary:
    rewards_members = db.query(User).filter(User.is_rewards_member.is_(True)).count()
    face_enrolled = db.query(User).filter(User.face_enrolled.is_(True)).count()
    products_tracked = db.query(Product).count()
    interest_events_total = db.query(InterestEvent).count()
    sent_filter = or_(
        MarketingEmail.status.like("sent%"),
        MarketingEmail.status == "converted",
    )
    emails_sent_total = db.query(MarketingEmail).filter(sent_filter).count()
    opens = (
        db.query(MarketingEmail)
        .filter(sent_filter, MarketingEmail.opened_at.isnot(None))
        .count()
    )
    clicks = (
        db.query(MarketingEmail)
        .filter(sent_filter, MarketingEmail.clicked_at.isnot(None))
        .count()
    )
    conversions = (
        db.query(MarketingEmail)
        .filter(sent_filter, MarketingEmail.converted_at.isnot(None))
        .count()
    )

    def rate(num: int, den: int) -> float:
        return round((num / den) * 100.0, 1) if den else 0.0

    # Product interest — counts/weights only, no user identifiers.
    interest_rows = (
        db.query(
            Product.id,
            Product.name,
            Product.brand,
            Product.category,
            func.count(UserProductInterest.id),
            func.coalesce(func.sum(UserProductInterest.weight), 0.0),
            func.coalesce(func.avg(UserProductInterest.weight), 0.0),
            func.max(UserProductInterest.last_seen_at),
        )
        .outerjoin(UserProductInterest, UserProductInterest.product_id == Product.id)
        .group_by(Product.id)
        .all()
    )
    event_counts = dict(
        db.query(InterestEvent.product_id, func.count(InterestEvent.id))
        .group_by(InterestEvent.product_id)
        .all()
    )
    product_interest = [
        ProductInterestAgg(
            product_id=pid,
            product_name=name,
            brand=brand,
            category=category,
            interested_shopper_count=int(shopper_count or 0),
            total_interest_weight=float(total_w or 0.0),
            avg_interest_weight=float(avg_w or 0.0),
            interest_event_count=int(event_counts.get(pid, 0)),
            last_interest_at=last_seen,
        )
        for pid, name, brand, category, shopper_count, total_w, avg_w, last_seen in interest_rows
    ]
    product_interest.sort(key=lambda r: r.total_interest_weight, reverse=True)

    funnel_rows = (
        db.query(
            Product.id,
            Product.name,
            func.count(MarketingEmail.id),
            func.sum(case((MarketingEmail.opened_at.isnot(None), 1), else_=0)),
            func.sum(case((MarketingEmail.clicked_at.isnot(None), 1), else_=0)),
            func.sum(case((MarketingEmail.converted_at.isnot(None), 1), else_=0)),
        )
        .outerjoin(
            MarketingEmail,
            and_(
                MarketingEmail.product_id == Product.id,
                or_(
                    MarketingEmail.status.like("sent%"),
                    MarketingEmail.status == "converted",
                ),
            ),
        )
        .group_by(Product.id)
        .all()
    )
    email_funnel = []
    for pid, name, sent, op, cl, conv in funnel_rows:
        sent_i = int(sent or 0)
        op_i = int(op or 0)
        cl_i = int(cl or 0)
        conv_i = int(conv or 0)
        email_funnel.append(
            EmailFunnelAgg(
                product_id=pid,
                product_name=name,
                emails_sent=sent_i,
                opens=op_i,
                clicks=cl_i,
                conversions=conv_i,
                open_rate=rate(op_i, sent_i),
                click_rate=rate(cl_i, sent_i),
                conversion_rate=rate(conv_i, sent_i),
            )
        )
    email_funnel.sort(key=lambda r: r.emails_sent, reverse=True)

    # Agent runs externally via MCP/OpenAI — no local agent cycle logs.
    recent_agent_runs: list[dict] = []

    return DashboardSummary(
        rewards_members=rewards_members,
        face_enrolled_members=face_enrolled,
        products_tracked=products_tracked,
        interest_events_total=interest_events_total,
        emails_sent_total=emails_sent_total,
        overall_open_rate=rate(opens, emails_sent_total),
        overall_click_rate=rate(clicks, emails_sent_total),
        overall_conversion_rate=rate(conversions, emails_sent_total),
        product_interest=product_interest,
        email_funnel=email_funnel,
        recent_agent_runs=recent_agent_runs,
    )
