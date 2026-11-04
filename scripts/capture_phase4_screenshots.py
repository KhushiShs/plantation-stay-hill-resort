"""Capture 768px tablet and 375px mobile screenshots for Enquiry screens."""
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screenshots"
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # -------------------------------------------------------------
    # 1. Tablet Viewport (768 x 1024)
    # -------------------------------------------------------------
    tablet_context = browser.new_context(
        viewport={"width": 768, "height": 1024},
        user_agent="Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    )
    t_page = tablet_context.new_page()

    # Public Form (768px)
    print("Capturing Public Enquiry Form (768px)...")
    t_page.goto(f"{BASE_URL}/enquire")
    t_page.wait_for_load_state("networkidle")
    t_page.screenshot(path=os.path.join(OUT_DIR, "enquiry_public_form_768px.png"), full_page=True)

    # Staff Login as GM
    print("Staff login on tablet...")
    t_page.goto(f"{BASE_URL}/staff/login")
    t_page.wait_for_load_state("networkidle")
    t_page.fill('input[name="email"]', "gm@plantationstay.local")
    t_page.fill('input[name="password"]', "os.environ[DEMO_GM_PASSWORD]")
    t_page.click('button[type="submit"]')
    t_page.wait_for_load_state("networkidle")

    # Staff Inbox (768px)
    print("Capturing Staff Enquiry Inbox (768px)...")
    t_page.goto(f"{BASE_URL}/staff/enquiries")
    t_page.wait_for_load_state("networkidle")
    t_page.screenshot(path=os.path.join(OUT_DIR, "staff_inbox_768px.png"), full_page=True)

    # Staff Enquiry Detail (768px)
    print("Capturing Staff Enquiry Detail (768px)...")
    t_page.goto(f"{BASE_URL}/staff/enquiries/ENQ-4411")
    t_page.wait_for_load_state("networkidle")
    t_page.screenshot(path=os.path.join(OUT_DIR, "staff_enquiry_detail_768px.png"), full_page=True)

    tablet_context.close()

    # -------------------------------------------------------------
    # 2. Mobile Viewport (375 x 812)
    # -------------------------------------------------------------
    mobile_context = browser.new_context(
        viewport={"width": 375, "height": 812},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    )
    m_page = mobile_context.new_page()

    # Public Form (375px)
    print("Capturing Public Enquiry Form (375px)...")
    m_page.goto(f"{BASE_URL}/enquire")
    m_page.wait_for_load_state("networkidle")
    m_page.screenshot(path=os.path.join(OUT_DIR, "enquiry_public_form_375px.png"), full_page=True)

    # Staff Login as GM
    print("Staff login on mobile...")
    m_page.goto(f"{BASE_URL}/staff/login")
    m_page.wait_for_load_state("networkidle")
    m_page.fill('input[name="email"]', "gm@plantationstay.local")
    m_page.fill('input[name="password"]', "os.environ[DEMO_GM_PASSWORD]")
    m_page.click('button[type="submit"]')
    m_page.wait_for_load_state("networkidle")

    # Staff Inbox (375px)
    print("Capturing Staff Enquiry Inbox (375px)...")
    m_page.goto(f"{BASE_URL}/staff/enquiries")
    m_page.wait_for_load_state("networkidle")
    m_page.screenshot(path=os.path.join(OUT_DIR, "staff_inbox_375px.png"), full_page=True)

    # Staff Enquiry Detail (375px)
    print("Capturing Staff Enquiry Detail (375px)...")
    m_page.goto(f"{BASE_URL}/staff/enquiries/ENQ-4411")
    m_page.wait_for_load_state("networkidle")
    m_page.screenshot(path=os.path.join(OUT_DIR, "staff_enquiry_detail_375px.png"), full_page=True)

    mobile_context.close()

    browser.close()
    print("All Phase 4 screenshots captured successfully!")
