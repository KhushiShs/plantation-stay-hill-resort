# Project Assumptions & Parameter Log

This document records all baseline assumptions, invented values, parameters, and architectural notes per project specification (`AGENTS.md`) and implementation decisions.

## 1. Product & Business Context
- **Product Name**: "Plantation Stay" (client brief designated as "Company A"). Retrieved from `app.config.APP_NAME`.
- **Property Size & Room Mix**: Total 76 keys across 64 rooms and 12 villas in Chikkamagaluru, Karnataka.
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

## 7. Staff Roles & Demo Users
- `reservations`: `reservations@plantationstay.local` / `ReservationsDemo2026!`
- `gm`: `gm@plantationstay.local` / `GMDemo2026!`
- `sales`: `sales@plantationstay.local` / `SalesDemo2026!`

## 8. Test Safety
- All test suites abort execution immediately unless database name ends with `_test`.
