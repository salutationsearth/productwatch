"""LLM email-drafting agent.

Default provider is a local mock LLM (no API key). Swap to OpenAI later with
PW_LLM_PROVIDER=openai and PW_OPENAI_API_KEY=...
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the WatcherMart marketing copy agent for a supermarket rewards program. "
    "Draft a short promotional email. Return JSON with keys: "
    "subject (string), paragraphs (array of 2-3 short strings), "
    "angle (one of: urgency, value, discovery, loyalty). "
    "Rules: warm and specific; no emoji; never mention cameras, face scanning, or surveillance; "
    "do not invent medical claims; keep under ~120 words total."
)


@dataclass
class DraftBrief:
    name: str
    product_name: str
    brand: str
    category: str
    percent_off: float
    weight: float
    hours_since: float
    rationale: str


@dataclass
class EmailDraft:
    subject: str
    paragraphs: list[str]
    angle: str
    provider: str
    model: str
    prompt_preview: str


def _user_prompt(brief: DraftBrief) -> str:
    first = brief.name.split()[0]
    return (
        f"Shopper first name: {first}\n"
        f"Product: {brief.product_name}\n"
        f"Brand: {brief.brand}\n"
        f"Category: {brief.category}\n"
        f"Discount: {brief.percent_off:.0f}%\n"
        f"Interest weight: {brief.weight:.1f}/100\n"
        f"Hours since last aisle interest: {brief.hours_since:.2f}\n"
        f"Decision rationale: {brief.rationale}\n"
        "Write the email now."
    )


def _parse_draft_json(content: str, provider: str, model: str, prompt_preview: str) -> EmailDraft | None:
    try:
        data = json.loads(content)
        subject = str(data["subject"]).strip()
        paragraphs = [str(p).strip() for p in data["paragraphs"] if str(p).strip()]
        angle = str(data.get("angle", "value")).strip() or "value"
        if subject and paragraphs:
            return EmailDraft(
                subject=subject,
                paragraphs=paragraphs,
                angle=angle,
                provider=provider,
                model=model,
                prompt_preview=prompt_preview,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse LLM draft JSON: %s", exc)
    return None


def _draft_with_openai(brief: DraftBrief) -> EmailDraft | None:
    if not settings.openai_api_key:
        return None
    user = _user_prompt(brief)
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
            timeout=20.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_draft_json(
            content,
            provider="openai",
            model=settings.openai_model,
            prompt_preview=user[:240],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI draft failed, falling back to mock LLM: %s", exc)
        return None


def _pick_angle(brief: DraftBrief) -> str:
    seed = f"{brief.product_name}|{brief.percent_off}|{brief.weight:.0f}|{brief.hours_since:.1f}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    angles = ("urgency", "value", "discovery", "loyalty")
    return angles[int(digest[:8], 16) % len(angles)]


def _draft_with_mock_llm(brief: DraftBrief) -> EmailDraft:
    """
    Local stand-in for an LLM: same I/O contract (system+user → JSON draft),
    with angle selection and copy variation so the agent still feels generative.
    """
    first = brief.name.split()[0]
    angle = _pick_angle(brief)
    freshness = "earlier today" if brief.hours_since < 12 else "over the last couple of days"
    intensity = "kept coming back to" if brief.weight >= 40 else "spent a moment with"

    if angle == "urgency":
        subject = f"{first}, your {brief.percent_off:.0f}% off {brief.product_name} won’t last"
        paragraphs = [
            f"You {intensity} {brief.product_name} on the shelf {freshness}. "
            f"We locked a members-only {brief.percent_off:.0f}% discount before the next restock rush.",
            f"Grab {brief.brand} while the offer is live — show this email at checkout or claim it online.",
        ]
    elif angle == "discovery":
        subject = f"A {brief.category} pick you noticed: {brief.percent_off:.0f}% off {brief.product_name}"
        paragraphs = [
            f"Looks like {brief.product_name} caught your eye {freshness}. "
            f"Here’s {brief.percent_off:.0f}% off from {brief.brand} to make trying it easy.",
            "Save the offer to your rewards wallet, or redeem in-store on your next pass through the aisle.",
        ]
    elif angle == "loyalty":
        subject = f"Thanks for browsing, {first} — {brief.percent_off:.0f}% off {brief.product_name}"
        paragraphs = [
            f"As a WatcherMart rewards member, you get first dibs when something you noticed goes on promo. "
            f"{brief.product_name} is {brief.percent_off:.0f}% off for a limited window.",
            f"Enjoy the savings on {brief.brand}, and thanks for shopping with us.",
        ]
    else:  # value
        subject = f"{first}, save {brief.percent_off:.0f}% on {brief.product_name}"
        paragraphs = [
            f"You {intensity} {brief.product_name} {freshness}, so we reserved a "
            f"{brief.percent_off:.0f}% member discount on {brief.brand}.",
            "Claim it with one tap, or show this email at the register. Offer available while supplies last.",
        ]

    # Simulate the model returning JSON (same shape as a real LLM).
    fake_json = json.dumps(
        {"subject": subject, "paragraphs": paragraphs, "angle": angle},
        ensure_ascii=True,
    )
    draft = _parse_draft_json(
        fake_json,
        provider="mock_llm",
        model="productwatch-local-drafter-v1",
        prompt_preview=_user_prompt(brief)[:240],
    )
    assert draft is not None
    return draft


def draft_marketing_email(brief: DraftBrief) -> EmailDraft:
    """Public entry: always returns an LLM-shaped draft (mock by default)."""
    provider = (settings.llm_provider or "mock").lower().strip()
    if provider == "openai":
        drafted = _draft_with_openai(brief)
        if drafted:
            return drafted
        logger.info("OpenAI unavailable; using mock LLM drafter")
    return _draft_with_mock_llm(brief)
