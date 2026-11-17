from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import MarketingEmail
from backend.app.schemas import AgentStatus, DashboardSummary
from backend.app.services.analytics import dashboard_summary

router = APIRouter(tags=["analytics"])


@router.get("/analytics/dashboard", response_model=DashboardSummary)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardSummary:
    """Anonymous product interest + email funnel metrics (no customer identities)."""
    return dashboard_summary(db)


@router.get("/agent/status", response_model=AgentStatus)
def get_agent_status(db: Session = Depends(get_db)) -> AgentStatus:
    """Status stub — marketing decisions run on the external OpenAI agent via MCP."""
    total = db.query(MarketingEmail).filter(MarketingEmail.status.like("sent%")).count()
    return AgentStatus(
        enabled=False,
        poll_seconds=0.0,
        last_run_at=None,
        last_summary="Marketing agent runs externally via MCP (OpenAI). Use report_email_sent to update the dashboard.",
        emails_sent_total=total,
    )
