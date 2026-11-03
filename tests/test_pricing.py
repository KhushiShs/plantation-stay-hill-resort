"""Tests for pricing calculation, GST slabs, promo codes, and integer rounding."""
import pytest
from datetime import date, timedelta
from app.services.pricing import calculate_pricing, get_gst_rate_bps_for_tariff
from app.models import RoomType, RatePlan, DailyRate, GSTSlab, PromoCode


def test_gst_slab_boundary(db_session):
    """
    Test GST slab threshold:
    Tariff <= 750,000 paise (Rs 7,500) -> 5% (500 bps)
    Tariff > 750,000 paise -> 18% (1800 bps)
    """
    # Boundary: Rs 7,499.00 = 749900 paise -> 500 bps
    assert get_gst_rate_bps_for_tariff(db_session, 749900) == 500

    # Boundary: Exact Rs 7,500.00 = 750000 paise -> 500 bps
    assert get_gst_rate_bps_for_tariff(db_session, 750000) == 500

    # Boundary: Rs 7,500.01 = 750001 paise -> 1800 bps
    assert get_gst_rate_bps_for_tariff(db_session, 750001) == 1800

    # Higher rate: Rs 16,000.00 = 1600000 paise -> 1800 bps
    assert get_gst_rate_bps_for_tariff(db_session, 1600000) == 1800


def test_estate_room_weekday_pricing_room_only(db_session):
    """
    Estate Room weekday rate: Rs 7,000/night (700,000 paise)
    Under 7,500 -> 5% GST (35,000 paise)
    Total per night = 735,000 paise (Rs 7,350)
    """
    # Pick a weekday
    stay = [date(2026, 11, 9)]  # Monday
    res = calculate_pricing(
        db_session,
        room_type_id="estate-room",
        rate_plan_id="room_only",
        stay_dates=stay,
        num_guests=2
    )

    night = res.nights[0]
    assert night.base_rate_paise == 700000
    assert night.breakfast_addon_paise == 0
    assert night.discount_paise == 0
    assert night.gst_bps == 500
    assert night.gst_paise == 35000
    assert night.total_night_paise == 735000
    assert res.grand_total_paise == 735000


def test_estate_room_weekend_pricing_crosses_slab(db_session):
    """
    Estate Room weekend rate: Rs 9,000/night (900,000 paise)
    Over 7,500 -> 18% GST (162,000 paise)
    Total per night = 1,062,000 paise (Rs 10,620)
    """
    stay = [date(2026, 11, 13)]  # Friday (weekend)
    res = calculate_pricing(
        db_session,
        room_type_id="estate-room",
        rate_plan_id="room_only",
        stay_dates=stay,
        num_guests=2
    )

    night = res.nights[0]
    assert night.base_rate_paise == 900000
    assert night.gst_bps == 1800
    assert night.gst_paise == 162000
    assert night.total_night_paise == 1062000


def test_stay_crossing_weekday_and_weekend(db_session):
    """
    Stay crossing slab boundaries: Thursday (Rs 7,000, 5% GST) + Friday (Rs 9,000, 18% GST).
    Verifies that GST slabs are chosen per-night based on each day's declared tariff.
    """
    stay = [date(2026, 11, 12), date(2026, 11, 13)]  # Thu, Fri
    res = calculate_pricing(
        db_session,
        room_type_id="estate-room",
        rate_plan_id="room_only",
        stay_dates=stay,
        num_guests=2
    )

    assert len(res.nights) == 2
    # Night 1: 700,000 + 35,000 = 735,000
    assert res.nights[0].gst_bps == 500
    assert res.nights[0].gst_paise == 35000
    assert res.nights[0].total_night_paise == 735000

    # Night 2: 900,000 + 162,000 = 1,062,000
    assert res.nights[1].gst_bps == 1800
    assert res.nights[1].gst_paise == 162000
    assert res.nights[1].total_night_paise == 1062000

    # Grand total: 735,000 + 1,062,000 = 1,797,000 paise
    assert res.grand_total_paise == 1797000
    assert res.gst_paise == 197000


def test_breakfast_addon_calculation(db_session):
    """
    Breakfast add-on is Rs 750/person/night = 75,000 paise.
    2 adults -> 150,000 paise breakfast add-on per night.
    GST slab is chosen on room tariff (700,000 paise -> 5% slab).
    GST applies to (room + breakfast) = 700,000 + 150,000 = 850,000.
    5% of 850,000 = 42,500 paise.
    Total = 892,500 paise.
    """
    stay = [date(2026, 11, 9)]
    res = calculate_pricing(
        db_session,
        room_type_id="estate-room",
        rate_plan_id="room_breakfast",
        stay_dates=stay,
        num_guests=2
    )

    night = res.nights[0]
    assert night.base_rate_paise == 700000
    assert night.breakfast_addon_paise == 150000
    assert night.gst_bps == 500
    assert night.gst_paise == 42500
    assert night.total_night_paise == 892500
    assert res.grand_total_paise == 892500


def test_promo_code_and_rounding(db_session):
    """
    Promo code WELCOME10 gives 10% (1,000 bps) discount.
    Estate room weekday = 700,000 paise.
    10% discount = 70,000 paise.
    Discounted room = 630,000 paise.
    Breakfast for 1 guest = 75,000 paise.
    Taxable amount = 630,000 + 75,000 = 705,000 paise.
    GST slab chosen on declared room tariff (700,000 <= 750,000 -> 5%).
    5% GST on 705,000 = 35,250 paise.
    Total = 705,000 + 35,250 = 740,250 paise.
    """
    stay = [date(2026, 11, 9)]
    res = calculate_pricing(
        db_session,
        room_type_id="estate-room",
        rate_plan_id="room_breakfast",
        stay_dates=stay,
        num_guests=1,
        promo_code_str="WELCOME10"
    )

    night = res.nights[0]
    assert night.base_rate_paise == 700000
    assert night.discount_paise == 70000
    assert night.breakfast_addon_paise == 75000
    assert night.taxable_amount_paise == 705000
    assert night.gst_bps == 500
    assert night.gst_paise == 35250
    assert night.total_night_paise == 740250
    assert res.grand_total_paise == 740250
    assert res.discount_paise == 70000
