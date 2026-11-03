# Project Assumptions & Parameter Log

This document records all baseline assumptions, invented values, parameters, and notes per project specification (AGENTS.md).

## Product & Business Context
- **Product Name**: "Plantation Stay" (client brief designated as "Company A").
- **Property Size & Room Mix**: Total 76 keys across 64 rooms and 12 villas in Chikkamagaluru, Karnataka.
  - Estate Rooms: 64 keys
  - Luxury Villas: 12 keys
- **Scope Clarification**: The brief's note stating *"Out of scope: Ai or automation"* is treated as a typo, since the AI router specification is explicitly required.

## Allotment & Booking Parameters
- **Hold Duration**: 10 minutes (`HOLD_MINUTES = 10`). Holds are released lazily on read plus via periodic cleanup script.
- **Website Allotment**: Admin-set allocation dedicated to direct booking, completely separate from physical total / OTA allocations to prevent overbooking.

## Pricing & GST Slabs (Unverified / Seed Baseline)
- All monetary values stored and calculated in integer **paise** (no floating point currency).
- **GST Slabs (Assumption - unverified)**:
  - Tariff up to Rs 7,500 / night: **5% GST**
  - Tariff above Rs 7,500 / night: **18% GST**
- **Rate Plans**:
  - Room Only (Base)
  - Room + Breakfast (Fixed add-on per person)

## AI Router & Enquiry Handling
- **AI Router Confidence Threshold**: 0.7 (`AI_CONFIDENCE_THRESHOLD = 0.7`). Enquiries with confidence below 0.7 route to the Unsorted lane for GM review.
- **Enquiry Routing Owners**:
  - `room` -> Reservations
  - `wedding` -> Sales
  - `offsite` -> Sales
  - `complaint` -> General Manager (GM) (Always alerts GM in-app regardless of confidence)
- **Target Response Time**: Median first reply under 30 minutes during working hours.

## Roles & Access Control
- **Staff Roles**: `reservations`, `gm`.
- **Guest Access**: No account required to browse, check availability, or book. Look-up by booking reference and guest email.
