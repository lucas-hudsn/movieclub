from sqlalchemy import select

from app.models import Cycle, CycleStatus, Ranking
from tests.conftest import register


def test_register_login_and_dashboard(client):
    r = register(client, "neo@matrix.io", "Neo")
    assert r.status_code == 303
    assert "movieclub_session" in r.cookies

    dash = client.get("/")
    assert dash.status_code == 200
    # month name rendered from period, e.g. "august 2026"
    import datetime

    now = datetime.date.today()
    month_names = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]
    expected = f"{month_names[now.month - 1]} {now.year}"
    assert expected in dash.text


def test_first_user_is_admin(client):
    register(client, "a@x.io")
    assert "lock submissions, start ranking" in client.get("/").text

    client.post("/logout")
    register(client, "b@x.io")
    assert "lock submissions, start ranking" not in client.get("/").text


def test_unauthenticated_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_search_selection_shows_preview(client, omdb_mock):
    register(client, "a@x.io")
    client.get("/")  # lazily create the current cycle

    # no selection: list only, no preview pane content
    resp = client.get("/partials/search", params={"q": "matrix"})
    assert resp.status_code == 200
    assert "The Matrix" in resp.text
    assert "select a film" in resp.text
    assert "search-hit selected" not in resp.text

    # selecting a hit highlights it and shows its details in the preview pane
    resp = client.get("/partials/search", params={"q": "matrix", "selected": "tt0133093"})
    assert resp.status_code == 200
    assert "search-hit selected" in resp.text
    assert "A hacker discovers reality is a simulation." in resp.text
    assert 'name="imdb_id" value="tt0133093"' in resp.text


def test_htmx_submission_redirects_via_hx_header(client, db, omdb_mock):
    register(client, "a@x.io")
    client.get("/")
    cycle = db.scalars(select(Cycle)).first()

    resp = client.post(
        f"/cycles/{cycle.id}/submissions",
        data={"imdb_id": "tt0133093"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 204
    assert resp.headers["hx-redirect"] == "/"

    # htmx errors render as flash fragment instead of raising
    resp = client.post(
        f"/cycles/{cycle.id}/submissions",
        data={"imdb_id": "tt0133093"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "you already submitted" in resp.text


def test_full_cycle_flow(client, db, omdb_mock):
    # Admin registers first (becomes admin); dashboard lazily creates the current cycle
    register(client, "admin@x.io", "Admin")
    assert client.get("/").status_code == 200
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"}).status_code == 303
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt1375666"}).status_code == 400  # one per user

    # Member registers (takes over cookie), submits Pulp Fiction
    register(client, "member@x.io", "Member")
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0110912"}).status_code == 303
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"}).status_code == 400  # dupe movie

    # Member cannot run admin actions
    assert client.post(f"/admin/cycles/{cid}/open-ranking").status_code == 403

    # Back to admin
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    assert client.post(f"/admin/cycles/{cid}/open-ranking").status_code == 303
    db.refresh(cycle)
    assert cycle.status == CycleStatus.ranking

    rankings = db.scalars(select(Ranking)).all()
    assert len(rankings) == 4  # 2 movies x 2 users

    # Admin actively votes: push their #1 down
    target = db.scalars(
        select(Ranking).where(Ranking.cycle_id == cid, Ranking.user_id == 1, Ranking.position == 1)
    ).first()
    resp = client.post(f"/cycles/{cid}/ranking/{target.submission_id}/move?dir=down")
    assert resp.status_code == 200
    assert "rank-list" in resp.text

    # Close & crown
    assert client.post(f"/admin/cycles/{cid}/close").status_code == 303
    db.refresh(cycle)
    assert cycle.status == CycleStatus.closed
    assert cycle.winner_submission_id is not None

    cycles = db.scalars(select(Cycle).order_by(Cycle.period)).all()
    assert len(cycles) == 2
    next_cycle = cycles[-1]

    from app.models import Submission
    loser_sub = db.get(Submission, cycle.loser_submission_id)
    assert next_cycle.banned_user_id == loser_sub.user_id

    # Loser cannot submit in the new cycle
    client.post("/logout")
    loser_email = "admin@x.io" if loser_sub.user_id == 1 else "member@x.io"
    client.post("/login", data={"email": loser_email, "password": "hunter2222"})
    resp = client.post(f"/cycles/{next_cycle.id}/submissions", data={"imdb_id": "tt1375666"})
    assert resp.status_code == 403

    lb = client.get("/leaderboard")
    assert lb.status_code == 200
