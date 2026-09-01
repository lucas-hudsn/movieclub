# Setup Guide

## Prerequisites

- **Python 3.13+** (project requires `==3.13.*`)
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **Docker** — for running PostgreSQL locally
- **OMDB API key** — get one at https://www.omdbapi.com/apikey.aspx

## Quick start

```bash
# 1. Clone the repo
git clone <repo-url>
cd movieclub

# 2. Start PostgreSQL
docker compose up -d db
# Runs on localhost:5433 (5432 is left free for any local Postgres)

# 3. Configure environment
cp .env.example .env
# Edit .env and fill in:
#   OMDB_API_KEY=your-key-here
#   SECRET_KEY=any-random-string

# 4. Apply database migrations
uv run alembic upgrade head

# 5. Start the dev server
uv run uvicorn app.main:app --port 8100
```

Open http://localhost:8100 in your browser. The first account you register becomes the admin.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `postgresql+psycopg://movieclub:movieclub@localhost:5433/movieclub` | PostgreSQL connection string |
| `SECRET_KEY` | Yes | `dev-secret-change-me` | Secret key for session cookies |
| `OMDB_API_KEY` | Yes | — | API key for the OMDB movie database |

## Running tests

```bash
uv run pytest
```

Tests use an in-memory SQLite database and a mocked OMDB client. No Docker or API key needed.

## Common issues

### Port 5433 already in use

Stop any existing container:

```bash
docker compose down
docker compose up -d db
```

### Migration errors

Reset the database (destroys all data):

```bash
docker compose down -v
docker compose up -d db
uv run alembic upgrade head
```

### OMDB API errors

Ensure your `OMDB_API_KEY` is set in `.env` and is a valid key from https://www.omdbapi.com/.
