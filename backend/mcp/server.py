"""
WatcherMart Marketing MCP server (stdio).

Exposes tools so an OpenAI agent can:
  - read customer aisle-interest data
  - create tracked discount links
  - report emails it sent (manager dashboard)
  - check conversion on those links

Run from repo root:
  python -m backend.mcp.server
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python -m backend.mcp.server` from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer

from backend.app.db import SessionLocal, init_db
from backend.app.services import marketing_ops

mcp = MCPServer(
    "watchermart-marketing",
    instructions=(
        "MCP tools for the WatcherMart supermarket marketing agent. "
        "Use list_customer_interests to find who to email, create_discount_link to get a "
        "tracked claim URL, send the email yourself, then report_email_sent so the store "
        "manager dashboard updates."
    ),
)


def _db():
    init_db()
    return SessionLocal()


@mcp.tool()
def list_customer_interests(min_weight: float = 0.0, limit: int = 50) -> str:
    """
    List rewards members with aisle product interest.

    Returns JSON: customer identity + product + interest weight + timestamps
    so you can decide whether/when to send a marketing email.
    """
    db = _db()
    try:
        rows = marketing_ops.list_customer_interests(
            db, min_weight=min_weight, limit=limit, face_enrolled_only=True
        )
        return json.dumps({"count": len(rows), "interests": rows}, indent=2)
    finally:
        db.close()


@mcp.tool()
def create_discount_link(user_id: int, product_id: int, percent_off: float = 15.0) -> str:
    """
    Create a tracked discount offer for a customer + product.

    Returns claim_url, convert_url, open_pixel_url, and token.
    Include claim_url (and optionally the open pixel) in the email you send.
    Clicks and redemptions are tracked automatically for conversion analytics.
    """
    db = _db()
    try:
        result = marketing_ops.create_discount_link(
            db, user_id=user_id, product_id=product_id, percent_off=percent_off
        )
        return json.dumps(result, indent=2)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


@mcp.tool()
def report_email_sent(
    token: str,
    subject: str,
    body_text: str,
    body_html: str = "",
    rationale: str = "",
) -> str:
    """
    Report that you sent a marketing email for a discount link token.

    Call this AFTER you send the email. This writes the message to the
    WatcherMart manager dashboard and local outbox.
    """
    db = _db()
    try:
        result = marketing_ops.report_email_sent(
            db,
            token=token,
            subject=subject,
            body_text=body_text,
            body_html=body_html or None,
            rationale=rationale or None,
        )
        return json.dumps(result, indent=2)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


@mcp.tool()
def list_sent_emails(limit: int = 30) -> str:
    """List recent marketing emails already reported (for your own memory / deduping)."""
    db = _db()
    try:
        rows = marketing_ops.list_sent_emails(db, limit=limit)
        return json.dumps({"count": len(rows), "emails": rows}, indent=2)
    finally:
        db.close()


@mcp.tool()
def get_link_conversion(token: str) -> str:
    """Get open / click / conversion status for a discount link token."""
    db = _db()
    try:
        result = marketing_ops.get_link_conversion(db, token)
        return json.dumps(result, indent=2)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


def main() -> None:
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
