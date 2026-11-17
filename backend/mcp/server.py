"""
WatcherMart Marketing MCP server.

Transports:
  stdio            — local clients
  streamable-http  — public VPS (OpenAI remote MCP)

Production:
  https://mcp.productwatch.jacob-yu.com/mcp
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.app.config import settings
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


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/healthz"}:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {self.token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _transport_security() -> TransportSecuritySettings:
    hosts = [h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()]
    origins = [o.strip() for o in settings.mcp_allowed_origins.split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


async def _health(_request: Request):
    return JSONResponse(
        {
            "status": "ok",
            "service": "watchermart-mcp",
            "endpoint": settings.mcp_path,
        }
    )


def run_http() -> None:
    """Serve streamable HTTP MCP behind nginx at mcp.productwatch.jacob-yu.com."""
    # Build app with explicit path + DNS rebinding allowlist for the public host.
    app = mcp.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        transport_security=_transport_security(),
        stateless_http=settings.mcp_stateless_http,
    )
    app.router.routes.insert(0, Route("/health", _health))
    if settings.mcp_auth_token:
        app.add_middleware(BearerAuthMiddleware, token=settings.mcp_auth_token)
        print("MCP bearer auth: enabled", flush=True)
    else:
        print("MCP bearer auth: DISABLED (set PW_MCP_AUTH_TOKEN for production)", flush=True)

    print(
        f"MCP listening on http://{settings.mcp_host}:{settings.mcp_port}{settings.mcp_path}",
        flush=True,
    )
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port, log_level="info")


def main() -> None:
    init_db()
    transport = (settings.mcp_transport or "stdio").lower().strip()

    if transport in {"streamable-http", "http"}:
        run_http()
        return

    if transport == "sse":
        mcp.run(
            transport="sse",
            host=settings.mcp_host,
            port=settings.mcp_port,
            transport_security=_transport_security(),
        )
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
