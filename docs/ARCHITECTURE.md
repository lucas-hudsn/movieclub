# Architecture

## Overview

Movie Club is a server-rendered web app. There is no SPA, no REST API — routes return either full HTML pages or HTMX fragments. The browser drives all state transitions.

```
Browser → Router (app/routers/) → SQLAlchemy models → Template or redirect
```

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI + Jinja2 templates + HTMX fragments |
| Database | PostgreSQL (SQLAlchemy 2.0 + Alembic migrations) |
| Auth | Email + password (argon2), signed session cookie |
| Movies | OMDB API via httpx |
| Styling | Hand-rolled CSS — CRT phosphor-green theme |

## Key patterns

### HTMX partials

Interactive bits (search results, rankings, submission previews) live in `templates/partials/` and are swapped in by HTMX. Pages extend `base.html`; partials do not.

Example flow:
1. User types in search box
2. HTMX GETs `/partials/search?q=...`
3. Server returns `partials/search_results.html` fragment
4. HTMX swaps it into `#search-results`

### Auth guards

All auth lives in `app/dependencies.py`:

- `get_current_user` — reads the signed session cookie, raises 303 redirect to `/login` if missing/invalid
- `require_admin` — additionally checks `user.is_admin`
- `is_team_admin(user, team)` — checks if user is the team creator or a global admin

The session cookie (`movieclub_session`) is a signed token containing the user ID, created with `itsdangerous.URLSafeSerializer`.

### Cycle lifecycle

```
submitting → ranking → closed → (auto-creates next month)
```

Admins can go backwards at any point. The full state machine:

| From | To | Trigger |
|------|----|---------|
| submitting | ranking | Admin locks submissions + starts ranking (or skips) |
| ranking | submitting | Admin reopens submissions |
| ranking | closed | Admin closes month (or skips) |
| closed | ranking | Admin goes back |

### Scoring

Points are awarded by **Borda count** in `app/services/scoring.py`:

- N films ranked 1..N
- Position 1 gets N-1 points, position 2 gets N-2, ..., position N gets 0
- Ties broken by: fewest first-place ranks, then earliest submission time
- Inactive ballots (`ballot_active=False`) are ignored — users who never interact keep default order

### Eviction

When a cycle closes, the losing submitter(s) are banned from submitting next month:

| Team size | Evictions |
|-----------|-----------|
| 1-4 | 0 (everyone stays) |
| 5 | 1 |
| 6 | 2 |

Evictions are stored in the `cycle_bans` junction table.

### Win tracking

Wins are stored directly on the `User.wins` column. They are incremented:
- Automatically when a cycle closes (winner gets +1)
- Manually by admins via the +1/-1 buttons on the leaderboard

When a cycle is reverted from closed to ranking, the winner's `wins` column is decremented.

## File structure

```
app/
  main.py              App factory, static files, error handlers
  config.py            Pydantic-settings loading from .env
  database.py          SQLAlchemy engine + session factory
  models.py            ORM models (User, Team, Cycle, Submission, Ranking)
  security.py          Password hashing + session tokens
  dependencies.py      FastAPI dependency-injection guards
  templating.py        Jinja2 environment setup
  services/
    omdb.py            OMDB API client (search + detail)
    scoring.py         Borda tally + cycle close logic
  routers/
    auth.py            Register / login / logout
    teams.py           Create team / join via invite code
    movies.py          OMDB search + submission CRUD
    cycles.py          Dashboard, admin actions, leaderboard
    rankings.py        Ballot ordering (HTMX)
  templates/           Jinja2 pages + partials
  static/css/          Theme CSS
alembic/               Database migrations
tests/                 Pytest test suite
docs/                  This documentation
```
