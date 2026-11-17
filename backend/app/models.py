from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


class DiscountScope(str, Enum):
    MEMBER_GENERAL = "member_general"
    PERSONALIZED = "personalized"
    COMPETITOR = "competitor"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_rewards_member: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    face_enrolled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    face_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_marketing_email_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    embeddings: Mapped[list[FaceEmbedding]] = relationship(back_populates="user", cascade="all, delete-orphan")
    interests: Mapped[list[UserProductInterest]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    offers: Mapped[list[UserOffer]] = relationship(back_populates="user", cascade="all, delete-orphan")
    interest_events: Mapped[list[InterestEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    marketing_emails: Mapped[list[MarketingEmail]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of floats
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="embeddings")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    competitor_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    zones: Mapped[list[ProductZone]] = relationship(back_populates="product", cascade="all, delete-orphan")
    interests: Mapped[list[UserProductInterest]] = relationship(back_populates="product")
    discounts: Mapped[list[Discount]] = relationship(back_populates="product")
    offers: Mapped[list[UserOffer]] = relationship(back_populates="product")
    marketing_emails: Mapped[list[MarketingEmail]] = relationship(back_populates="product")


class ProductZone(Base):
    __tablename__ = "product_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="webcam-0")
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    product: Mapped[Product] = relationship(back_populates="zones")


class InterestEvent(Base):
    __tablename__ = "interest_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dwell_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    gaze_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    gaze_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user: Mapped[User] = relationship(back_populates="interest_events")
    product: Mapped[Product] = relationship()


class UserProductInterest(Base):
    __tablename__ = "user_product_interest"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="interests")
    product: Mapped[Product] = relationship(back_populates="interests")


class Discount(Base):
    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    percent_off: Mapped[float] = mapped_column(Float, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)  # DiscountScope value
    min_interest_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    product: Mapped[Product] = relationship(back_populates="discounts")


class UserOffer(Base):
    __tablename__ = "user_offers"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", "scope", name="uq_user_offer_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    percent_off: Mapped[float] = mapped_column(Float, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="offers")
    product: Mapped[Product] = relationship(back_populates="offers")


class MarketingEmail(Base):
    """Outbound marketing message. Dashboard aggregates only — never expose user↔product in UI."""

    __tablename__ = "marketing_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("user_offers.id", ondelete="SET NULL"), nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    percent_off: Mapped[float] = mapped_column(Float, nullable=False)
    agent_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    interest_weight_at_send: Mapped[float] = mapped_column(Float, nullable=False)
    interest_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hours_since_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="marketing_emails")
    product: Mapped[Product] = relationship(back_populates="marketing_emails")


class AgentRunLog(Base):
    __tablename__ = "agent_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    candidates_reviewed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emails_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
