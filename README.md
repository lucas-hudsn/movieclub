# MOVIE CLUB

**Live: <https://movieclub.fastapicloud.dev>**

A monthly movie club app for teams: everyone submits a film, everyone watches and ranks,
the club crowns a monthly winner, and the loser's pick earns their submitter a month
on the bench.

![stack](https://img.shields.io/badge/FastAPI-Jinja2%20%2B%20HTMX-00ff41)

## How a cycle works

1. **SUBMITTING** — each member picks one movie (searched live against [OMDB](https://www.omdbapi.com/)). One pick per person, no duplicate movies. An admin must **lock submissions** (requires the minimum submissions: min of 4 and team size) before ranking can start.
2. **RANKING** — an admin starts ranking after locking. Every member orders all locked films best → worst with ▲▼ controls on the `/vote` page. Points are awarded by **Borda count**: position 1 of N films gets `N−1` points, last gets `0`. Members can abstain (inactive ballots aren't tallied). Admins can **reopen submissions** to return to the submitting phase (clears all votes), or **go back** from a closed cycle to reopen it for ranking.
3. **CLOSED** — the film with the most points wins; the film with the fewest points sends its submitter to the bench: they can still watch and rank next month, but cannot submit. A new cycle starts automatically.

**Admin shortcuts:** at any point an admin can **skip to the next stage** (force-open ranking without the minimum-submission gate, or force-close and tally even with partial voting) and **go back** (revert ranking → submitting, or closed → ranking). Useful when members are lagging or a mistake was made.

An all-time **leaderboard** tracks wins per member. Admins can manually adjust win counts with +1/-1 buttons on the admin actions page.

Joining is invite-only: the team creator shares a code from `/team`, and nobody gets in without it. The first account registered becomes the admin.

## Quick start

```bash
# 1. Start Postgres (port 5433)
docker compose up -d db

# 2. Configure secrets
cp .env.example .env        # then fill in OMDB_API_KEY and SECRET_KEY

# 3. Apply migrations
uv run alembic upgrade head

# 4. Run
uv run uvicorn app.main:app --port 8100
```

Open <http://localhost:8100> — **the first account registered becomes the admin.**

## Running tests

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
  models.py          User, Team, Cycle, Submission, Ranking
  security.py        password hashing + session cookies
  dependencies.py    auth guards
  templating.py      Jinja2 loader
  services/
    omdb.py          OMDB search/detail client
    scoring.py       Borda tally + winner/loser resolution
  routers/
    auth.py          register/login/logout
    teams.py         team creation + invite-code joining
    movies.py        search + submission management
    cycles.py        dashboard, phase transitions, admin actions, leaderboard
    rankings.py      ballot ordering (HTMX)
  templates/         Jinja2 pages + HTMX partials
  static/css/        CRT lofi cinema theme
alembic/             migrations
tests/
docs/                project documentation
```

## Useful commands

```bash
uv run alembic revision --autogenerate -m "..."   # new migration after model changes
uv run alembic upgrade head                       # apply migrations
uv run pytest                                     # test suite
docker compose up -d db                           # start database
uv run fastapi cloud deploy                       # deploy to FastAPI Cloud
```

## Documentation

Detailed docs live in the [`docs/`](docs/) folder:

- [Setup guide](docs/SETUP.md) — local development prerequisites and configuration
- [Architecture](docs/ARCHITECTURE.md) — how the codebase is structured
- [Routes](docs/ROUTES.md) — all endpoints and their behavior
- [Database](docs/DATABASE.md) — schema, models, and migrations
- [Deployment](docs/DEPLOYMENT.md) — FastAPI Cloud + Supabase production setup
