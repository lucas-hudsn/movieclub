# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Commands

```bash
uv run pytest                          # test suite (in-memory SQLite, no services needed)
uv run alembic upgrade head            # apply migrations
uv run alembic revision --autogenerate -m "msg"   # create migration after model edits
docker compose up -d db                # start Postgres on localhost:5433
uv run uvicorn app.main:app --port 8100           # dev server (port 8000 is occupied locally)
```

- Package manager is **uv** — add deps with `uv add`, never edit `pyproject.toml` versions by hand.
- Python **3.14**. Annotations are lazy (PEP 649): a missing import used only in a signature will *not* fail at def-time; it surfaces later as a 422/500 with `ForwardRef(...)` errors. If an endpoint suddenly treats a param as a query param, check the imports first.

## Architecture

Server-rendered FastAPI + Jinja2 + HTMX. There is no SPA, no REST API to speak of — routes return either full pages or HTML fragments.

- **Flow of control:** browser → router (`app/routers/`) → SQLAlchemy models (`app/models.py`) → template or redirect.
- **Auth:** signed cookie (`movieclub_session`) via `itsdangerous`; guards live in `app/dependencies.py`. Unauthenticated requests raise `HTTPException(303, Location=/login)`, converted to redirects in `app/main.py`.
- **Cycle lifecycle:** `submitting → ranking → closed` (`CycleStatus`). Only admins advance phases (`/admin/cycles/{id}/open-ranking|close`). Closing tallies Borda points (`app/services/scoring.py`), records winner/loser, and auto-creates next month's cycle with the loser's submitter banned from submitting.
- **OMDB:** all external calls go through `app/services/omdb.py`. Never call httpx elsewhere. Results are cached onto the `Submission` row at creation time.
- **Rankings:** one `Ranking` row per (cycle, user, submission). Ballots are only tallied when `ballot_active=True` (set when the user moves anything); abstainers keep inactive default-order rows.

## Conventions

- Templates: pages extend `base.html`; interactive bits are partials in `templates/partials/` swapped by HTMX (`hx-target="#ballot"`, `#search-results`). Keep that pattern for new interactivity.
- Styling: single file `app/static/css/theme.css`, CSS variables at top (`--green`, `--panel`, ...). No CSS frameworks, no JS beyond HTMX.
- DB access: synchronous SQLAlchemy 2.0 style (`Mapped[...]`, `select()`), sessions via `Depends(get_db)`.
- Tests: `tests/conftest.py` sets env vars *before* importing app modules and overrides `get_db`. Reuse its fixtures (`client`, `db`, `omdb_mock`) rather than hitting real OMDB.
- Secrets: `.env` is gitignored and may contain the user's real API key — never read, print, or commit it.

## Gotchas

- Postgres runs on port **5433** (host already has something on 5432).
- The first registered user becomes admin — don't create throwaway users against the dev database casually.
- After editing models, always generate + apply a migration before testing against Postgres.
