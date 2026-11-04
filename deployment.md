# Deployment & Operations Guide — Plantation Stay

**GitHub Repository:** https://github.com/KhushiShs/plantation-stay-hill-resort

This document details the local setup, cloud deployment on Render + Neon PostgreSQL, configuration variable requirements, demo logins, and performance profiles for the **Plantation Stay** hill resort direct-booking application.

---

## 1. Local Setup Instructions

### Prerequisites
- Python 3.12+
- PostgreSQL 15+ (Local or Docker)
- Docker & Docker Compose (optional, recommended for clean database isolation)

### Option A: Running with Docker Compose (PostgreSQL)
1. Start the local PostgreSQL database:
   ```bash
   docker compose up -d db
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
3. Initialize and seed the database schema:
   ```bash
   python scripts/init_db.py
   ```
4. Start the development server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

### Option B: Running with Native Local PostgreSQL
1. Ensure your local PostgreSQL service is running and create the database:
   ```sql
   CREATE DATABASE plantation_stay;
   ```
2. Set `DATABASE_URL` in your `.env` file:
   ```env
   DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_stay
   ```
3. Run schema initialization:
   ```bash
   python scripts/init_db.py
   ```
4. Launch the application:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

---

## 2. Production Deployment (Render + Neon PostgreSQL)

### Step 1: Provision Neon PostgreSQL Database
1. Log into your [Neon Console](https://neon.tech).
2. Create a new project (e.g. `plantation-stay-prod`).
3. Copy the pooled connection string (format: `postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require`).
   *(Note: The application automatically normalizes this connection string to use the `postgresql+psycopg://` driver).*

### Step 2: Deploy to Render
1. In the [Render Dashboard](https://dashboard.render.com), click **New +** -> **Blueprint**.
2. Connect the GitHub repository: `https://github.com/KhushiShs/plantation-stay-hill-resort`.
3. Render reads `render.yaml` automatically:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips='*'`
   - **Health Check Path**: `/health`

### Step 3: Populate Environment Variables
Configure the required environment variable values in the Render Dashboard (**Environment** tab):

| Variable Name | Description | Example / Notes |
| :--- | :--- | :--- |
| `APP_ENV` | Environment mode (`production` or `development`) | `production` |
| `DATABASE_URL` | Neon PostgreSQL pooled connection URI | `postgresql://user:secret@ep-xyz.neon.tech/neondb?sslmode=require` |
| `SECRET_KEY` | Cryptographic secret for session cookie encryption | 64-char hex string (e.g. `openssl rand -hex 32`) |
| `WEBHOOK_SECRET` | HMAC SHA256 secret for mock payment verification | 64-char hex string |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames for HTTP Host header | `localhost,127.0.0.1,plantation-stay.onrender.com,*.onrender.com` |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI Enquiry Router | `sk-ant-api03-...` |
| `ANTHROPIC_MODEL` | Model specifier for Anthropic router | `claude-3-7-sonnet-20250219` |

> [!IMPORTANT]
> Never hardcode or commit actual secrets to version control. The repository contains only `.env.example` with variable names.

### Step 4: One-Off Database Initialization
In the Render Web Service shell or one-off job console, execute:
```bash
python scripts/init_db.py
```
This runs `Base.metadata.create_all()` and seeds initial room types, rate plans, promotional codes, GST tariff slabs, and 180 days of estate allotment if the database is unpopulated.

---

## 3. Cold-Start Warm-up & Monitoring

Render free/starter web services spin down after 15 minutes of inactivity.
- **Health Check Path**: `/health` runs a lightweight `SELECT 1` query to verify end-to-end database connectivity and returns `{"status":"ok"}`.
- **Warm-up Recommendation**: Configure an external ping monitor (e.g. UptimeRobot, BetterUptime, or Cron-job.org) to ping `https://your-service.onrender.com/health` every 10 minutes to prevent cold-start spin-down delays.

---

## 4. Demonstration Staff Logins

> [!NOTE]
> All names, phone numbers, booking references, and credentials in this codebase are synthetic test data created specifically for assessment purposes.

Staff portal URL: `/staff/login`

| Role | Username / Email | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **General Manager** | `gm@plantationstay.com` | `EstateGM2026!` | Full access: Rate calendar, allotments, blackouts, promos, bookings CSV export, enquiry inbox (all lanes including Unsorted and Complaints), refund processing, audit ledger. |
| **Reservations Staff** | `reservations@plantationstay.com` | `ResDesk2026!` | Daily allotments, room rates, bookings ledger, CSV export, room reservation enquiry routing. |

---

## 5. Measured Performance & Slow 4G Benchmarks

Measured on the production build with GZip compression and static asset caching enabled:

| Page / Resource | Gzip Payload Size | Slow 4G Estimated TTI (400 Kbps, 170ms RTT) | Budget Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Home Page HTML** | 7.75 KB | 0.83s | < 50 KB | PASS |
| **Estate Room Detail HTML (180 days)** | 141.16 KB | 3.50s | < 180 KB | PASS |
| **Core Non-image Assets** (CSS, HTMX, Calendar JS) | 73.13 KB | 2.14s | < 150 KB | PASS |
| **Home Total Load (HTML + Assets)** | 80.88 KB | 2.30s | < 3.50s | PASS |
| **Room Total Load (HTML + Assets)** | 214.29 KB | 4.97s | < 6.00s | PASS |

- **Image Delivery**: Hero and room imagery delivered in modern WebP format with responsive `<picture>` / `srcset` targeting 400w, 768w, and 1200w breakpoints.
- **Zero Client Frameworks**: Server-rendered Jinja2 + HTMX maintains total client JavaScript weight under 15 KB (excluding HTMX runtime).
