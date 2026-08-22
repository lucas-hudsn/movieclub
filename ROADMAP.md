# ROADMAP.md

From "runs on Lucas's laptop" to "my friends use it" — cheapest path first,
each step is a complete stopping point. No step requires more than the last.

## Current state

- App + Postgres in `docker-compose.yml`, migrations via Alembic
- Auth works, no rate limiting, dev-grade `SECRET_KEY` fallback
- No HTTPS, no backups, no deployment config

---

## Phase 0 — Free, today: share over Tailscale

Zero cost, zero infra. Good enough while the club is < 5 people.

1. Install [Tailscale](https://tailscale.com) on your Mac and on friends' devices (free plan covers 100 devices).
2. Run the app bound to your tailnet IP:
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8100
   ```
3. Friends visit `http://<your-tailscale-ip>:8100`.

**Caveats:** only online when your Mac is. Fine as a trial period.

## Phase 1 — ~€5/mo: single cheap VPS (the recommended end state)

One box, one `docker compose up -d`, done. Hetzner CX22 (~€4/mo) is the usual pick;
Netcup and OVH are similar. Skip Fly/Railway/Render — their "free" tiers died and
managed-Postgres add-ons cost more than this entire server.

### 1.1 Production compose file

Add `docker-compose.prod.yml` alongside the existing one:

- **app**: build from a small `Dockerfile` (`python:3.14-slim` + `uv sync --frozen --no-dev`)
- **db**: same postgres image, volume instead of `./.pgdata` bind mount
- **caddy**: [Caddy](https://caddyserver.com) front proxy — automatic Let's Encrypt TLS,
  two lines of config:
  ```
  movieclub.yourdomain.com {
      reverse_proxy app:8000
  }
  ```
  This replaces any nginx/certbot fiddling.

### 1.2 Server bootstrap

```bash
ssh root@vps
apt install docker.io docker-compose-plugin
adduser club && usermod -aG docker club
# copy repo + .env, then:
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
```

### 1.3 Before inviting people

- [ ] Generate a real `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- [ ] Set `DATABASE_URL` to the compose-internal db host, not localhost
- [ ] Domain (~$10/yr at Porkbun/Cloudflare) → A record to the VPS
- [ ] UFW firewall: allow 22/80/443 only; Postgres stays container-internal

**Total: ~€5/mo server + ~$1/mo domain.** Stop here unless it breaks.

## Phase 2 — Hardening (do after the first real month)

- [ ] **Backups** — non-negotiable once the club has history. Nightly cron on the VPS:
  ```bash
  docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U movieclub movieclub | gzip > backups/mc-$(date +%F).sql.gz
  ```
  plus a weekly offsite copy (rclone to Backblaze B2 — pennies/month).
- [ ] Restore drill: actually restore one backup into a scratch container once.
- [ ] Watch `docker compose logs` / enable basic `watchtower` for image updates, or just ssh in monthly.
- [ ] Rate-limit login attempts (slowapi or Caddy level) — low priority for a friends-only box.

## Phase 3 — Only if it grows (probably never)

Things worth doing if the club outgrows one VPS or you want nicer ops:

- Managed Postgres (Hetzner managed DB or Neon) with automated backups
- GitHub Actions: test → build image → push to GHCR → ssh deploy on merge to main
- Staging environment on the same box (second compose project, second port)
- Feature ideas from actual usage: deadline auto-transitions instead of admin clicks,
  email nudges when ranking opens, watch-list links (JustWatch) on submissions,
  per-cycle comments/reviews, tie-break rules UI

## Explicitly not planned

- Kubernetes, message queues, Celery, Redis, a frontend framework — nothing here needs them.
- Multiple clubs per instance — schema assumes one club; revisit only if another group asks.
