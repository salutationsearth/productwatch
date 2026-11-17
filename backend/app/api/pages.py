from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.app.api.auth import get_customer_id, is_manager
from backend.app.db import get_db
from backend.app.models import MarketingEmail, Product, User
from backend.app.services.analytics import dashboard_summary
from backend.app.services.interest import list_interests

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(request: Request, **extra):
    return {
        "customer_id": get_customer_id(request),
        "is_manager": is_manager(request),
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", _ctx(request, title="Home"))


@router.get("/rewards", response_class=HTMLResponse)
def rewards_signup(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "rewards.html", _ctx(request, title="Rewards Club"))


@router.get("/onboard", response_class=HTMLResponse)
def onboard_redirect() -> RedirectResponse:
    return RedirectResponse(url="/rewards", status_code=302)


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, db: Session = Depends(get_db)):
    cid = get_customer_id(request)
    if cid is None:
        return RedirectResponse(url="/account/login", status_code=302)
    user = db.get(User, cid)
    if not user:
        request.session.pop("customer_id", None)
        return RedirectResponse(url="/account/login", status_code=302)
    interests = list_interests(db, cid)
    return templates.TemplateResponse(
        request,
        "account.html",
        _ctx(request, title="My Account", user=user, interests=interests),
    )


@router.get("/account/login", response_class=HTMLResponse)
def account_login(request: Request):
    if get_customer_id(request) is not None:
        return RedirectResponse(url="/account", status_code=302)
    return templates.TemplateResponse(request, "account_login.html", _ctx(request, title="Sign in"))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_redirect() -> RedirectResponse:
    return RedirectResponse(url="/manager", status_code=302)


@router.get("/manager/login", response_class=HTMLResponse)
def manager_login_page(request: Request, error: int = 0):
    if is_manager(request):
        return RedirectResponse(url="/manager", status_code=302)
    return templates.TemplateResponse(
        request,
        "manager_login.html",
        _ctx(request, title="Manager Login", error=bool(error)),
    )


@router.get("/manager", response_class=HTMLResponse)
def manager_dashboard(request: Request, db: Session = Depends(get_db)):
    if not is_manager(request):
        return RedirectResponse(url="/manager/login", status_code=302)
    summary = dashboard_summary(db)
    emails = (
        db.query(MarketingEmail, Product, User)
        .join(Product, Product.id == MarketingEmail.product_id)
        .join(User, User.id == MarketingEmail.user_id)
        .order_by(MarketingEmail.sent_at.desc())
        .limit(50)
        .all()
    )
    email_rows = [
        {
            "id": email.id,
            "sent_at": email.sent_at,
            "subject": email.subject,
            "product_name": product.name,
            "to_email": user.email,
            "percent_off": email.percent_off,
            "status": email.status,
            "opened": email.opened_at is not None,
            "clicked": email.clicked_at is not None,
            "converted": email.converted_at is not None,
            "token": email.tracking_token,
        }
        for email, product, user in emails
    ]
    return templates.TemplateResponse(
        request,
        "manager.html",
        _ctx(request, title="Marketing Admin", summary=summary, emails=email_rows),
    )


@router.get("/offer/{token}", response_class=HTMLResponse)
def offer_page(
    token: str,
    request: Request,
    redeemed: int = 0,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    row = db.query(MarketingEmail).filter(MarketingEmail.tracking_token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Offer not found")
    product = db.get(Product, row.product_id)
    return templates.TemplateResponse(
        request,
        "offer.html",
        _ctx(
            request,
            title="Your offer",
            subject=row.subject,
            percent_off=row.percent_off,
            product_name=product.name if product else "Product",
            body_html=row.body_html,
            redeemed=bool(redeemed),
            token=token,
        ),
    )
