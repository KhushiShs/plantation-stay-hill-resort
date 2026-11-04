"""Capture 768px tablet screenshots for staff admin screens."""
import os
import re
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screenshots"
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # 768x1024 tablet viewport
    context = browser.new_context(
        viewport={"width": 768, "height": 1024},
        user_agent="Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    page = context.new_page()

    # 1. Staff Login
    print("Navigating to login...")
    page.goto(f"{BASE_URL}/staff/login")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="email"]', "gm@plantationstay.local")
    page.fill('input[name="password"]', "os.environ[DEMO_GM_PASSWORD]")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # 2. Staff Calendar (768px)
    print("Capturing 1. Staff Calendar (768px)...")
    page.goto(f"{BASE_URL}/staff/calendar")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "staff_calendar_768px.png"), full_page=True)

    # 3. Staff Promos (768px)
    print("Capturing 2. Staff Promos (768px)...")
    page.goto(f"{BASE_URL}/staff/promos")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "staff_promos_768px.png"), full_page=True)

    # 4. Staff Bookings (768px)
    print("Capturing 3. Staff Bookings (768px)...")
    page.goto(f"{BASE_URL}/staff/bookings")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "staff_bookings_768px.png"), full_page=True)

    browser.close()
    print("All 768px staff screenshots captured successfully!")
