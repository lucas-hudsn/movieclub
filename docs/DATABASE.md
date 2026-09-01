# Database

## Connection

The app uses PostgreSQL in production and SQLite for tests. The connection string is configured via `DATABASE_URL` in `.env`.

The app automatically normalizes `postgresql://` and `postgres://` to `postgresql+psycopg://`, and appends `sslmode=require` for remote databases.

## Models

All models are in `app/models.py` using SQLAlchemy 2.0 mapped types.

### User

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | Auto-increment |
| `email` | string(255) | Unique, indexed |
| `name` | string(80) | Display name |
| `password_hash` | string(255) | argon2 hash |
| `is_admin` | boolean | First registered user is admin |
| `wins` | integer | All-time win count (auto + manual) |
| `team_id` | integer FK → teams | Nullable (null = no team yet) |
| `created_at` | timestamptz | Server default `now()` |

### Team

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | |
| `name` | string(80) | Team display name |
| `invite_code` | string(32) | Unique, indexed; 8-char random token |
| `created_by_id` | integer FK → users | The team owner/admin |
| `created_at` | timestamptz | |

### Cycle

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | |
| `team_id` | integer FK → teams | |
| `period` | string(7) | e.g. `"2026-08"`, unique per team |
| `status` | enum | `submitting` / `ranking` / `closed` |
| `winner_submission_id` | integer FK → submissions | Set when closed |
| `loser_submission_id` | integer FK → submissions | First loser (for eviction) |
| `submissions_locked` | boolean | Admin can lock to prevent edits |

Unique constraint: `(team_id, period)`.

### Submission

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | |
| `cycle_id` | integer FK → cycles | |
| `user_id` | integer FK → users | |
| `imdb_id` | string(20) | OMDB identifier |
| `title` | string(255) | Movie title |
| `year` | string(10) | Release year |
| `poster_url` | text | Nullable |
| `plot` | text | Nullable |
| `created_at` | timestamptz | |
| `locked_at` | timestamptz | Set when user locks their pick |

Unique constraints: one submission per user per cycle, one movie per cycle.

### Ranking

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer PK | |
| `cycle_id` | integer FK → cycles | |
| `user_id` | integer FK → users | |
| `submission_id` | integer FK → submissions | |
| `position` | integer | 1 = best |
| `ballot_active` | boolean | True only after user moves anything |

Unique constraint: `(cycle_id, user_id, submission_id)`.

### cycle_bans (junction table)

| Column | Type | Notes |
|--------|------|-------|
| `cycle_id` | integer FK → cycles | PK |
| `user_id` | integer FK → users | PK |

Links cycles to users who are banned from submitting in that cycle.

## Migrations

Managed by Alembic. Migrations live in `alembic/versions/`.

### Common commands

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Create a new migration after model changes
uv run alembic revision --autogenerate -m "description"

# Roll back one step
uv run alembic downgrade -1

# Show current revision
uv run alembic current

# Show migration history
uv run alembic history
```

### Migration conventions

- When **adding** a column: migrate first, then deploy (so old code can handle both schemas during rolling deploys).
- When **removing** a column: deploy first (stop reading the column), then migrate (drop it).
- Use `server_default` for new nullable columns to avoid backfilling on large tables.
- Backfill data in the migration itself when the column must be non-null.

## SQLite (tests)

Tests use an in-memory SQLite database (`sqlite://`). The `conftest.py` sets env vars before importing app modules and creates/drops all tables per test via `Base.metadata.create_all(engine)`.

Key differences from PostgreSQL:
- No `server_default` evaluation — defaults are handled by SQLAlchemy
- No `ON CONFLICT` upsert syntax
- `BOOLEAN` is stored as integer (0/1)
