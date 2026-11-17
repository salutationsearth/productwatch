from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    is_rewards_member: bool = True


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    is_rewards_member: bool
    enrolled_at: datetime


class ProductCreate(BaseModel):
    sku: str
    name: str
    brand: str
    category: str
    price: float
    competitor_group: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    brand: str
    category: str
    price: float
    competitor_group: str | None


class ZoneIn(BaseModel):
    product_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    label: str | None = None


class ZonesReplace(BaseModel):
    zones: list[ZoneIn]


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    camera_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    label: str | None


class InterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    weight: float
    updated_at: datetime
    product_name: str | None = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    percent_off: float
    scope: str
    reason: str
    active: bool
    product_name: str | None = None


class EnrollFaceResponse(BaseModel):
    user_id: int
    samples_captured: int
    embedding_dim: int
    message: str


class AisleSessionRequest(BaseModel):
    camera_id: str = "webcam-0"
    max_seconds: float | None = 60.0
    force_user_id: int | None = None


class AisleSessionResult(BaseModel):
    matched_user_id: int | None
    events_recorded: int
    interest_updates: list[InterestOut]
    offers: list[OfferOut]
