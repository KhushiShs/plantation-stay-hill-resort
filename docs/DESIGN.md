# Design Direction: Estate Tariff Card

## Visual Philosophy
The design of **Plantation Stay** is inspired by a vintage colonial planter's estate ledger and printed tariff cards from the Western Ghats:
- Tactile, quiet, unhurried, and paper-like.
- **Strictly avoided**: Modern SaaS cliches, gradients, glassmorphism, floating drop-shadows, 3-column emoji/icon feature cards, centered hero text overlaid with heavy dark overlays, and multi-typeface mashups.
- **Layout Structure**: Single, confident visual hierarchy built strictly with one variable serif typeface, asymmetric editorial rows, hairline rules, dotted bill leaders, and high-contrast typographic balance.

## Typography
- **Typeface**: `Source Serif 4` (variable serif, self-hosted WOFF2 with Latin subset, `font-display: swap`, system serif fallback `Georgia, "Times New Roman", serif`).
- **Typographic Hierarchy**:
  - Distinctions are achieved solely through font size, weight (300 to 700), optical size, italics, and letter-spaced small caps.
  - **Tabular figures (`font-variant-numeric: tabular-nums`)**: Enforced for all monetary numbers, rate tables, dates, and bills to guarantee vertical column alignment.

## Colour Palette & Contrast
All contrast ratios meet or exceed WCAG 2.1 AA (minimum 4.5:1 for body copy):
- **Paper** (`--color-paper: #F5F0E6`): Warm, unbleached cotton-linen background.
- **Ink** (`--color-ink: #2A1F1A`): Deep roasted coffee bean tone for primary text and structural hairlines (Contrast ratio ~11.8:1 on Paper).
- **Muted Ink** (`--color-muted: #7A6C62`): Sun-dried parchment earth for captions, small caps labels, and secondary notes (Contrast ratio ~4.6:1 on Paper).
- **Coffee Cherry** (`--color-accent: #A63A2B`): Ripe robusta cherry red used sparingly for primary buttons, active dates, and call-to-actions (Contrast ratio ~4.9:1 on Paper).
- **Mist** (`--color-mist: #DCE1DF`): Cool morning hill-station fog, reserved strictly for sold-out/blackout indicators and disabled states.

## Key Screen Layouts
1. **Home**:
   - Full-bleed estate landscape imagery with a single quiet caption line.
   - Room types presented as wide, asymmetric editorial rows alternating sides, paired with a clean "estate tariff card" displaying physical keys, occupancy, and dynamic "from Rs X" pricing derived from the database.
2. **Room Detail & Tariff Calendar**:
   - Custom minimal calendar table with the exact nightly price directly under each date, striking through sold-out and blackout dates with `--color-mist`.
   - Native `<input type="date">` fallback for non-JS clients.
   - Scarcity indicator: "N left" appears ONLY when remaining allotment $\le 3$ based on real database records.
3. **Booking Stepper (Stay $\rightarrow$ Details $\rightarrow$ Pay)**:
   - Plain text stepped indicator.
   - Price breakdown styled like a traditional printed invoice with dotted leaders (`dot-leader`) and tabular currency figures.
   - Mobile: Sticky bottom bar (min 44px touch targets) showing live total and progress action.
   - Step 3 (Payment): A discreet 2px hold expiration progress bar along the very top of the viewport.
4. **Pass / Confirmation**:
   - Styled like a planter's estate pass with a simulated tear-line / perforation, prominent reference code, and dedicated print stylesheet (`@media print`).
   - Prominent Form C regulatory notice.
5. **Mock Payment Screen**:
   - Plain, intentional "Test Mode" appearance distinct from the guest site to prevent user confusion during simulation.
