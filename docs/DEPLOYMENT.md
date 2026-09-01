# Deployment

The app is deployed on [FastAPI Cloud](https://fastapicloud.com) with a Supabase Postgres database.

**Production URL:** https://movieclub.fastapicloud.dev

## Architecture

```
FastAPI Cloud (app)  ←→  Supabase Postgres (database)
       ↑
   GitHub repo (auto-deploys on push)
```

- **App**: `movieclub` on FastAPI Cloud, linked to this repo
- **Database**: Supabase Postgres (connected via dashboard integration)
- **Secrets**: `SECRET_KEY` and `OMDB_API_KEY` set via `fastapi cloud env set`
- **Entrypoint**: declared in `pyproject.toml` as `app.main:app`

## Deploying

```bash
uv run fastapi cloud deploy
```

## Migrations in production

Migrations are **never** run automatically on deploy. Apply them manually:

```bash
DATABASE_URL="postgresql+psycopg://...supabase..." uv run alembic upgrade head
```

The production `DATABASE_URL` lives in the FastAPI Cloud dashboard env secrets.

### Migration strategy for zero-downtime deploys

Because FastAPI Cloud runs old and new code side by side during rolling deploys:

- **Adding a column**: migrate first, then deploy. Old code ignores the new column.
- **Removing a column**: deploy first (stop reading the column), then migrate to drop it.
- **Renaming a column**: add new, deploy, migrate data, deploy code using new column, then drop old.

## Environment variables

| Variable | Where to set | Description |
|----------|-------------|-------------|
| `DATABASE_URL` | FastAPI Cloud dashboard | Supabase connection string (auto-injected) |
| `SECRET_KEY` | `fastapi cloud env set` | Session cookie signing key |
| `OMDB_API_KEY` | `fastapi cloud env set` | OMDB API key |

## Health checks

The app exposes a basic health check. Supabase provides database health via its dashboard.

## Useful commands

```bash
# Check deployment status
uv run fastapi cloud status

# View logs
uv run fastapi cloud logs

# Set an env var
fastapi cloud env set SECRET_KEY=your-new-secret

# List env vars
fastapi cloud env list
```

## Rollback

If a deploy breaks:

1. Revert the commit in git
2. Run `uv run fastapi cloud deploy` again
3. If a migration needs reverting: `uv run alembic downgrade -1` (with the production DATABASE_URL)
