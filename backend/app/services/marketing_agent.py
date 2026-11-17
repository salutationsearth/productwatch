"""Always-on marketing agent: decide when to email, then LLM-draft the copy."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import AgentRunLog, MarketingEmail, Product, User, UserOffer, UserProductInterest
from backend.app.services.discounts import refresh_offers_for_user
from backend.app.services.emailer import deliver_marketing_email
from backend.app.services.llm_drafter import DraftBrief, draft_marketing_email

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    enabled: bool = True
    last_run_at: datetime | None = None
    last_summary: str | None = None
    stop_event: threading.Event | None = None
    thread: threading.Thread | None = None


agent_state = AgentState()


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


def evaluate_candidate(
    db: Session,
    interest: UserProductInterest,
    user: User,
    product: Product,
    now: datetime,
) -> tuple[bool, str]:
    """Return (should_send, rationale)."""
    if not user.email or not user.is_rewards_member or not user.face_enrolled:
        return False, "skip: not a fully enrolled rewards member with email"

    if interest.weight < settings.agent_min_interest_weight:
        return False, f"skip: weight {interest.weight:.1f} below threshold"

    hours = _hours_since(interest.last_seen_at, now)
    if hours is None:
        return False, "skip: missing interest timestamp"
    if hours < settings.agent_min_hours_since_interest:
        return False, f"skip: interest too fresh ({hours:.2f}h) — wait for natural exit"
    if hours > settings.agent_max_hours_since_interest:
        return False, f"skip: interest too stale ({hours:.1f}h)"

    user_gap = _hours_since(user.last_marketing_email_at, now)
    if user_gap is not None and user_gap < settings.agent_cooldown_hours_per_user:
        return False, f"skip: user cooldown ({user_gap:.2f}h since last email)"

    recent_same = (
        db.query(MarketingEmail)
        .filter(
            MarketingEmail.user_id == user.id,
            MarketingEmail.product_id == product.id,
            MarketingEmail.sent_at
            >= now - timedelta(hours=settings.agent_cooldown_hours_per_product),
        )
        .first()
    )
    if recent_same:
        return False, "skip: already emailed this product recently"

    return (
        True,
        (
            f"send: weight={interest.weight:.1f}, last interest {hours:.2f}h ago, "
            f"member enrolled, no active cooldown for {product.name}"
        ),
    )


def run_agent_once(db: Session | None = None) -> AgentRunLog:
    own_session = db is None
    db = db or SessionLocal()
    now = datetime.now(timezone.utc)
    reviewed = 0
    sent = 0
    notes: list[str] = []

    try:
        interests = (
            db.query(UserProductInterest)
            .filter(UserProductInterest.weight >= settings.agent_min_interest_weight)
            .order_by(UserProductInterest.weight.desc())
            .limit(50)
            .all()
        )
        for interest in interests:
            reviewed += 1
            user = db.get(User, interest.user_id)
            product = db.get(Product, interest.product_id)
            if not user or not product:
                continue
            ok, rationale = evaluate_candidate(db, interest, user, product, now)
            if not ok:
                continue

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
            percent = offer.percent_off if offer else settings.personalized_offer_percent
            hours = _hours_since(interest.last_seen_at, now) or 0.0

            draft = draft_marketing_email(
                DraftBrief(
                    name=user.name,
                    product_name=product.name,
                    brand=product.brand,
                    category=product.category,
                    percent_off=percent,
                    weight=interest.weight,
                    hours_since=hours,
                    rationale=rationale,
                )
            )
            full_rationale = (
                f"{rationale} | llm={draft.provider}/{draft.model} angle={draft.angle}"
            )

            deliver_marketing_email(
                db,
                user=user,
                product_id=product.id,
                product_name=product.name,
                percent_off=percent,
                subject=draft.subject,
                paragraphs=draft.paragraphs,
                rationale=full_rationale,
                interest_weight=interest.weight,
                interest_last_seen_at=_aware(interest.last_seen_at),
                hours_since_interest=hours,
                offer_id=offer.id if offer else None,
            )
            sent += 1
            notes.append(
                f"emailed product={product.sku} via {draft.provider} angle={draft.angle}"
            )

        summary = (
            f"Reviewed {reviewed} interest rows; sent {sent} email(s) "
            f"(llm_provider={settings.llm_provider}). "
            + ("; ".join(notes) if notes else "No sends this cycle.")
        )
        log = AgentRunLog(
            candidates_reviewed=reviewed,
            emails_sent=sent,
            summary=summary,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        agent_state.last_run_at = now
        agent_state.last_summary = summary
        return log
    finally:
        if own_session:
            db.close()


def _loop() -> None:
    assert agent_state.stop_event is not None
    while not agent_state.stop_event.is_set():
        if agent_state.enabled and settings.agent_enabled:
            try:
                run_agent_once()
            except Exception:  # noqa: BLE001
                logger.exception("Marketing agent cycle failed")
        agent_state.stop_event.wait(settings.agent_poll_seconds)


def start_marketing_agent() -> None:
    if agent_state.thread and agent_state.thread.is_alive():
        return
    agent_state.enabled = settings.agent_enabled
    agent_state.stop_event = threading.Event()
    agent_state.thread = threading.Thread(target=_loop, name="marketing-agent", daemon=True)
    agent_state.thread.start()
    logger.info(
        "Marketing agent started (poll=%ss, llm=%s, email=%s)",
        settings.agent_poll_seconds,
        settings.llm_provider,
        settings.email_provider,
    )


def stop_marketing_agent() -> None:
    if agent_state.stop_event:
        agent_state.stop_event.set()
    if agent_state.thread:
        agent_state.thread.join(timeout=2.0)
