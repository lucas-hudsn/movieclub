# MOVIE CLUB

**Live: <https://movieclub.fastapicloud.dev>**

A monthly movie club app for teams: everyone submits a film, everyone watches and ranks,
the club crowns a monthly winner, and the losering pick earns their submitter a month
on the bench.

![stack](https://img.shields.io/badge/FastAPI-Jinja2%20%2B%20HTMX-00ff41)

## How a cycle works

1. **SUBMITTING** — each member picks one movie (searched live against [OMDB](https://www.omdbapi.com/)). One pick per person, no duplicate movies. An admin must **lock submissions** (requires the minimum submissions: min of 4 and team size) before ranking can start.
2. **RANKING** — an admin starts ranking after locking. Every member orders all locked films best → worst with ▲▼ controls on the `/vote` page. Points are awarded by **Borda count**: position 1 of N films gets `N−1` points, last gets `0`. Members can abstain (inactive ballots aren't tallied). Admins can **reopen submissions** to return to the submitting phase (clears all votes), or **go back** from a closed cycle to reopen it for ranking.
3. **CLOSED** — the film with the most points wins; the film with the fewest points sends its submitter to the bench: they can still watch and rank next month, but cannot submit. A new cycle starts automatically.

**Admin shortcuts:** at any point an admin can **skip to the next stage** (force-open ranking without the minimum-submission gate, or force-close and tally even with partial voting) and **go back** (revert ranking → submitting, or closed → ranking). Useful when members are lagging or a mistake was made.

An all-time **leaderboard** tallies wins and losses per member.

Joining is invite-only: the team creator shares a code from `/team`, and nobody gets in without it. The first account registered becomes the admin.

## Stack

| Layer    | Choice                                                             |
| -------- | ------------------------------------------------------------------ |
| Hosting  | [FastAPI Cloud](https://fastapicloud.com)                          |
| Backend  | FastAPI, Jinja2 templates, HTMX fragments                          |
| Database | PostgreSQL (SQLAlchemy 2.0 + Alembic migrations), Supabase in prod |
| Auth     | Email + password (argon2), signed session cookie                   |
| Movies   | OMDB API (`OMDB_API_KEY` env var)                                  |
| Styling  | Hand-rolled CSS — black / phosphor-green CRT lofi cinema theme     |

## Local development

Requires Python 3.13+ ([uv](https://docs.astral.sh/uv/)), Docker, and an OMDB API key.

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
  main.py            FastAPI app, static files, error pages
  config.py          pydantic-settings (.env)
  database.py        engine/session
  models.py          User, Team, Cycle, Submission, Ranking, …
  security.py        password hashing + session cookies
  dependencies.py    auth guards
  services/
    omdb.py          OMDB search/detail client
    scoring.py       Borda tally + winner/loser resolution
  routers/
    auth.py          register/login/logout
    teams.py         team creation + invite-code joining
    movies.py        search + submission management
    cycles.py        dashboard, phase transitions, leaderboard, skip/back
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
uv run fastapi cloud deploy                       # deploy to FastAPI Cloud
```

## Deployment (FastAPI Cloud + Supabase)

The app is deployed on [FastAPI Cloud](https://fastapicloud.com) at
**<https://movieclub.fastapicloud.dev>**, with the database on Supabase Postgres
(app auth stays as-is; Supabase is used purely as the Postgres host).

Current setup, for reference:

1. **App** — `movieclub` on FastAPI Cloud, linked to this repo via `.fastapicloud/cloud.json`.
   The entrypoint is declared in `pyproject.toml`
   (`[tool.fastapi] entrypoint = "app.main:app"`).
2. **Supabase ↔ FastAPI Cloud** — connected via dashboard integrations; FastAPI Cloud
   injects a `DATABASE_URL` secret. The app normalizes it itself
   (`postgresql://` → `postgresql+psycopg://`, adds `sslmode=require`).
3. **Env vars** — `SECRET_KEY` and `OMDB_API_KEY` are set via
   `fastapi cloud env set`.
4. **Migrations** — never run automatically on deploy; apply manually:
   ```bash
   DATABASE_URL="postgresql+psycopg://...supabase..." uv run alembic upgrade head
   ```
   (The URL lives only in the FastAPI Cloud dashboard/env secrets.)
5. **Deploying an update**:
   ```bash
   uv run fastapi cloud deploy
   ```

Remember: when adding columns, migrate **before** deploying; when removing them, deploy first and migrate after (zero-downtime gradual deployments mean old and new code run side by side).

### Deployed: admin skip / back

Admin shortcuts (**skip to next stage** and **go back**) are now live on the dashboard. No schema changes — just the new `skip` and `back` routes in `cycles.py`.
