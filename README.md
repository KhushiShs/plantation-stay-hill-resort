# Plantation Stay

Direct-booking site and AI enquiry routing for a luxury hill resort in Chikkamagaluru, Karnataka.

## Overview
- **Product Name**: Plantation Stay (defined in `app/config.py`)
- **Client**: Coffee-estate hill resort (64 rooms + 12 villas; 76 keys total)
- **Stack**: Python 3.12, FastAPI, Jinja2, HTMX + minimal vanilla JS, PostgreSQL (Neon / Docker local), SQLAlchemy 2.0 + Psycopg 3, Anthropic SDK

## Local Database Setup (Docker Compose)
A `docker-compose.yml` is provided to spin up a local PostgreSQL 16 container pre-configured with both `plantation_dev` and `plantation_test` databases:

```bash
# Start PostgreSQL container
docker compose up -d

# Verify databases are running
docker compose ps
```

The database connection strings will be:
- Dev: `postgresql+psycopg://postgres:postgres@localhost:5432/plantation_dev`
- Test: `postgresql+psycopg://postgres:postgres@localhost:5432/plantation_test`

## Getting Started
See [deployment.md](deployment.md) for local setup, environment configuration, and deployment details.
See [ASSUMPTIONS.md](ASSUMPTIONS.md) for recorded assumptions, pricing slabs, allotments, and thresholds.
