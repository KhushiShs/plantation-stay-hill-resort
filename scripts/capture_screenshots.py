"""Capture mobile screenshots at 375px width."""
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screenshots"
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # 375x667 viewport (iPhone SE dimensions)
    context = browser.new_context(
        viewport={"width": 375, "height": 667},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    page = context.new_page()

    # 1. Mobile Home Screen
    print("Capturing 1. Home screen...")
    page.goto(f"{BASE_URL}/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "01_mobile_home_375px.png"), full_page=True)

    # 2. Mobile Room Detail (Estate Room)
    print("Capturing 2. Room detail screen...")
    page.goto(f"{BASE_URL}/rooms/estate-room")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "02_mobile_room_detail_375px.png"), full_page=True)

    # 3. Mobile Booking Step 1 & 2 (Details & DPDP Consent & Bill Breakdown)
    print("Capturing 3. Booking step 1 & 2 screen...")
    page.goto(f"{BASE_URL}/book?room_type_id=estate-room&rate_plan_id=room_breakfast&check_in=2026-12-01&check_out=2026-12-03&num_guests=2")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="guest_name"]', "Rohan Deshmukh")
    page.fill('input[name="guest_email"]', "rohan@example.com")
    page.fill('input[name="guest_phone"]', "+91 98765 43210")
    page.check('input[name="dpdp_consent"]')
    page.screenshot(path=os.path.join(OUT_DIR, "03_mobile_booking_details_375px.png"), full_page=True)

    # Submit to Step 3 Mock Payment
    print("Submitting hold and navigating to Step 3 Mock Payment...")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    
    # 4. Mobile Step 3 Mock Payment Gateway (2px line hold timer, test mode badge)
    print("Capturing 4. Step 3 Mock Payment...")
    page.screenshot(path=os.path.join(OUT_DIR, "04_mobile_payment_step3_375px.png"), full_page=True)

    # Submit Mock Payment Success
    print("Simulating successful mock payment...")
    page.click('button:has-text("Pay")')
    page.wait_for_load_state("networkidle")

    # 5. Mobile Booking Confirmation (Pass format, tear-line, Form C notice)
    print("Capturing 5. Booking Confirmation pass...")
    page.screenshot(path=os.path.join(OUT_DIR, "05_mobile_confirmation_pass_375px.png"), full_page=True)

    # 6. Booking Lookup
    print("Capturing 6. Booking lookup screen...")
    page.goto(f"{BASE_URL}/booking-lookup")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "06_mobile_booking_lookup_375px.png"), full_page=True)

    browser.close()
    print("All mobile screenshots captured successfully!")
