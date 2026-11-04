"""Seed database with baseline data according to AGENTS.md and requirements."""
import os
import sys
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import engine, Base, SessionLocal
from app.models import (
    User, RoomType, RatePlan, DailyRate, Allotment, GSTSlab, PromoCode
)
from app.security import hash_password

# Default demo passwords for local development only
DEFAULT_LOCAL_RESERVATIONS_PWD = "ReservationsDemo2026!"
DEFAULT_LOCAL_GM_PWD = "GMDemo2026!"
DEFAULT_LOCAL_SALES_PWD = "SalesDemo2026!"


def get_staff_seed_passwords() -> dict:
    """
    Resolve staff credentials safely based on APP_ENV:
    - In development (or test): fallback to local demo passwords if unset.
    - In production: DEMO_RESERVATIONS_PASSWORD, DEMO_GM_PASSWORD, and DEMO_SALES_PASSWORD
      MUST be explicitly configured and at least 12 characters long. Aborts with error if missing.
    """
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()

    res_pwd = os.getenv("DEMO_RESERVATIONS_PASSWORD")
    gm_pwd = os.getenv("DEMO_GM_PASSWORD")
    sales_pwd = os.getenv("DEMO_SALES_PASSWORD")

    if app_env == "production":
        missing_or_short = []
        if not res_pwd or len(res_pwd) < 12:
            missing_or_short.append("DEMO_RESERVATIONS_PASSWORD (missing or < 12 chars)")
        if not gm_pwd or len(gm_pwd) < 12:
            missing_or_short.append("DEMO_GM_PASSWORD (missing or < 12 chars)")
        if not sales_pwd or len(sales_pwd) < 12:
            missing_or_short.append("DEMO_SALES_PASSWORD (missing or < 12 chars)")

        if missing_or_short:
            raise ValueError(
                "Production database seeding aborted: The following staff password environment "
                f"variables are required and must be at least 12 characters: {', '.join(missing_or_short)}. "
                "Set DEMO_RESERVATIONS_PASSWORD, DEMO_GM_PASSWORD, and DEMO_SALES_PASSWORD before seeding production."
            )
    else:
        # Development fallback
        res_pwd = res_pwd or DEFAULT_LOCAL_RESERVATIONS_PWD
        gm_pwd = gm_pwd or DEFAULT_LOCAL_GM_PWD
        sales_pwd = sales_pwd or DEFAULT_LOCAL_SALES_PWD

    return {
        "reservations": res_pwd,
        "gm": gm_pwd,
        "sales": sales_pwd
    }


def seed_database(session: Session, start_date: date = None) -> None:
    """Populate database with room types, rates for 180 days, users, slabs, promos."""
    if start_date is None:
        start_date = date.today()

    passwords = get_staff_seed_passwords()

    # 1. Users (reservations, gm, sales)
    users_data = [
        ("reservations@plantationstay.local", passwords["reservations"], "Reservations Desk", "reservations"),
        ("gm@plantationstay.local", passwords["gm"], "General Manager", "gm"),
        ("sales@plantationstay.local", passwords["sales"], "Sales & Events Team", "sales"),
    ]
    for email, pwd, name, role in users_data:
        existing = session.scalar(select(User).where(User.email == email))
        if not existing:
            u = User(
                email=email,
                hashed_password=hash_password(pwd),
                full_name=name,
                role=role,
                is_active=True
            )
            session.add(u)

    # 2. Room Types (64 rooms + 12 villas = 76 keys)
    # Estate Room Rs 7,000 weekday / Rs 9,000 weekend (base 700000 paise)
    # Villa Rs 16,000 weekday / Rs 20,000 weekend (base 1600000 paise)
    room_types_data = [
        RoomType(
            id="estate-room",
            name="Estate Room",
            description="Spacious heritage room overlooking coffee plantations with private sit-out and ensuite bath.",
            base_occupancy=2,
            max_occupancy=3,
            total_inventory=64,
            base_price_paise=700000,
            image_url="/static/img/estate-room-1200.webp"
        ),
        RoomType(
            id="luxury-villa",
            name="Luxury Plantation Villa",
            description="Private luxury villa amidst lush coffee trees, featuring private plunge pool and estate views.",
            base_occupancy=2,
            max_occupancy=4,
            total_inventory=12,
            base_price_paise=1600000,
            image_url="/static/img/luxury-villa-1200.webp"
        )
    ]
    for rt in room_types_data:
        existing_rt = session.get(RoomType, rt.id)
        if not existing_rt:
            session.add(rt)
        else:
            existing_rt.image_url = rt.image_url
    session.flush()

    # 3. Rate Plans
    rate_plans_data = [
        RatePlan(
            id="room_only",
            name="Room Only",
            description="Room accommodation only. Meals and extras charged separately.",
            breakfast_addon_paise=0,
            is_active=True
        ),
        RatePlan(
            id="room_breakfast",
            name="Room + Breakfast",
            description="Includes lavish gourmet buffet breakfast at the plantation restaurant.",
            breakfast_addon_paise=75000,  # Rs 750 / person / night
            is_active=True
        )
    ]
    for rp in rate_plans_data:
        if not session.get(RatePlan, rp.id):
            session.add(rp)
    session.flush()

    # 4. GST Slabs (integer basis points: 5% = 500 bps, 18% = 1800 bps)
    if not session.scalars(select(GSTSlab)).first():
        session.add(GSTSlab(min_price_paise=0, max_price_paise=750000, rate_bps=500))
        session.add(GSTSlab(min_price_paise=750001, max_price_paise=None, rate_bps=1800))
        session.flush()

    # 5. Promo Code (WELCOME10 -> 10% = 1000 bps)
    if not session.get(PromoCode, "WELCOME10"):
        promo = PromoCode(
            code="WELCOME10",
            discount_bps=1000,
            discount_flat_paise=0,
            valid_from=start_date,
            valid_to=start_date + timedelta(days=365),
            is_active=True
        )
        session.add(promo)
        session.flush()

    # 6. 180 Days Rates & Allotments
    # Estate Room: Rs 7,000 weekday / Rs 9,000 weekend (Friday, Saturday nights)
    # Luxury Villa: Rs 16,000 weekday / Rs 20,000 weekend
    # Website Allotment:
    # Estate room: 25 keys website allotment
    # Villa: 5 keys website allotment
    # Special brief requirement: Leave exactly 1 villa available on 14-16 Nov 2026!
    # (If 5 total website allotment, 4 are sold on 14-16 Nov 2026, leaving exactly 1 available).
    target_nov_14 = date(2026, 11, 14)
    target_nov_15 = date(2026, 11, 15)

    for i in range(180):
        current_d = start_date + timedelta(days=i)
        is_weekend = current_d.weekday() in (4, 5)  # Friday, Saturday

        # Daily Rates
        estate_price = 900000 if is_weekend else 700000
        villa_price = 2000000 if is_weekend else 1600000

        # Upsert Daily Rates
        dr_estate = session.scalar(
            select(DailyRate).where(DailyRate.room_type_id == "estate-room", DailyRate.date == current_d)
        )
        if not dr_estate:
            session.add(DailyRate(room_type_id="estate-room", date=current_d, price_paise=estate_price))

        dr_villa = session.scalar(
            select(DailyRate).where(DailyRate.room_type_id == "luxury-villa", DailyRate.date == current_d)
        )
        if not dr_villa:
            session.add(DailyRate(room_type_id="luxury-villa", date=current_d, price_paise=villa_price))

        # Allotments
        # Estate: total 25
        alt_estate = session.scalar(
            select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == current_d)
        )
        if not alt_estate:
            session.add(Allotment(
                room_type_id="estate-room",
                date=current_d,
                total=25,
                sold=0,
                held=0,
                blackout=False
            ))

        # Villa: total 5
        alt_villa = session.scalar(
            select(Allotment).where(Allotment.room_type_id == "luxury-villa", Allotment.date == current_d)
        )
        # Check special condition: on 14-16 Nov 2026 (nights of Nov 14 and Nov 15), exactly 1 villa available:
        sold_villa = 4 if current_d in (target_nov_14, target_nov_15) else 0

        if not alt_villa:
            session.add(Allotment(
                room_type_id="luxury-villa",
                date=current_d,
                total=5,
                sold=sold_villa,
                held=0,
                blackout=False
            ))
        elif current_d in (target_nov_14, target_nov_15):
            alt_villa.sold = 4

    # 7. Seed enquiries offline from data/enquiries_seed.json
    from app.services.enquiry_service import seed_enquiries_offline
    seed_enquiries_offline(session)

    session.commit()


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)
        print("Database seeded successfully!")


if __name__ == "__main__":
    main()
