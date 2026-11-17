from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import get_db
from backend.app.models import MarketingEmail
from backend.app.schemas import AgentStatus, DashboardSummary
from backend.app.services.analytics import dashboard_summary
from backend.app.services.marketing_agent import agent_state, run_agent_once

router = APIRouter(tags=["analytics"])


@router.get("/analytics/dashboard", response_model=DashboardSummary)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardSummary:
    """Anonymous product interest + email funnel metrics (no customer identities)."""
    return dashboard_summary(db)


@router.get("/agent/status", response_model=AgentStatus)
def get_agent_status(db: Session = Depends(get_db)) -> AgentStatus:
    total = db.query(MarketingEmail).count()
    return AgentStatus(
        enabled=agent_state.enabled and settings.agent_enabled,
        poll_seconds=settings.agent_poll_seconds,
        last_run_at=agent_state.last_run_at,
        last_summary=agent_state.last_summary,
        emails_sent_total=total,
    )


@router.post("/agent/run-once")
def trigger_agent(db: Session = Depends(get_db)) -> dict:
    log = run_agent_once(db)
    return {
        "candidates_reviewed": log.candidates_reviewed,
        "emails_sent": log.emails_sent,
        "summary": log.summary,
    }
