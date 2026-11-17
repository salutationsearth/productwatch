"""Always-on marketing agent: decide when to email shoppers based on fresh interest."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import AgentRunLog, MarketingEmail, Product, User, UserOffer, UserProductInterest
from backend.app.services.discounts import refresh_offers_for_user
from backend.app.services.emailer import deliver_marketing_email

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


def _draft_with_openai(
    *,
    name: str,
    product_name: str,
    brand: str,
    percent_off: float,
    weight: float,
    hours_since: float,
    rationale: str,
) -> tuple[str, list[str]] | None:
    if not settings.openai_api_key:
        return None
    prompt = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write short supermarket rewards emails. Return JSON with keys "
                    "subject (string) and paragraphs (array of 2-3 short strings). "
                    "No emoji. Warm, specific, not creepy. Do not mention cameras or face scanning."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Shopper first name: {name.split()[0]}\n"
                    f"Product: {product_name} ({brand})\n"
                    f"Discount: {percent_off:.0f}%\n"
                    f"Interest weight: {weight:.1f}/100\n"
                    f"Hours since last aisle interest: {hours_since:.2f}\n"
                    f"Agent rationale: {rationale}\n"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=prompt,
            timeout=20.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        subject = str(data["subject"]).strip()
        paragraphs = [str(p).strip() for p in data["paragraphs"] if str(p).strip()]
        if subject and paragraphs:
            return subject, paragraphs
    except Exception as exc:  # noqa: BLE001 — fall back to template
        logger.warning("OpenAI draft failed: %s", exc)
    return None


def _draft_template(
    *,
    name: str,
    product_name: str,
    brand: str,
    percent_off: float,
    hours_since: float,
) -> tuple[str, list[str]]:
    first = name.split()[0]
    freshness = "earlier today" if hours_since < 12 else "recently"
    subject = f"{first}, {percent_off:.0f}% off {product_name} is waiting"
    paragraphs = [
        f"You spent a little time with {product_name} on the shelf {freshness} — "
        f"so we reserved a members-only {percent_off:.0f}% discount on {brand}.",
        "Show this email at checkout or tap through to save it to your rewards wallet. "
        "Offer applies to rewards members while supplies last.",
    ]
    return subject, paragraphs


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

            drafted = _draft_with_openai(
                name=user.name,
                product_name=product.name,
                brand=product.brand,
                percent_off=percent,
                weight=interest.weight,
                hours_since=hours,
                rationale=rationale,
            )
            if drafted is None:
                subject, paragraphs = _draft_template(
                    name=user.name,
                    product_name=product.name,
                    brand=product.brand,
                    percent_off=percent,
                    hours_since=hours,
                )
            else:
                subject, paragraphs = drafted

            deliver_marketing_email(
                db,
                user=user,
                product_id=product.id,
                product_name=product.name,
                percent_off=percent,
                subject=subject,
                paragraphs=paragraphs,
                rationale=rationale,
                interest_weight=interest.weight,
                interest_last_seen_at=_aware(interest.last_seen_at),
                hours_since_interest=hours,
                offer_id=offer.id if offer else None,
            )
            sent += 1
            notes.append(f"emailed product={product.sku} weight={interest.weight:.1f}")

        summary = (
            f"Reviewed {reviewed} interest rows; sent {sent} email(s). "
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
    logger.info("Marketing agent started (poll=%ss)", settings.agent_poll_seconds)


def stop_marketing_agent() -> None:
    if agent_state.stop_event:
        agent_state.stop_event.set()
    if agent_state.thread:
        agent_state.thread.join(timeout=2.0)
