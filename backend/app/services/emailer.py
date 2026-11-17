"""Deliver marketing emails: always write outbox; optionally send via Resend or SMTP."""

from __future__ import annotations

import logging
import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import MarketingEmail, User

logger = logging.getLogger(__name__)


def _tracking_urls(token: str) -> dict[str, str]:
    base = settings.public_base_url.rstrip("/")
    return {
        "open": f"{base}/t/open/{token}.gif",
        "click": f"{base}/t/click/{token}",
        "convert": f"{base}/t/convert/{token}",
    }


def build_email_html(
    *,
    name: str,
    product_name: str,
    percent_off: float,
    body_paragraphs: list[str],
    token: str,
) -> str:
    urls = _tracking_urls(token)
    paras = "".join(f"<p>{p}</p>" for p in body_paragraphs)
    return f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;background:#0f1410;color:#e8efe6;padding:32px;">
  <div style="max-width:560px;margin:0 auto;background:#1a221c;padding:28px;border:1px solid #2d3b30;">
    <div style="font-size:13px;letter-spacing:0.18em;text-transform:uppercase;color:#8fb389;">ProductWatch Rewards</div>
    <h1 style="font-weight:500;font-size:28px;margin:12px 0 8px;">Hi {name.split()[0]},</h1>
    <p style="font-size:20px;color:#c6e2bf;">{percent_off:.0f}% off {product_name}</p>
    {paras}
    <p style="margin-top:24px;">
      <a href="{urls['click']}" style="display:inline-block;background:#c6e2bf;color:#122016;padding:12px 18px;text-decoration:none;font-weight:600;">
        Claim your offer
      </a>
    </p>
    <p style="font-size:12px;color:#7a8a7c;margin-top:28px;">
      Already bought it in-store? <a href="{urls['convert']}" style="color:#a8c4a3;">Mark as redeemed</a>
    </p>
  </div>
  <img src="{urls['open']}" width="1" height="1" alt="" />
</body></html>"""


def _send_resend(*, to_email: str, subject: str, html: str, text: str) -> str | None:
    if not settings.resend_api_key:
        return None
    payload = {
        "from": f"{settings.marketing_from_name} <{settings.marketing_from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json=payload,
        timeout=20.0,
    )
    resp.raise_for_status()
    return str(resp.json().get("id") or "resend-ok")


def _send_smtp(*, to_email: str, subject: str, html: str, text: str) -> str | None:
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        return None
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.marketing_from_name} <{settings.marketing_from_email}>"
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)
    return "smtp-ok"


def _try_send_live(*, to_email: str, subject: str, html: str, text: str) -> tuple[str, str | None]:
    """Returns (channel, provider_id). channel is outbox|resend|smtp."""
    provider = (settings.email_provider or "outbox").lower().strip()
    try:
        if provider == "resend":
            pid = _send_resend(to_email=to_email, subject=subject, html=html, text=text)
            if pid:
                return "resend", pid
        if provider == "smtp":
            pid = _send_smtp(to_email=to_email, subject=subject, html=html, text=text)
            if pid:
                return "smtp", pid
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live email send failed (%s); kept outbox copy: %s", provider, exc)
    return "outbox", None


def deliver_marketing_email(
    db: Session,
    *,
    user: User,
    product_id: int,
    product_name: str,
    percent_off: float,
    subject: str,
    paragraphs: list[str],
    rationale: str,
    interest_weight: float,
    interest_last_seen_at: datetime | None,
    hours_since_interest: float | None,
    offer_id: int | None = None,
) -> MarketingEmail:
    token = secrets.token_urlsafe(24)
    body_text = "\n\n".join(paragraphs)
    body_html = build_email_html(
        name=user.name,
        product_name=product_name,
        percent_off=percent_off,
        body_paragraphs=paragraphs,
        token=token,
    )
    row = MarketingEmail(
        tracking_token=token,
        user_id=user.id,
        product_id=product_id,
        offer_id=offer_id,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        percent_off=percent_off,
        agent_rationale=rationale,
        interest_weight_at_send=interest_weight,
        interest_last_seen_at=interest_last_seen_at,
        hours_since_interest=hours_since_interest,
        status="sent",
        sent_at=datetime.now(timezone.utc),
    )
    db.add(row)
    user.last_marketing_email_at = row.sent_at
    db.commit()
    db.refresh(row)

    channel, provider_id = _try_send_live(
        to_email=str(user.email),
        subject=subject,
        html=body_html,
        text=body_text,
    )
    out: Path = settings.outbox_dir / f"email_{row.id}_{token[:8]}.html"
    header = (
        f"To: {user.email}\n"
        f"From: {settings.marketing_from_name} <{settings.marketing_from_email}>\n"
        f"Subject: {subject}\n"
        f"X-Delivery: {channel}\n"
        f"X-Provider-Id: {provider_id or '-'}\n\n"
    )
    out.write_text(header + body_html, encoding="utf-8")
    if channel != "outbox":
        row.status = f"sent_{channel}"
        db.commit()
    return row
