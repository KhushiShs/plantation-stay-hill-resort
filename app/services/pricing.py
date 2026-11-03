"""Pricing and tax calculation service using integer basis points."""
import math
from datetime import date
from typing import List, Dict, Any, Optional
from collections import defaultdict
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import RoomType, RatePlan, DailyRate, GSTSlab, PromoCode


def round_half_up(n: float) -> int:
    """Standard commercial round-half-up to nearest integer."""
    return int(math.floor(n + 0.5))


@dataclass
class NightlyBreakdown:
    date: date
    base_rate_paise: int
    breakfast_addon_paise: int
    discount_paise: int
    taxable_amount_paise: int
    gst_bps: int
    gst_paise: int
    total_night_paise: int


@dataclass
class GSTSlabSummary:
    rate_bps: int
    percent: float
    nights_count: int
    taxable_amount_paise: int
    gst_paise: int
    label: str


@dataclass
class BookingPriceBreakdown:
    nights: List[NightlyBreakdown]
    gst_summaries: List[GSTSlabSummary]
    gst_text: str
    room_total_paise: int
    discount_paise: int
    gst_paise: int
    grand_total_paise: int
    promo_code: Optional[str] = None


def get_gst_rate_bps_for_tariff(session: Session, declared_tariff_paise: int) -> int:
    """
    Find GST rate in basis points based on declared room tariff per night (before promo and breakfast).
    Tariff <= 750000 paise -> 5% (500 bps), above -> 18% (1800 bps).
    """
    slabs = session.scalars(select(GSTSlab).order_by(GSTSlab.min_price_paise.asc())).all()
    for slab in slabs:
        if slab.max_price_paise is None:
            if declared_tariff_paise >= slab.min_price_paise:
                return slab.rate_bps
        else:
            if slab.min_price_paise <= declared_tariff_paise <= slab.max_price_paise:
                return slab.rate_bps
    # Fallback to assumption default if table is unseeded
    return 500 if declared_tariff_paise <= 750000 else 1800


def calculate_pricing(
    session: Session,
    room_type_id: str,
    rate_plan_id: str,
    stay_dates: List[date],
    num_guests: int = 1,
    promo_code_str: Optional[str] = None
) -> BookingPriceBreakdown:
    """
    Calculate nightly pricing breakdown and totals.
    - Money is in integer paise throughout.
    - GST slab is determined on declared room tariff per night (before promo and breakfast).
    - Promo discount applies to the base room tariff.
    - GST applies to the discounted room tariff plus breakfast add-on.
    - Per night, round half up to the paisa, then sum.
    - GST summary aggregates by chosen slab, dynamically constructing clear invoice text.
    """
    if not stay_dates:
        raise ValueError("Stay dates cannot be empty")

    rate_plan = session.get(RatePlan, rate_plan_id)
    if not rate_plan:
        raise ValueError(f"Invalid rate plan: {rate_plan_id}")

    # Fetch daily rates
    daily_rates_map: Dict[date, int] = {}
    db_rates = session.scalars(
        select(DailyRate).where(
            DailyRate.room_type_id == room_type_id,
            DailyRate.date.in_(stay_dates)
        )
    ).all()
    for r in db_rates:
        daily_rates_map[r.date] = r.price_paise

    room_type = session.get(RoomType, room_type_id)
    if not room_type:
        raise ValueError(f"Invalid room type: {room_type_id}")

    # Validate promo code
    promo: Optional[PromoCode] = None
    if promo_code_str:
        promo = session.get(PromoCode, promo_code_str)
        if not promo or not promo.is_active:
            promo = None

    nightly_items: List[NightlyBreakdown] = []
    num_nights = len(stay_dates)
    slab_nights = defaultdict(list)

    for d in stay_dates:
        declared_tariff = daily_rates_map.get(d, room_type.base_price_paise)
        breakfast_addon = rate_plan.breakfast_addon_paise * num_guests

        # Promo discount per night
        discount = 0
        if promo:
            if promo.discount_bps > 0:
                discount += round_half_up(declared_tariff * (promo.discount_bps / 10000.0))
            if promo.discount_flat_paise > 0:
                discount += round_half_up(promo.discount_flat_paise / float(num_nights))

        discount = min(discount, declared_tariff)
        discounted_room = declared_tariff - discount
        taxable_amount = discounted_room + breakfast_addon

        # GST slab chosen on declared tariff
        gst_bps = get_gst_rate_bps_for_tariff(session, declared_tariff)
        gst_paise = round_half_up(taxable_amount * (gst_bps / 10000.0))
        total_night = taxable_amount + gst_paise

        item = NightlyBreakdown(
            date=d,
            base_rate_paise=declared_tariff,
            breakfast_addon_paise=breakfast_addon,
            discount_paise=discount,
            taxable_amount_paise=taxable_amount,
            gst_bps=gst_bps,
            gst_paise=gst_paise,
            total_night_paise=total_night
        )
        nightly_items.append(item)
        slab_nights[gst_bps].append(item)

    # Build GST slab summary
    gst_summaries: List[GSTSlabSummary] = []
    label_parts = []
    for bps in sorted(slab_nights.keys()):
        items = slab_nights[bps]
        count = len(items)
        taxable = sum(i.taxable_amount_paise for i in items)
        gst_amt = sum(i.gst_paise for i in items)
        pct = bps / 100.0
        pct_str = f"{int(pct)}%" if pct.is_integer() else f"{pct:.1f}%"
        night_word = "night" if count == 1 else "nights"
        label = f"GST {pct_str} x {count} {night_word}"
        label_parts.append(label)
        gst_summaries.append(GSTSlabSummary(
            rate_bps=bps,
            percent=pct,
            nights_count=count,
            taxable_amount_paise=taxable,
            gst_paise=gst_amt,
            label=label
        ))

    gst_text = ", ".join(label_parts) if label_parts else "GST"

    # Sum totals
    room_total_paise = sum(n.base_rate_paise + n.breakfast_addon_paise for n in nightly_items)
    discount_paise = sum(n.discount_paise for n in nightly_items)
    gst_paise = sum(n.gst_paise for n in nightly_items)
    grand_total_paise = sum(n.total_night_paise for n in nightly_items)

    return BookingPriceBreakdown(
        nights=nightly_items,
        gst_summaries=gst_summaries,
        gst_text=gst_text,
        room_total_paise=room_total_paise,
        discount_paise=discount_paise,
        gst_paise=gst_paise,
        grand_total_paise=grand_total_paise,
        promo_code=promo.code if promo else None
    )
