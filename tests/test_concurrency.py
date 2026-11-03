"""Concurrency and race condition tests against real PostgreSQL database.

Includes:
1. Barrier-synchronized 20-thread concurrency test on last unit (total=1):
   - Exactly 1 succeeds, 19 fail with SoldOutException
   - Database constraint check: sold + held <= total
2. Total=3 variant:
   - Exactly 3 threads succeed, 17 fail
3. Overlapping multi-night variant:
   - Multiple threads contending across overlapping date ranges
   - Date-order updates prevent deadlocks
   - sold + held never exceeds total
"""
import pytest
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select, text
from app.models import Allotment
from app.services.allotment import create_atomic_hold, SoldOutException


def test_concurrency_20_threads_last_unit(session_factory):
    """
    20 threads with individual database sessions simultaneously contend for 1 remaining room.
    Synchronized via threading.Barrier for maximum simultaneous contention.
    Asserts:
    - Exactly 1 thread succeeds in acquiring hold
    - Exactly 19 threads receive SoldOutException ('just sold out')
    - Database state verifies held == 1, sold == 0, total == 1
    """
    target_date = date(2026, 12, 20)
    room_type = "estate-room"

    # Setup 1 remaining room
    with session_factory() as setup_session:
        alt = setup_session.scalar(
            select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == target_date)
        )
        if not alt:
            alt = Allotment(room_type_id=room_type, date=target_date, total=1, sold=0, held=0)
            setup_session.add(alt)
        else:
            alt.total = 1
            alt.sold = 0
            alt.held = 0
        setup_session.commit()

    num_threads = 20
    barrier = Barrier(num_threads)
    results = []

    def attempt_hold(thread_id):
        # Each thread gets its own isolated session and connection
        with session_factory() as session:
            barrier.wait()  # Synchronize launch across all 20 threads
            try:
                create_atomic_hold(session, room_type, [target_date], num_rooms=1)
                session.commit()
                return ("success", thread_id)
            except SoldOutException:
                session.rollback()
                return ("sold_out", thread_id)
            except Exception as e:
                session.rollback()
                return ("error", str(e))

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_hold, i) for i in range(num_threads)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == "success"]
    sold_outs = [r for r in results if r[0] == "sold_out"]
    errors = [r for r in results if r[0] == "error"]

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(sold_outs) == 19, f"Expected 19 sold out, got {len(sold_outs)}"

    # Check database state
    with session_factory() as verify_session:
        alt = verify_session.scalar(
            select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == target_date)
        )
        assert alt.held == 1
        assert alt.sold == 0
        assert alt.total == 1
        assert alt.sold + alt.held <= alt.total


def test_concurrency_total_3_variant(session_factory):
    """
    Total=3 variant: 20 threads contend for 3 available rooms.
    Asserts:
    - Exactly 3 threads succeed
    - Exactly 17 threads receive SoldOutException
    - Held == 3, sold + held <= total
    """
    target_date = date(2026, 12, 21)
    room_type = "estate-room"

    with session_factory() as setup_session:
        alt = setup_session.scalar(
            select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == target_date)
        )
        if not alt:
            alt = Allotment(room_type_id=room_type, date=target_date, total=3, sold=0, held=0)
            setup_session.add(alt)
        else:
            alt.total = 3
            alt.sold = 0
            alt.held = 0
        setup_session.commit()

    num_threads = 20
    barrier = Barrier(num_threads)

    def attempt_hold(thread_id):
        with session_factory() as session:
            barrier.wait()
            try:
                create_atomic_hold(session, room_type, [target_date], num_rooms=1)
                session.commit()
                return ("success", thread_id)
            except SoldOutException:
                session.rollback()
                return ("sold_out", thread_id)
            except Exception as e:
                session.rollback()
                return ("error", str(e))

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_hold, i) for i in range(num_threads)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == "success"]
    sold_outs = [r for r in results if r[0] == "sold_out"]
    errors = [r for r in results if r[0] == "error"]

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(successes) == 3, f"Expected exactly 3 successes, got {len(successes)}"
    assert len(sold_outs) == 17, f"Expected 17 sold out, got {len(sold_outs)}"

    with session_factory() as verify_session:
        alt = verify_session.scalar(
            select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == target_date)
        )
        assert alt.held == 3
        assert alt.sold == 0
        assert alt.total == 3
        assert alt.sold + alt.held <= alt.total


def test_concurrency_overlapping_multinight_variant(session_factory):
    """
    Overlapping multi-night contention:
    Dates: Day 1, Day 2, Day 3, Day 4.
    Capacity: 2 rooms on all days.
    Thread group A wants: Day 1 + Day 2 + Day 3
    Thread group B wants: Day 2 + Day 3 + Day 4
    Thread group C wants: Day 1 + Day 2
    Total 15 threads contending simultaneously.
    Asserts:
    - No deadlocks occur (all rows locked in strict date order)
    - Capacity is never exceeded on any single day (sold + held <= total)
    """
    base_d = date(2026, 12, 25)
    dates = [base_d + timedelta(days=i) for i in range(4)]
    room_type = "estate-room"

    with session_factory() as setup_session:
        for d in dates:
            alt = setup_session.scalar(
                select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == d)
            )
            if not alt:
                alt = Allotment(room_type_id=room_type, date=d, total=2, sold=0, held=0)
                setup_session.add(alt)
            else:
                alt.total = 2
                alt.sold = 0
                alt.held = 0
        setup_session.commit()

    num_threads = 15
    barrier = Barrier(num_threads)

    # 3 groups with overlapping stays
    stay_patterns = [
        [dates[0], dates[1], dates[2]],  # Days 0,1,2
        [dates[1], dates[2], dates[3]],  # Days 1,2,3
        [dates[0], dates[1]],            # Days 0,1
    ]

    def attempt_multinight(thread_id):
        stay = stay_patterns[thread_id % len(stay_patterns)]
        with session_factory() as session:
            barrier.wait()
            try:
                create_atomic_hold(session, room_type, stay, num_rooms=1)
                session.commit()
                return ("success", thread_id, stay)
            except SoldOutException:
                session.rollback()
                return ("sold_out", thread_id, stay)
            except Exception as e:
                session.rollback()
                return ("error", str(e), stay)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_multinight, i) for i in range(num_threads)]
        results = [f.result() for f in futures]

    errors = [r for r in results if r[0] == "error"]
    assert len(errors) == 0, f"Overlapping multi-night generated deadlock or errors: {errors}"

    # Verify database constraints on each day
    with session_factory() as verify_session:
        for d in dates:
            alt = verify_session.scalar(
                select(Allotment).where(Allotment.room_type_id == room_type, Allotment.date == d)
            )
            assert alt.held <= alt.total, f"Day {d} held {alt.held} exceeded total {alt.total}"
            assert alt.sold + alt.held <= alt.total
