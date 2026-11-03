# Project: Plantation Stay, direct-booking site + AI enquiry routing for a hill resort

Project folder: Plantation-Stay-Hill_Resort
Product name: "Plantation Stay" (my own invention; the client brief only says
"Company A"). Use APP_NAME from app/config.py everywhere the name appears. Never
hardcode it in templates. Always quote file paths in shell commands.

## Context
Client "Company A", a coffee-estate resort in Chikkamagaluru, Karnataka: 64 rooms
+ 12 villas (76 keys), lawns for weddings and offsites, 140 staff, run by a General
Manager (GM). 68% of room nights come via online travel agencies at 18-22%
commission; only 12% are direct. The site is a brochure. Event enquiries arrive by
email, phone, social media and the GM's WhatsApp. Rates live in Excel.
Goal: a fast, beautiful direct-booking site where guests pick dates, see real
prices and pay, plus ONE enquiry inbox where every enquiry reaches the right person
with a reply ready.
Success targets: direct share 12% -> 20% of room nights in 12 months; median first
reply under 30 minutes in working hours; zero website overbookings.

## Stack (fixed)
Python 3.12, FastAPI, Jinja2 server-rendered templates, HTMX + minimal vanilla JS,
Postgres (Neon in production, local Postgres in dev; NOT SQLite), SQLAlchemy 2.0 +
psycopg, Pydantic validation, Starlette session cookies + bcrypt, pytest,
Anthropic SDK for the AI router. Deploy on Render. No SPA framework.

## Core build (must work end to end, 8 screens)
Guest (no account needed):
1. Home / room list: large photo per room type, "from Rs X" price
2. Room page: gallery, date picker, live availability, price with GST
3. Booking, 3 steps max: (1) dates + guests + rate plan, (2) details + DPDP consent
   checkbox + price breakdown, (3) mock payment
4. Confirmation page: booking reference + summary; look-up by reference + email
Staff (login; roles: reservations, gm):
5. Rate + allotment calendar: daily rate, website allotment, blackout dates, promo codes
6. Enquiry inbox with lanes: Room, Wedding, Offsite, Complaint, Unsorted
7. Enquiry detail: extracted fields, owner, editable draft, one-click re-route,
   Send (simulated)
8. Public enquiry form (wedding/event form if time allows)

Roles: guest and reservations staff (plus gm). Mock payments, messages and outside
systems. Seed from the sample data.

## Hard part: never overbook
Table allotment(room_type_id, date, total, sold, held), one row per night.
- HOLD: one transaction; UPDATE allotment SET held = held + 1 WHERE room_type_id=:r
  AND date IN (:nights) AND sold + held < total AND NOT blackout. If rowcount <
  number of nights, ROLLBACK and show "just sold out". Never read-then-write.
- Holds expire after HOLD_MINUTES (default 10): release lazily on read, plus a
  cleanup script.
- Payment success: held -> sold, idempotent, keyed on payment id (repeat webhook = no-op).
- Payment fail / abandon / expiry: release the hold.
- Website allotment is a separate admin-set number from the physical room count,
  so the site never sells agency stock.
- tests/test_concurrency.py: 20 threads on the last unit against real Postgres;
  assert exactly one succeeds and sold + held never exceeds total.

## Pricing
- All money is integer paise. No floats.
- price = nightly rate (room_type x date x rate_plan) -> promo -> GST per night by
  tariff slab. Slabs live in a gst_slabs table, seeded as an ASSUMPTION
  (e.g. 5% up to Rs 7,500/night, 18% above); mark them unverified in ASSUMPTIONS.md.
- Two rate plans: Room only; Room + breakfast (fixed per-person add-on).
- Show the breakdown: room total, discount, GST, grand total.
- Tests: slab boundaries, stays crossing a slab, promo rules, rounding.

## AI router
- On every new enquiry (web form, simulated email, simulated WhatsApp) call the
  model and require JSON: {category, confidence, dates, guests, budget, summary}.
  Categories: room, wedding, offsite, complaint.
- Validate with Pydantic. On invalid JSON, API error or timeout, use the keyword
  fallback classifier and flag the enquiry "classified by fallback".
- confidence < AI_CONFIDENCE_THRESHOLD (0.7) -> Unsorted lane, visible to the GM.
- Complaints ALWAYS alert the GM (in-app alert), regardless of confidence.
- Assign owner by category: room -> reservations, wedding/offsite -> sales,
  complaint -> GM.
- Draft reply uses placeholders like {{price_14_16_nov}}; code fills them from the
  rate table. The model NEVER writes a price or any number the rate table owns.
- Drafts are never sent automatically; staff edit and click Send (simulated).
- Staff re-route in one click; log every re-route in enquiry_events.
- Each inbox card shows "waiting N min", overdue highlighted (target: first reply
  under 30 min in working hours).
- Seed these three with EXACT IDs and messages:
  ENQ-4410 "Venue for my sister's wedding in Feb 2027, about 250 guests, 2 nights" -> Wedding
  ENQ-4411 "Is a villa free 14-16 Nov for 2 adults and a child?" -> Room booking
  ENQ-4412 "Team of 45 wants a January offsite with a conference hall" -> Corporate offsite
  Plus ~15 messy cases (Hinglish, mixed intent, no dates, a complaint disguised as
  a booking question). Expected categories go in data/enquiries_seed.json.
- The brief's "Out of scope: Ai or automation" line is treated as a typo, since the
  AI part is required. Note this in ASSUMPTIONS.md.

## Data model (tables)
users(role), room_types, rate_plans, daily_rates, allotment, gst_slabs, promo_codes,
bookings, booking_guests (minimal fields), payments, enquiries, enquiry_events
(classification, re-route, draft edits, sent), alerts.
Indexes: allotment(room_type_id, date), bookings(reference).

## Security and compliance
- Secrets only in env vars; keep .env.example with names only; never commit secrets.
- Validate every input with Pydantic; CSRF on forms; rate-limit public forms.
- Role checks server-side in dependencies. Guests cannot reach /staff or other
  guests' bookings. Complaint alerts and the unsorted lane are GM-visible.
- DPDP Act 2023: consent checkbox at booking, minimum fields only, fake data only.
- Do NOT collect passport details online (Form C is taken at check-in); say so on
  the confirmation page.
- Payment webhook requires a valid HMAC signature.
- Show GST at the rate for the tariff.

## Design
Minimal: one typeface, one accent colour, lots of white space, large photos as the
only decoration, nothing on screen without a purpose. Tokens in tokens.css.
Mobile-first and fast on slow hill-station networks: server-rendered, WebP at 3
sizes with srcset, lazy-load below the fold, non-image assets under ~150 KB,
minimal JS. Every screen has loading, empty and error states. Booking flow is
3 steps max.

## Out of scope
Replacing the reservation system or channel manager, loyalty programme, restaurant
bookings, video, timetables. Optional depth ONLY after the core works: wedding/event
form, daily booking CSV export, simulated forwarded-email/WhatsApp intake.

## Working rules
- Build in phases and STOP after each so I can review:
  Phase 1: models, seed, pricing, allotment + tests (concurrency test must pass).
  Phase 2: guest flow + mock payment.
  Phase 3: staff admin (rates, allotment, blackouts, promos).
  Phase 4: enquiry inbox + AI router.
  Phase 5: polish, access control, deploy.
- Give a short plan first and wait for approval before coding each phase.
- Small, clearly named commits after each working piece (history is reviewed).
- Write pricing and allotment code simply, with comments; I must explain it.
- Record every invented number in ASSUMPTIONS.md (room mix, rates, allotments,
  GST slabs, hold time, AI threshold, staff roles, product name).
- Fake names, emails and phone numbers only. Images: licence-free or placeholders.
- Run the tests before declaring a phase done.
- Submission needs: a TDD (PDF/Word) with the GitHub URL at the top, and
  deployment.md (local setup, deployment, env var NAMES, demo logins). Keep
  both easy to produce from docs/ and ASSUMPTIONS.md.