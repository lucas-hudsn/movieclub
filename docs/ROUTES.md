# Routes

All routes are defined in `app/routers/`. The app returns HTML (full pages or HTMX fragments), not JSON.

## Auth (`app/routers/auth.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/register` | Registration form |
| POST | `/register` | Create account (first user becomes admin) |
| GET | `/login` | Login form |
| POST | `/login` | Authenticate and set session cookie |
| POST | `/logout` | Clear session cookie |

## Teams (`app/routers/teams.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/teams/onboard` | Onboarding page (create or join a team) |
| POST | `/teams` | Create a new team (user becomes owner) |
| POST | `/teams/join` | Join a team via invite code |
| GET | `/team` | Team settings page (members, invite code) |
| POST | `/team/invite/regenerate` | Generate a new invite code (admin only) |
| POST | `/team/members/{id}/remove` | Remove a member from the team (admin only) |

## Movies (`app/routers/movies.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/partials/search?q=...` | HTMX: search OMDB and return results fragment |
| POST | `/cycles/{id}/submissions` | Submit a movie for the current cycle |
| POST | `/submissions/{id}/lock` | Lock in your submission (prevent changes) |
| POST | `/submissions/{id}/delete` | Remove your unlocked submission |

## Cycles & Dashboard (`app/routers/cycles.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard — current cycle, submissions, leaderboard |
| GET | `/admin/actions` | Admin control panel (all cycles, leaderboard, win adjustment) |
| GET | `/leaderboard` | Public all-time leaderboard |

### Admin cycle controls

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/cycles/{id}/lock-submissions` | Lock submissions (requires min submissions) |
| POST | `/admin/cycles/{id}/unlock-submissions` | Unlock submissions |
| POST | `/admin/cycles/{id}/open-ranking` | Start ranking phase |
| POST | `/admin/cycles/{id}/reopen-submissions` | Reopen submissions (clears all votes) |
| POST | `/admin/cycles/{id}/close` | Close month, crown winner |
| POST | `/admin/cycles/{id}/skip` | Skip to next stage |
| POST | `/admin/cycles/{id}/back` | Revert to previous stage |

### Admin ban & win controls

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/cycles/{id}/toggle-ban/{user_id}` | Toggle ban for a user in a cycle |
| POST | `/admin/wins/{user_id}?delta=N` | Adjust a user's win count (+1 or -1) |

## Rankings (`app/routers/rankings.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vote` | Vote page — shows ballot and results for current cycle |
| GET | `/cycles/{id}/ranking` | HTMX: get ballot fragment |
| POST | `/cycles/{id}/ranking/{submission_id}/move?dir=up\|down` | HTMX: move a film up or down in your ballot |
| POST | `/cycles/{id}/submit-ballot` | Submit your final ballot |
| POST | `/cycles/{id}/abstain` | Mark yourself as abstaining (inactive ballot) |

## Static

| Method | Path | Description |
|--------|------|-------------|
| GET | `/static/*` | CSS and static assets |
