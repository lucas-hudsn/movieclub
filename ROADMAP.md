# ROADMAP.md

From "runs on Lucas's laptop" to "my friends use it" — cheapest path first,
each step is a complete stopping point. No step requires more than the last.

## Current state (updated 2026-08-25)

- Server-rendered FastAPI + Jinja/HTMX; auth via argon2 + signed cookie
- **Teams**: one cycle per team per month, creator-run phases, invite-code-only joining
- Postgres in `docker-compose.yml` for local dev; migrations via Alembic
- Deployment target chosen: **FastAPI Cloud** (app) + **Supabase** (Postgres) + **GitHub Pages** (landing site)
- **Deployed**: first successful deploy is live at https://movieclub.fastapicloud.dev
  - App `movieclub` exists on FastAPI Cloud and is linked locally (`.fastapicloud/cloud.json`)
  - Entrypoint declared in `pyproject.toml` (`[tool.fastapi] entrypoint = "app.main:app"`)
  - Env vars already set on the app: `DATABASE_URL` (secret), `SECRET_KEY` (secret), `OMDB_API_KEY`
  - Gotcha fixed during first deploy: the app's `directory` setting pointed at `src/`
    but the repo root holds `pyproject.toml` → build failed with
    "Installing Python interpreter … os error 2"; fixed with
    `fastapi cloud apps update --directory .`
- Not done yet: migrations against the cloud DB, admin bootstrap, backups, monitoring

---

## Phase 0 — Launch: FastAPI Cloud + Supabase (mostly done)

The app and database split across two free-tier-friendly services. No servers to manage.

1. **Database — Supabase**
   - [x] Create a Supabase project (us-east or EU region, your call)
   - [x] `DATABASE_URL` is set on the FastAPI Cloud app (verify it's the Supabase
         pooled URL — check dashboard → app → env/integrations)
         FastAPI Cloud injects `DATABASE_URL`; the app normalizes
         scheme + `sslmode=require` itself (`app/config.py`).
2. **Secrets — FastAPI Cloud env**
   - [x] `SECRET_KEY` set (secret)
   - [x] `OMDB_API_KEY` set
3. **Deploy**
   - [x] App created + linked: `fastapi cloud apps link --app-id 546b9f03-…`
   - [x] Entrypoint in `pyproject.toml`: `[tool.fastapi] entrypoint = "app.main:app"`
   - [x] First deploy succeeded (`uv run fastapi cloud deploy`); `/login` renders.
         If a build fails with "Installing Python interpreter … os error 2",
         re-check the app's directory setting (`fastapi cloud apps get`) —
         it must point at the folder containing `pyproject.toml` (`.` here).
4. **Migrate the cloud DB** (migrations do NOT run on deploy) — *next up*:
   ```bash
   DATABASE_URL="<supabase pooled url>" uv run alembic upgrade head
   ```
   The URL is only in the FastAPI Cloud dashboard/env secrets — fetch it from there.
5. **Bootstrap the club** — *after migrating*:
   - [ ] Register yourself → you're global admin → create the team
   - [ ] Share the invite code from `/team` — nobody else can get in without it

**Total: $0 until friends actually use it.** Stop here; the club is live.

## Phase 1 — Landing site on GitHub Pages

A static "what is this" page with a join link — keeps the app URL out of chat threads,
and gives the repo a public front door without exposing anything dynamic.

1. [ ] Add a single-file `docs/index.html` (no build step, reuse the CRT theme vibe):
      one-liner pitch, how a cycle works, **join** button → FastAPI Cloud app URL.
2. [ ] Repo Settings → Pages → deploy from `main` / `docs` folder (or a small
      `deploy-pages.yml` GitHub Action for more control).
3. [ ] Optional: custom domain on Pages + redirect `movieclub.<domain>` (app) vs
      `<domain>` (landing). FastAPI Cloud supports custom domains in dashboard settings.

## Phase 2 — CI & zero-downtime discipline (after the first real deploy)

- [ ] `uv run fastapi cloud setup-ci` — deploy on merge to main via GitHub Actions
- [ ] Migration rule of thumb baked into habits: **add columns → migrate before
      deploy; remove columns → deploy before migrating** (gradual deployments mean
      old and new code run side by side)
- [ ] Add `.fastapicloudignore` if upload size ever matters (tests, `.pgdata`)
- [ ] Skim Logs/Metrics tabs in the FastAPI Cloud dashboard after each cycle close

## Phase 3 — Backups & hardening (once the club has history worth keeping)

- [ ] **Backups** — non-negotiable once wins/losses are treasured:
  - Supabase daily backups (paid plans) or a scheduled GitHub Action running
    `pg_dump` against the Supabase pooler into a private repo/artifact
  - Weekly offsite copy (rclone to B2/GDrive) — pennies/month
- [ ] Restore drill: actually restore one backup into a scratch Supabase project once
- [ ] Rotate `SECRET_KEY` procedure documented (it invalidates all sessions — fine,
      everyone just logs in again)
- [ ] Rate-limit login attempts only if logs show bots poking at it

## Phase 4 — Only if it grows (probably never)

Feature ideas from actual usage:

- Deadline auto-transitions instead of creator clicks (cron or startup hook)
- Email/Discord nudge when ranking opens
- Watch-list links (JustWatch) on submissions; per-cycle one-line reviews
- Multiple teams per user (schema is one-team-per-user by design today)
- Cross-team leaderboard if a second club shows up

## Explicitly not planned

- Kubernetes, message queues, Celery, Redis, a frontend framework — nothing here needs them.
- Self-hosted VPS/compose in prod — FastAPI Cloud + Supabase replaced that plan.
- Public open registration — joining requires an invite code from a team creator, period.
