# ROADMAP.md

From "runs on Lucas's laptop" to "my friends use it" — cheapest path first,
each step is a complete stopping point. No step requires more than the last.

## Current state

- **Live at <https://movieclub.fastapicloud.dev>** on FastAPI Cloud + Supabase Postgres
- Server-rendered FastAPI + Jinja/HTMX; auth via argon2 + signed cookie
- **Teams**: one cycle per team per month, creator-run phases, invite-code-only joining
- `/vote` page: members rank locked films; pending picks stay hidden until finalized
- Postgres in `docker-compose.yml` for local dev; migrations via Alembic
- Next up: push the current batch of changes (`/vote`, locking, ballot polish) to FastAPI Cloud — schema unchanged, so `uv run fastapi cloud deploy` with no migration step
- Not done yet: backups, monitoring, CI deploys

---

## Phase 0 — Launch: FastAPI Cloud + Supabase ✅ done

The app and database split across two free-tier-friendly services. No servers to manage.

1. **Database — Supabase**
   - [x] Create a Supabase project (us-east or EU region, your call)
   - [x] In FastAPI Cloud: Team settings → Integrations → connect Supabase;
         then on the app's Integrations tab pick the project + DB password.
         FastAPI Cloud injects `DATABASE_URL` automatically — the app normalizes
         scheme + `sslmode=require` itself (`app/config.py`).
2. **Secrets — FastAPI Cloud env**
   - [x] `SECRET_KEY` set via `fastapi cloud env set`
   - [x] `OMDB_API_KEY` set via `fastapi cloud env set`
3. **Migrate before first deploy** (migrations do NOT run on deploy):
   - [x] All migrations applied against the Supabase DB
4. **Deploy**:
   - [x] Live at **<https://movieclub.fastapicloud.dev>**
5. **Bootstrap the club**
   - [x] Register yourself → you're global admin → create the team
   - [x] Share the invite code from `/team` — nobody else can get in without it

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

- [ ] `uv run fastapi setup-ci` — deploy on merge to main via GitHub Actions
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
