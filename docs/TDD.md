# Technical Design Document (TDD) — Plantation Stay

**GitHub Repository:** https://github.com/KhushiShs/plantation-stay-hill-resort  
**Product Name:** Plantation Stay  
**Target:** 76-key Coffee Estate Resort, Chikkamagaluru, Karnataka  

---

## 1. Executive Summary & Goals
Plantation Stay is a high-performance direct-booking web application and unified enquiry management platform built for a heritage coffee estate resort in Chikkamagaluru, Karnataka (64 estate rooms + 12 luxury villas).

### Strategic Objectives:
1. **Direct Booking Shift**: Increase direct room night bookings from 12% to 20% in 12 months, reducing dependence on online travel agencies (OTAs) charging 18–22% commission.
2. **Zero Overbookings**: Guarantee zero overselling via atomic SQL row-level locking on inventory allotments.
3. **Sub-30-Minute Enquiry Triage**: Route inbound event and guest enquiries to the correct team (Reservations, Sales, GM) with rate-table populated draft replies ready for review.

---

## 2. System Architecture & Technology Stack

The stack is strictly non-SPA, mobile-first, and optimized for low-bandwidth hill station network environments:

- **Backend**: Python 3.12, FastAPI (ASGI)
- **Database**: PostgreSQL (Neon in production, local PostgreSQL in dev)
- **ORM & Driver**: SQLAlchemy 2.0 with Psycopg (psycopg3) driver (`pool_pre_ping=True`)
- **Templating**: Server-rendered Jinja2 templates
- **Frontend Interaction**: HTMX + vanilla JavaScript (strict CSP `script-src 'self'`)
- **Styling**: Pure CSS using design tokens (`tokens.css`, `style.css`), self-hosted Newsreader serif font, zero UI frameworks
- **AI Classification**: Anthropic Claude API SDK with deterministic keyword fallback classifier
- **Security & Session**: Starlette SessionMiddleware with encrypted cookies, HMAC SHA256 webhook signatures, bcrypt password hashing

```
[ Client Browser ]
       |  (HTTPS, HTTP/2, GZip)
       v
[ FastAPI Application Server ]
   ├── Middleware Stack:
   │     ├── GZipMiddleware
   │     ├── SecurityHeadersMiddleware (CSP, HSTS, X-Frame-Options)
   │     ├── BodySizeLimitMiddleware (2 MB cap)
   │     ├── SessionMiddleware (Encrypted cookie)
   │     └── TrustedHostMiddleware (Host header whitelist)
   ├── Routers:
   │     ├── /rooms, /book (Guest direct booking flow)
   │     ├── /enquire (Wedding/Offsite intake form)
   │     └── /staff (Rate/Allotment calendar, Inbox, CSV export)
   └── Services:
         ├── PricingEngine (Integer paise, GST slabs)
         ├── AllotmentManager (Atomic SQL reservation holds)
         └── EnquiryRouter (Anthropic AI classification + fallback)
       |
       v
[ PostgreSQL Database (Neon / Local) ]
```

---

## 3. Data Model & Schema Design

All monetary amounts are represented as **64-bit integer paise** (1 INR = 100 paise) to eliminate floating-point arithmetic errors.

```
+--------------------+       +---------------------+       +--------------------+
|     room_types     |       |     daily_rates     |       |     allotment      |
+--------------------+       +---------------------+       +--------------------+
| id (PK, varchar)   |<-----\| id (PK, serial)     |       | id (PK, serial)    |
| name (varchar)     |       | room_type_id (FK)   |       | room_type_id (FK)  |
| description (text) |       | date (date)         |       | date (date)        |
| physical_keys (int)|       | rate_plan_id (FK)   |       | total (int)        |
| max_guests (int)   |       | price_paise (int)   |       | sold (int)         |
+--------------------+       +---------------------+       | held (int)         |
                                                           +--------------------+
                                                                     ^
                                                                     |
+--------------------+       +---------------------+                 |
|     rate_plans     |       |      bookings       |                 |
+--------------------+       +---------------------+                 |
| id (PK, varchar)   |       | id (PK, serial)     |                 |
| name (varchar)     |       | reference (varchar) |-----------------+
| addon_paise (int)  |       | room_type_id (FK)   | (Atomic holds)
+--------------------+       | rate_plan_id (FK)   |
                             | check_in (date)     |
                             | check_out (date)    |
                             | status (varchar)    |
                             | hold_expires_at     |
                             +---------------------+
```

### Key Entities:
1. `allotment`: Daily website allocation (`total`), `sold`, and `held` counts per room type per night.
2. `daily_rates`: Base rates in paise per room type per night.
3. `gst_slabs`: Indian GST tariff slabs (5% for rates <= ₹7,500/night; 18% above ₹7,500/night).
4. `enquiries`: Inbound communications across web form, email, and WhatsApp channels.
5. `enquiry_events`: Audit trail for re-routing, drafting, and simulated sending.

---

## 4. Concurrency & Inventory Reservation ("Never Overbook")

To guarantee that simultaneous reservation requests never exceed available website inventory, the booking engine utilizes **atomic SQL row-level updates**:

### Atomic Hold Algorithm:
```sql
UPDATE allotment
SET held = held + 1
WHERE room_type_id = :room_type_id
  AND date IN (:stay_dates)
  AND (sold + held) < total
  AND NOT blackout;
```
- **Execution**: Run inside a single database transaction.
- **Verification**: If `cursor.rowcount < number_of_nights`, the transaction is immediately rolled back, and the guest is informed that the dates have just sold out.
- **No Read-Then-Write**: Prevents race conditions and phantom reads entirely.
- **Hold Expiration**: Temporary holds are timestamped with `hold_expires_at = now() + 10 minutes`. Expired holds are released lazily upon read operations and via scheduled cleanup.
- **Verification**: Stress-tested under 20 concurrent threads against a live PostgreSQL instance in `tests/test_concurrency.py`.

---

## 5. Pricing & Taxation Engine

The pricing engine calculates total billables dynamically:
1. **Base Room Tariff**: Look up `daily_rates` for each night of stay.
2. **Rate Plan Add-on**: If "Room + Breakfast", add ₹750/person/night (75,000 paise).
3. **Promotions**: Apply percentage discount (e.g. `WELCOME10` = 10%) or flat rupee discount up to maximum discount caps.
4. **GST Calculation**: Evaluated per night based on the pre-tax nightly rate:
   - <= ₹7,500 per night: 5% GST
   - > ₹7,500 per night: 18% GST
5. **Grand Total**: Sum of discounted room nights + total GST in paise.

---

## 6. AI Enquiry Classification & Routing

Enquiries from public web forms, email, and WhatsApp intake are processed by the AI Enquiry Router:
- **LLM Pipeline**: Calls Anthropic Claude using a structured schema prompt, extracting `{category, confidence, dates, guests, budget, summary}`.
- **Categories**: `room`, `wedding`, `offsite`, `complaint`.
- **Validation**: Validated with Pydantic models. On invalid JSON, timeout, or API error, the deterministic **Keyword Fallback Classifier** executes and tags the record `classified_by="fallback"`.
- **Confidence Gate**: Enquiries with `confidence < 0.70` are routed to the **Unsorted** lane visible directly to the GM.
- **Complaint Protocol**: Complaints immediately generate an urgent in-app alert for the General Manager regardless of confidence score.
- **Rate-Table Draft Replies**: Draft replies incorporate rate-derived pricing templates (e.g. `{{price_14_16_nov}}`) resolved from the rate table; the LLM is prohibited from inventing tariffs.

---

## 7. Security, DPDP Compliance & Hardening

1. **Digital Personal Data Protection (DPDP) Act 2023**: Mandatory explicit consent checkboxes on booking and enquiry forms; data collected is strictly minimized.
2. **Form C Compliance**: No passport numbers or nationality documents are collected online. The confirmation page clearly advises guests that identity verification occurs physically at check-in.
3. **CSRF & Rate Limiting**: Form tokens and sliding-window rate limiters defend against spam submissions.
4. **Content Security Policy (CSP)**: Strict `script-src 'self'` policy with zero inline scripts.
5. **Formula-Safe CSV Export**: Cells in staff booking exports starting with `=`, `+`, `-`, or `@` are prefixed with `'` to prevent CSV spreadsheet formula injection.

---

## 8. Test Verification & Code Quality

The system is validated by an automated test suite of 99 unit, integration, and concurrency tests:
- `tests/test_concurrency.py`: 20 concurrent threads competing for last room unit.
- `tests/test_pricing.py`: GST slab thresholds, promo codes, multi-night spans.
- `tests/test_router.py`: AI classification, seed message routing, complaint alerts.
- `tests/test_guest_flow.py`: Complete booking flow from dates to confirmation.
- `tests/test_security_hardening.py`: Trusted hosts, CSP, body size limit, health check.
- `tests/test_room_calendar.py`: Interactive calendar pagination and state tracking.

**Suite Status**: `99 passed in 254.16s`
