"""Local mock LLM email drafter (no external AI API required)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


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


def _pick_angle(brief: DraftBrief) -> str:
    seed = f"{brief.product_name}|{brief.percent_off}|{brief.weight:.0f}|{brief.hours_since:.1f}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    angles = ("urgency", "value", "discovery", "loyalty")
    return angles[int(digest[:8], 16) % len(angles)]


def draft_marketing_email(brief: DraftBrief) -> EmailDraft:
    first = brief.name.split()[0]
    angle = _pick_angle(brief)
    freshness = "earlier today" if brief.hours_since < 12 else "over the last couple of days"
    intensity = "kept coming back to" if brief.weight >= 40 else "spent a moment with"

    if angle == "urgency":
        subject = f"{first}, your {brief.percent_off:.0f}% off {brief.product_name} won’t last"
        paragraphs = [
            f"You {intensity} {brief.product_name} on the shelf {freshness}. "
            f"We locked a members-only {brief.percent_off:.0f}% discount before the next restock rush.",
            f"Grab {brief.brand} while the offer is live — claim it online or show this email at checkout.",
        ]
    elif angle == "discovery":
        subject = f"A {brief.category} pick you noticed: {brief.percent_off:.0f}% off {brief.product_name}"
        paragraphs = [
            f"Looks like {brief.product_name} caught your eye {freshness}. "
            f"Here’s {brief.percent_off:.0f}% off from {brief.brand} to make trying it easy.",
            "Save the offer to your rewards wallet, or redeem in-store on your next visit.",
        ]
    elif angle == "loyalty":
        subject = f"Thanks for browsing, {first} — {brief.percent_off:.0f}% off {brief.product_name}"
        paragraphs = [
            f"As a WatcherMart rewards member, you get first dibs when something you noticed goes on promo. "
            f"{brief.product_name} is {brief.percent_off:.0f}% off for a limited window.",
            f"Enjoy the savings on {brief.brand}, and thanks for shopping with us.",
        ]
    else:
        subject = f"{first}, save {brief.percent_off:.0f}% on {brief.product_name}"
        paragraphs = [
            f"You {intensity} {brief.product_name} {freshness}, so we reserved a "
            f"{brief.percent_off:.0f}% member discount on {brief.brand}.",
            "Claim it with one tap, or show this email at the register. Offer available while supplies last.",
        ]

    return EmailDraft(
        subject=subject,
        paragraphs=paragraphs,
        angle=angle,
        provider="mock_llm",
        model="productwatch-local-drafter-v1",
    )
