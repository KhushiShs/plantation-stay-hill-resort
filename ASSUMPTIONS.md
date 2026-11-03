# Project Assumptions & Parameter Log

This document records all baseline assumptions, invented values, parameters, and architectural notes per project specification (`AGENTS.md`) and implementation decisions.

## 1. Product & Business Context
- **Product Name**: "Plantation Stay" (client brief designated as "Company A"). Retrieved from `app.config.APP_NAME`. Never hardcoded in templates.
- **Property Location & Context**: Working coffee-estate resort in Chikkamagaluru, Karnataka.
- **Property Size & Room Mix**: Total 76 keys across 64 rooms and 12 villas:
  - Estate Rooms (`estate-room`): 64 physical keys
  - Luxury Villas (`luxury-villa`): 12 physical keys
- **Scope Clarification**: The brief's note stating *"Out of scope: Ai or automation"* is treated as a typo, since the AI router specification is explicitly required.

## 2. Room Rates & Website Allotments
- **Estate Room (`estate-room`)**:
  - Total Physical Inventory: 64 rooms
  - Website Allotment: 25 rooms
  - Weekday Rate (Sun–Thu): Rs 7,000 / night (`700000` paise)
  - Weekend Rate (Fri–Sat): Rs 9,000 / night (`900000` paise)
- **Luxury Plantation Villa (`luxury-villa`)**:
  - Total Physical Inventory: 12 villas
  - Website Allotment: 5 villas
  - Weekday Rate (Sun–Thu): Rs 16,000 / night (`1600000` paise)
  - Weekend Rate (Fri–Sat): Rs 20,000 / night (`2000000` paise)
  - Special requirement: Exactly 1 villa available on 14–16 Nov 2026 (allotment has 4 sold, 0 held, 1 remaining).
- **Rate Schedule**: Seeded for 180 days from start date across both room types.

## 3. Rate Plans & Add-ons
- **Room Only (`room_only`)**: Base accommodation, breakfast add-on = Rs 0.
- **Room + Breakfast (`room_breakfast`)**: Includes gourmet plantation breakfast buffet at fixed add-on of Rs 750 / person / night (`75000` paise).

## 4. Pricing Calculation & GST Slabs (Integer Basis Points)
- **Money Standard**: All money throughout the database, business logic, and API is stored and calculated in integer **paise** (`BIGINT`). Zero floats or Decimal approximations in money calculations.
- **Basis Points**: Percentages stored in integer basis points (`100 bps = 1.00%`, `10000 bps = 100%`).
- **GST Slabs (Unverified assumption per AGENTS.md)**:
  - Declared Tariff $\le$ Rs 7,500 / night (`750000` paise): **5% GST** (`500` bps)
  - Declared Tariff $>$ Rs 7,500 / night: **18% GST** (`1800` bps)
- **Slab Selection Rule**: The GST slab is chosen strictly on the **declared room tariff per night** (before promo discount and breakfast add-on).
- **GST Application Rule**: GST applies to the discounted room tariff plus the breakfast add-on:
  $$\text{Taxable} = (\text{Base} - \text{Discount}) + \text{Breakfast}$$
  $$\text{GST} = \text{round\_half\_up}\left(\text{Taxable} \times \frac{\text{GST bps}}{10000}\right)$$
- **Rounding Rule**: Per night, round half up to the paisa, then sum across nights.
- **Multi-Slab Display**: For stays crossing weekend/weekday tariff slabs (e.g. Fri Rs 9,000 [18% slab] + Sun Rs 7,000 [5% slab]), the bill dynamically itemizes GST per slab (e.g., `GST 5% x 1 night`, `GST 18% x 1 night`).

## 5. Promotional Codes
- `WELCOME10`: 10% discount (`1000` bps) applied to base room tariff, valid for 12 months.

## 6. Allotment, Holds & Concurrency
- **Hold Duration**: 10 minutes (`HOLD_MINUTES = 10`). Created at "Continue to Payment" (end of Step 2), never on passive page view.
- **Hold Atomicity**: Atomic `UPDATE allotment SET held = held + :n WHERE date IN (...) AND sold + held + :n <= total AND NOT blackout`.
- **Deadlock Avoidance**: Updates sorted in strict ascending date order, with 1 retry on deadlock (Postgres SQLSTATE 40P01).
- **Release Order**: Booking is claimed first (`UPDATE bookings SET status='expired' WHERE status='held' RETURNING ...`), and allotment is decremented only if a row was returned.
- **Confirm Order**:
  1. `UPDATE payments pending -> success` with amount check (rowcount 0 = no-op / repeat webhook).
  2. `UPDATE bookings held -> confirmed`. If rowcount 0 (hold had expired), retry atomic hold. If re-hold fails, mark payment `needs_refund`.
  3. Move `held -> sold` on allotment.

## 7. Security, Webhooks & Rate Limiting
- **Booking References**: Unguessable cryptographically secure tokens generated via `secrets.token_urlsafe` (e.g., `BK-A9F8X2Q1`).
- **Session Isolation**: Sessions store `guest_booking_ref`. Actions like mock-pay, mock-fail, and mock-abandon verify both CSRF tokens and signed session cookie authorization to prevent session tampering or cross-guest cancellations.
- **Webhook HMAC Signatures**: Webhook payloads are signed with SHA256 HMAC as `payment_id:booking_id:amount:timestamp`. Stale timestamps older than 5 minutes (300 seconds) are rejected with HTTP 400. Stored payment amount is verified against database records, ignoring client-supplied body amounts.
- **In-Memory Rate Limiting**: Helper function `check_rate_limit(request, route_key, max_requests, window_seconds)` tracks requests in an in-memory dictionary `(client_ip, route_key) -> [timestamps]`. Note: In-memory store resets on server restart/re-deployment; exposed `reset_rate_limits()` helper is called directly in test fixtures.

## 8. Staff Portal, Input Caps & Audit Rules
- **Role Hierarchy & Access Boundaries**:
  - `reservations`: Can view & modify rates, allotments, blackout status, promo codes, booking ledger, and issue refunds on the simulated needs-refund queue.
  - `gm`: Possesses all permissions of `reservations` plus visibility into the immutable append-only `audit_logs` ledger.
  - `sales`: Restricted role; receives HTTP 403 Forbidden on all rate/promo/booking admin actions (used in Phase 4 for enquiries).
- **Staff Input Parsing & Caps**:
  - Staff rupee and percent inputs are parsed with strict `Decimal` from strings only (no floats).
  - Maximum 2 decimal places allowed; negative values rejected.
  - `MAX_RUPEES = Decimal("500000.00")` (Rs 5,00,000 / night per room) to prevent integer overflow or clerical errors.
  - `MAX_PERCENT = Decimal("100.00")` (10,000 basis points).
  - Rupee values are converted to integer paise (`int(Decimal * 100)`).
  - Percent values are converted to basis points (`int(Decimal * 100)`).
- **Range Updates**:
  - Staff can update single dates or date ranges up to 180 days (`end_date >= start_date`).
  - Executed in a single atomic transaction.
  - Capacity Check: If a new website allotment would fall below existing `sold + held` on any night in the range, the entire transaction is rolled back and the failing dates are listed in a friendly flash error without raising a database 500 exception.
- **Blackout Semantics**:
  - Blackout toggling blocks subsequent holds on guest routes (`AND NOT blackout`).
  - Existing confirmed bookings remain honored and are never cancelled; sold/held allotments are never modified by blackout changes.
  - Staff UI warns with the count of already-confirmed bookings overlapping the blacked-out window.
- **Booking Price Immutability**:
  - Confirmed bookings store nightly price snapshots (`booking_nights`). Administrative rate changes never mutate past or already-booked reservations.
- **Refund Queue**:
  - "Mark Refunded" triggers an idempotent atomic update (`UPDATE payments SET status = 'refunded' WHERE status = 'needs_refund'`).
  - Explicitly labeled in the UI as simulated.
- **CSV Data Sanitization**:
  - Booking CSV export escapes formula-leading characters (`=`, `+`, `-`, `@`) with a single-quote prefix to safeguard against spreadsheet formula injection. Restricted to `reservations` and `gm`.
- **Search Engine Indexing & Robots**:
  - `<meta name="robots" content="noindex, nofollow">` on all `/staff` pages.
  - `/static/robots.txt` explicitly disallows `/staff` and `/staff/`.
- **Responsive Layout**:
  - 768px tablet layout supported with horizontal scroll containers on tabular ledgers, grid wrapping for form fields, and responsive typography.

## 9. Typography & Asset Licences
- **Typeface**: Single self-hosted variable font family: `Newsreader` (Google Fonts / Production Type), licensed under the SIL Open Font License (OFL 1.1). Hosted as subset WOFF2 (`newsreader-latin.woff2`, `newsreader-italic-latin.woff2`).
- **Photography & Placeholders**:
  - `docs/photos_todo.md` is currently absent, so no third-party licence-free photographs are assumed or invented.
  - Per project instructions, no photographers or external licences are fabricated.
  - Exactly the following images are locally generated flat paper-colour placeholders (`#F5F0E6` background, `#7A6C62` subtle border, `#2A1F1A` Newsreader title text):
    1. `/static/images/estate-hero.webp` (Hero banner on Home)
    2. `/static/images/estate-room.webp` & `/static/images/estate-room-thumb.webp` (Estate Room gallery & thumbnail)
    3. `/static/images/luxury-villa.webp` & `/static/images/luxury-villa-thumb.webp` (Luxury Villa gallery & thumbnail)
  - All placeholder images maintain `aspect-ratio: 16/9`, `fetchpriority="high"` on hero, and native `loading="lazy"` for below-the-fold content.

## 9. Staff Roles & Demo Users
- `reservations`: `reservations@plantationstay.local` / `ReservationsDemo2026!`
- `gm`: `gm@plantationstay.local` / `GMDemo2026!`
- `sales`: `sales@plantationstay.local` / `SalesDemo2026!`

## 10. Test Safety
- All test suites abort execution immediately unless database name ends with `_test`.
