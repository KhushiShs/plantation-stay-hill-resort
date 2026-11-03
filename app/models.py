"""Database models for Plantation Stay."""
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Integer, BIGINT, Boolean, Date, DateTime, Text,
    ForeignKey, UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('reservations', 'gm', 'sales')", name="chk_user_role"),
    )


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    base_occupancy: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_occupancy: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    total_inventory: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    allotments: Mapped[List["Allotment"]] = relationship(back_populates="room_type", cascade="all, delete-orphan")
    daily_rates: Mapped[List["DailyRate"]] = relationship(back_populates="room_type", cascade="all, delete-orphan")


class RatePlan(Base):
    __tablename__ = "rate_plans"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    breakfast_addon_paise: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DailyRate(Base):
    __tablename__ = "daily_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_type_id: Mapped[str] = mapped_column(String(50), ForeignKey("room_types.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    price_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    room_type: Mapped["RoomType"] = relationship(back_populates="daily_rates")

    __table_args__ = (
        UniqueConstraint("room_type_id", "date", name="uq_daily_rate_room_date"),
        Index("idx_daily_rates_lookup", "room_type_id", "date"),
    )


class Allotment(Base):
    __tablename__ = "allotment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_type_id: Mapped[str] = mapped_column(String(50), ForeignKey("room_types.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    held: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blackout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    room_type: Mapped["RoomType"] = relationship(back_populates="allotments")

    __table_args__ = (
        UniqueConstraint("room_type_id", "date", name="uq_allotment_room_date"),
        CheckConstraint("sold >= 0 AND held >= 0 AND (sold + held) <= total", name="chk_allotment_capacity"),
        Index("idx_allotment_room_date", "room_type_id", "date"),
    )


class GSTSlab(Base):
    __tablename__ = "gst_slabs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_price_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    max_price_paise: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("rate_bps >= 0", name="chk_gst_rate_bps"),
    )


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    discount_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_flat_paise: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("discount_bps >= 0 AND discount_bps <= 10000", name="chk_promo_discount_bps"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    room_type_id: Mapped[str] = mapped_column(String(50), ForeignKey("room_types.id"), nullable=False)
    rate_plan_id: Mapped[str] = mapped_column(String(50), ForeignKey("rate_plans.id"), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    num_guests: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    num_rooms: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="held", nullable=False)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    guest_name: Mapped[str] = mapped_column(String(100), nullable=False)
    guest_email: Mapped[str] = mapped_column(String(255), nullable=False)
    guest_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    dpdp_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    room_total_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    gst_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    grand_total_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    promo_code: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("promo_codes.code"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    nights: Mapped[List["BookingNight"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    guests: Mapped[List["BookingGuest"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship(back_populates="booking", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("check_out > check_in", name="chk_booking_dates"),
        CheckConstraint("status IN ('held', 'confirmed', 'cancelled', 'expired')", name="chk_booking_status"),
        Index("idx_bookings_guest_ref", "guest_email", "reference"),
    )


class BookingNight(Base):
    __tablename__ = "booking_nights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    base_rate_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    breakfast_addon_paise: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    taxable_amount_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    gst_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    gst_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    total_night_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="nights")

    __table_args__ = (
        UniqueConstraint("booking_id", "date", name="uq_booking_night_date"),
    )


class BookingGuest(Base):
    __tablename__ = "booking_guests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="guests")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BIGINT, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="mock", nullable=False)
    signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    booking: Mapped["Booking"] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'success', 'failed', 'needs_refund')", name="chk_payment_status"),
    )


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="web_form", nullable=False)
    guest_name: Mapped[str] = mapped_column(String(100), nullable=False)
    guest_email: Mapped[str] = mapped_column(String(255), nullable=False)
    guest_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="unsorted", nullable=False)
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    classified_by_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_role: Mapped[str] = mapped_column(String(32), default="reservations", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EnquiryEvent(Base):
    __tablename__ = "enquiry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[str] = mapped_column(String(32), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_role: Mapped[str] = mapped_column(String(32), default="gm", nullable=False)
    enquiry_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("enquiries.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
