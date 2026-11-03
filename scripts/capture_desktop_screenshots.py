"""Capture desktop screenshots at 1280px width."""
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screenshots"
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # 1280x800 desktop viewport
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    # 1. Desktop Home Screen
    print("Capturing 1. Desktop Home screen (1280px)...")
    page.goto(f"{BASE_URL}/")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "desktop_home_1280px.png"), full_page=True)

    # 2. Desktop Room Detail (Estate Room)
    print("Capturing 2. Desktop Room Detail screen (1280px)...")
    page.goto(f"{BASE_URL}/rooms/estate-room")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(OUT_DIR, "desktop_room_detail_1280px.png"), full_page=True)

    browser.close()
    print("Desktop screenshots captured successfully!")

