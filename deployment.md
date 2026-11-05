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
3. Set the three staff password variables in your `.env` (or shell) to any passwords you choose (minimum 12 characters each):
   ```env
   DEMO_RESERVATIONS_PASSWORD=YourPasswordChoice123!
   DEMO_GM_PASSWORD=YourPasswordChoice123!
   DEMO_SALES_PASSWORD=YourPasswordChoice123!
   ```
4. Initialize and seed the database schema:
   ```bash
   python scripts/init_db.py
   ```
5. Start the development server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

### Option B: Running with Native Local PostgreSQL
1. Ensure your local PostgreSQL service is running and create the database:
   ```sql
   CREATE DATABASE plantation_stay;
   ```
2. Set `DATABASE_URL` and `TEST_DATABASE_URL` in your `.env` file (DATABASE_URL = dev database, TEST_DATABASE_URL = test database, never the same):
   ```env
   DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_dev
   TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_test
   ```
3. Set `DEMO_RESERVATIONS_PASSWORD`, `DEMO_GM_PASSWORD`, and `DEMO_SALES_PASSWORD` in `.env` to any passwords of your choice (minimum 12 characters each).
4. Run schema initialization:
   ```bash
   python scripts/init_db.py
   ```
5. Launch the application:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

---

## 2. Production Deployment (Render + Neon PostgreSQL)

### Step 1: Provision Neon PostgreSQL Database
1. Log into your [Neon Console](https://neon.tech).
2. Create a new project (e.g. `plantation-stay-prod`).
3. Copy the pooled connection string (format: `postgresql://<user>:<password>@<endpoint>.us-east-2.aws.neon.tech/<dbname>?sslmode=require`).
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
| `DATABASE_URL` | Application database connection URI (dev/prod database, never the test database) | `postgresql://<db_user>:<db_password>@<db_host>/<db_name>?sslmode=require` |
| `TEST_DATABASE_URL` | Dedicated test database URI (DATABASE_URL = dev database, TEST_DATABASE_URL = test database, never the same) | `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_test` |
| `SECRET_KEY` | Cryptographic secret for session cookie encryption | Generate via `openssl rand -hex 32` |
| `WEBHOOK_SECRET` | HMAC SHA256 secret for mock payment verification | Generate via `openssl rand -hex 32` |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames for HTTP Host header | `localhost,127.0.0.1,plantation-stay.onrender.com,*.onrender.com` |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI Enquiry Router | Paste your key from console.anthropic.com |
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

## 4. Staff Accounts & Logins

> [!NOTE]
> All names, phone numbers, booking references, and credentials in this codebase are synthetic test data created specifically for assessment purposes.

Staff portal URL: `/staff/login`

### Local Development Logins
Set the three staff password environment variables to any passwords of your choice (minimum 12 characters each) in your `.env` file before running the seed script:
- `DEMO_RESERVATIONS_PASSWORD`
- `DEMO_GM_PASSWORD`
- `DEMO_SALES_PASSWORD`

| Role | Username / Email | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **General Manager** | `gm@plantationstay.local` | Set via `DEMO_GM_PASSWORD` | Full access: Rate calendar, allotments, blackouts, promos, bookings CSV export, enquiry inbox (all lanes including Unsorted and Complaints), refund processing, audit ledger. |
| **Reservations Staff** | `reservations@plantationstay.local` | Set via `DEMO_RESERVATIONS_PASSWORD` | Daily allotments, room rates, bookings ledger, CSV export, room reservation enquiry routing. |
| **Sales & Events** | `sales@plantationstay.local` | Set via `DEMO_SALES_PASSWORD` | Event and wedding enquiry lane, quotation drafts. |

### Production / Live Site Logins
Because the repository is public, live logins are provided separately in the submission. Production seeding requires `DEMO_RESERVATIONS_PASSWORD`, `DEMO_GM_PASSWORD`, and `DEMO_SALES_PASSWORD` (minimum 12 characters each) set in the hosting environment variables. No default or fallback passwords exist in this repository.

---

## 5. Measured Performance & Slow 4G Benchmarks

Measured on the production build with GZip compression and static asset caching enabled:

| Page / Resource | Gzip Payload Size | Slow 4G Estimated TTI (400 Kbps, 170ms RTT) | Budget Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Home Page HTML** | 7.75 KB | 0.83s | < 50 KB | PASS |
| **Estate Room Detail HTML (90 days / 3 mo)** | 5.22 KB | 0.78s | < 50 KB | PASS |
| **Core Non-image Assets** (CSS, HTMX, Calendar JS) | 21.50 KB | 1.10s | < 50 KB | PASS |
| **Home Total Load (HTML + Assets)** | 29.25 KB | 1.25s | < 3.50s | PASS |
| **Room Total Load (HTML + Assets)** | 26.72 KB | 1.21s | < 3.50s | PASS |

- **Image Delivery**: Hero and room imagery delivered in modern WebP format with responsive `<picture>` / `srcset` targeting 400w, 768w, and 1200w breakpoints.
- **Zero Client Frameworks**: Server-rendered Jinja2 + HTMX maintains total client JavaScript weight under 15 KB (excluding HTMX runtime).
