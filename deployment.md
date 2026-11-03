# Deployment & Local Setup Guide

## Local Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 15+ (local instance or Neon cloud database)

### Installation
1. Clone the repository and enter directory:
   ```bash
   cd Plantation-Stay-Hill_Resort
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Populate `.env` with your database and API credentials.

5. Run development server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Environment Variable Names
The application relies on the following environment variables (defined in `.env.example`):
- `DATABASE_URL`: PostgreSQL connection string (`postgresql+psycopg://user:password@host/dbname`)
- `SECRET_KEY`: Secret string for cryptographic signing and session cookies
- `ANTHROPIC_API_KEY`: API key for Anthropic SDK AI router
- `WEBHOOK_SECRET`: HMAC signature verification key for mock payment callbacks
- `ENVIRONMENT`: Environment mode (`development` / `production`)
- `HOLD_MINUTES`: Booking hold duration before expiry (default: `10`)
- `AI_CONFIDENCE_THRESHOLD`: Minimum confidence score for auto-routing enquiries (default: `0.7`)

## Demo Logins (Staff)
- **General Manager (GM)**: `gm@plantationstay.local` / role: `gm`
- **Reservations Staff**: `reservations@plantationstay.local` / role: `reservations`

## Deployment (Render)
The application is configured for deployment on Render via `render.yaml`:
- **Web Service**: Python runtime running Uvicorn
- **Managed Database**: PostgreSQL instance
