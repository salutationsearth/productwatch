from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import MarketingEmail, Product

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "onboard.html", {"title": "Join Rewards"})


@router.get("/onboard", response_class=HTMLResponse)
def onboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "onboard.html", {"title": "Join Rewards"})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"title": "Marketing Dashboard"},
    )


@router.get("/offer/{token}", response_class=HTMLResponse)
def offer_page(token: str, request: Request, redeemed: int = 0, db: Session = Depends(get_db)) -> HTMLResponse:
    row = db.query(MarketingEmail).filter(MarketingEmail.tracking_token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Offer not found")
    product = db.get(Product, row.product_id)
    return templates.TemplateResponse(
        request,
        "offer.html",
        {
            "title": "Your offer",
            "subject": row.subject,
            "percent_off": row.percent_off,
            "product_name": product.name if product else "Product",
            "body_html": row.body_html,
            "redeemed": bool(redeemed),
            "token": token,
        },
    )
