# MOVIE CLUB // `▚▚ SIGNAL ACQUIRED ▚▚`

A monthly movie club app for teams: everyone submits a film, everyone watches and ranks,
the club crowns a monthly winner, and the loser's pick earns their submitter a month
on the bench.

![stack](https://img.shields.io/badge/FastAPI-Jinja2%20%2B%20HTMX-00ff41)

## How a cycle works

1. **SUBMITTING** — each member picks one movie (searched live against [OMDB](https://www.omdbapi.com/)). One pick per person, no duplicate movies.
2. **RANKING** — an admin locks submissions. Every member orders all films best → worst with ▲▼ controls. Points are awarded by **Borda count**: position 1 of N films gets `N−1` points, last gets `0`. Members can abstain (inactive ballots aren't tallied).
3. **CLOSED** — the film with the most points wins; the film with the fewest points sends its submitter to the bench: they can still watch and rank next month, but cannot submit. A new cycle starts automatically.

An all-time **leaderboard** tallies wins and losses per member.

## Stack

| Layer    | Choice                                                        |
| -------- | ------------------------------------------------------------- |
| Backend  | FastAPI, Jinja2 templates, HTMX fragments                      |
| Database | PostgreSQL (SQLAlchemy 2.0 + Alembic migrations)               |
| Auth     | Email + password (argon2), signed session cookie               |
| Movies   | OMDB API (`OMDB_API_KEY` in `.env`)                            |
| Styling  | Hand-rolled CSS — black / phosphor-green CRT lofi cinema theme |

## Getting started

Requires Python 3.14+ ([uv](https://docs.astral.sh/uv/)), Docker, and an OMDB API key.

```bash
# 1. Start Postgres (port 5433 — 5432 is left free for any local instance)
docker compose up -d db

# 2. Configure secrets
cp .env.example .env        # then fill in OMDB_API_KEY and SECRET_KEY

# 3. Apply migrations
uv run alembic upgrade head

# 4. Run
uv run uvicorn app.main:app --port 8100
```

Open <http://localhost:8100> — **the first account registered becomes the admin.**

### Running tests

```bash
uv run pytest
```

Tests run against in-memory SQLite; no Docker needed. The full cycle lifecycle is covered end-to-end with a mocked OMDB client.

## Project layout

```
app/
  main.py            app factory, static files, error pages
  config.py          pydantic-settings (.env)
  database.py        engine/session
  models.py          User, Cycle, Submission, Ranking
  security.py        password hashing + session cookies
  dependencies.py    auth guards
  services/
    omdb.py          OMDB search/detail client
    scoring.py       Borda tally + winner/loser resolution
  routers/
    auth.py          register/login/logout
    movies.py        search + submission management
    cycles.py        dashboard, phase transitions, leaderboard
    rankings.py      ballot ordering (HTMX)
  templates/         Jinja2 pages + HTMX partials
  static/css/        the matrix theme
alembic/             migrations
tests/
```

## Useful commands

```bash
uv run alembic revision --autogenerate -m "..."   # new migration after model changes
uv run alembic upgrade head                       # apply migrations
uv run pytest                                     # test suite
docker compose up -d db                           # start database
```

## Deployment (FastAPI Cloud + Supabase)

The app is deployed on [FastAPI Cloud](https://fastapicloud.com) with the database hosted on Supabase Postgres (app auth stays as-is; Supabase is used purely as the Postgres host).

1. **Connect Supabase to FastAPI Cloud** — Team settings → Integrations → connect Supabase. Then on your app's Integrations tab, pick your Supabase project and enter its DB password. FastAPI Cloud injects a `DATABASE_URL` secret automatically.
2. **Set remaining env vars** — `SECRET_KEY` (as a secret) and `OMDB_API_KEY`:
   ```bash
   fastapi cloud env set --secret SECRET_KEY "..."
   fastapi cloud env set OMDB_API_KEY "..."
   ```
   The app normalizes `DATABASE_URL` itself (`postgresql://` → `postgresql+psycopg://`, adds `sslmode=require`), so the injected value works unchanged.
3. **Migrate the database** — migrations are not run automatically on deploy, so apply them against Supabase before/alongside deploying:
   ```bash
   DATABASE_URL="postgresql+psycopg://...supabase..." uv run alembic upgrade head
   ```
4. **Deploy**:
   ```bash
   uv run fastapi login    # first time only
   uv run fastapi deploy   # entrypoint app/main.py:app is auto-detected
   ```

Remember: when adding columns, migrate **before** deploying; when removing them, deploy first and migrate after (zero-downtime gradual deployments mean old and new code run side by side).
