"""Database models for Plantation Stay."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    String, Integer, BIGINT, Boolean, Date, DateTime, Text, Numeric,
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
        CheckConstraint("status IN ('pending', 'success', 'failed', 'needs_refund', 'refunded')", name="chk_payment_status"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_role: Mapped[str] = mapped_column(String(32), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[Optional["User"]] = relationship()


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # ENQ-xxxx
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # web_form, email_sim, whatsapp_sim
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sender_contact: Mapped[str] = mapped_column(String(120), nullable=False)  # fake email or phone
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # room, wedding, offsite, complaint, unsorted
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 0.000 to 1.000
    extracted_check_in: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    extracted_check_out: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    extracted_guests: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extracted_budget: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str] = mapped_column(String(20), nullable=False)  # reservations, sales, gm
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)  # new, drafted, sent, closed
    classified_by: Mapped[str] = mapped_column(String(10), nullable=False)  # ai, fallback
    draft_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    code_inserted_prices: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of allowed price strings
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    first_replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[List["EnquiryEvent"]] = relationship(back_populates="enquiry", cascade="all, delete-orphan", order_by="EnquiryEvent.created_at.asc()")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="enquiry", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("channel IN ('web_form', 'email_sim', 'whatsapp_sim')", name="chk_enquiry_channel"),
        CheckConstraint("category IN ('room', 'wedding', 'offsite', 'complaint', 'unsorted')", name="chk_enquiry_category"),
        CheckConstraint("owner_role IN ('reservations', 'sales', 'gm')", name="chk_enquiry_owner_role"),
        CheckConstraint("status IN ('new', 'drafted', 'sent', 'closed')", name="chk_enquiry_status"),
        CheckConstraint("classified_by IN ('ai', 'fallback')", name="chk_enquiry_classified_by"),
        Index("ix_enquiries_status_owner", "status", "owner_role"),
        Index("ix_enquiries_category", "category"),
        Index("ix_enquiries_created_at", "created_at"),
    )


class EnquiryEvent(Base):
    __tablename__ = "enquiry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[str] = mapped_column(String(16), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # classified, rerouted, draft_saved, reply_sent, closed
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    from_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    enquiry: Mapped["Enquiry"] = relationship(back_populates="events")
    actor: Mapped[Optional["User"]] = relationship()

    __table_args__ = (
        CheckConstraint("event_type IN ('classified', 'rerouted', 'draft_saved', 'reply_sent', 'closed')", name="chk_enquiry_event_type"),
        Index("ix_enquiry_events_enquiry_created", "enquiry_id", "created_at"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enquiry_id: Mapped[Optional[str]] = mapped_column(String(16), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=True)
    target_role: Mapped[str] = mapped_column(String(20), default="gm", nullable=False)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)  # complaint_received, response_overdue
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    enquiry: Mapped[Optional["Enquiry"]] = relationship(back_populates="alerts")

    __table_args__ = (
        CheckConstraint("target_role IN ('gm', 'reservations', 'sales')", name="chk_alert_target_role"),
        CheckConstraint("alert_type IN ('complaint_received', 'response_overdue')", name="chk_alert_type"),
        Index("ix_alerts_target_is_read", "target_role", "is_read", "created_at"),
    )
