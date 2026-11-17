"""Simple session auth for customers + manager."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import get_db
from backend.app.models import User
from backend.app.schemas import UserOut

router = APIRouter(tags=["auth"])


def get_customer_id(request: Request) -> int | None:
    raw = request.session.get("customer_id")
    return int(raw) if raw is not None else None


def require_customer(request: Request) -> int:
    cid = get_customer_id(request)
    if cid is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return cid


def is_manager(request: Request) -> bool:
    return bool(request.session.get("is_manager"))


@router.post("/auth/customer/login", response_model=UserOut)
def customer_login(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
) -> User:
    cleaned = email.strip()
    user = db.query(User).filter(User.email == cleaned).first()
    if not user:
        user = db.query(User).filter(User.email == cleaned.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="No rewards account for that email")
    request.session["customer_id"] = user.id
    request.session.pop("is_manager", None)
    return user


@router.post("/auth/customer/session/{user_id}", response_model=UserOut)
def customer_session(user_id: int, request: Request, db: Session = Depends(get_db)) -> User:
    """Establish customer session after signup / face enroll."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    request.session["customer_id"] = user.id
    request.session.pop("is_manager", None)
    return user


@router.post("/auth/customer/logout")
def customer_logout(request: Request) -> RedirectResponse:
    request.session.pop("customer_id", None)
    return RedirectResponse(url="/", status_code=303)


@router.post("/auth/manager/login")
def manager_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    if username == settings.manager_username and password == settings.manager_password:
        request.session["is_manager"] = True
        request.session.pop("customer_id", None)
        return RedirectResponse(url="/manager", status_code=303)
    return RedirectResponse(url="/manager/login?error=1", status_code=303)


@router.post("/auth/manager/logout")
def manager_logout(request: Request) -> RedirectResponse:
    request.session.pop("is_manager", None)
    return RedirectResponse(url="/manager/login", status_code=303)
