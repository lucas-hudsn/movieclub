from sqlalchemy import func, select

from app.models import Cycle, CycleStatus, Ranking
from tests.conftest import create_team, join_team, register, team_invite_code


def test_register_login_and_dashboard(client):
    r = register(client, "neo@matrix.io", "Neo")
    assert r.status_code == 303
    assert "movieclub_session" in r.cookies

    # no team yet: dashboard sends you to onboarding
    assert client.get("/").headers["location"] == "/teams/onboard"

    assert create_team(client).status_code == 303
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
    create_team(client)
    assert "lock submissions, start ranking" in client.get("/").text

    client.post("/logout")
    register(client, "b@x.io")
    assert client.get("/").headers["location"] == "/teams/onboard"


def test_unauthenticated_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_search_selection_shows_preview(client, omdb_mock):
    register(client, "a@x.io")
    create_team(client)
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
    create_team(client)
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


def test_remove_and_lock_in_submission(client, db, omdb_mock):
    from app.models import Submission

    register(client, "admin@x.io", "Admin")
    create_team(client)
    client.get("/")
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id

    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"}).status_code == 303
    sub = db.scalars(select(Submission)).first()

    # a member joins but hasn't picked yet; admin's pick is unlocked, so removable
    code = team_invite_code(db)
    register(client, "member@x.io", "Member")
    join_team(client, code)

    # member cannot remove someone else's submission
    assert client.post(f"/submissions/{sub.id}/delete").status_code == 404

    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    resp = client.post(f"/submissions/{sub.id}/delete", headers={"HX-Request": "true"})
    assert resp.status_code == 204
    assert resp.headers["hx-redirect"] == "/"
    assert db.scalars(select(Submission)).first() is None

    # re-pick and lock in: removal blocked even though others haven't picked
    client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"})
    sub = db.scalars(select(Submission).where(Submission.user_id == 1)).first()
    assert client.post(f"/submissions/{sub.id}/lock").status_code == 303
    resp = client.post(
        f"/submissions/{sub.id}/delete",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "locked in" in resp.text
    assert db.get(Submission, sub.id) is not None

    # locking again is rejected
    resp = client.post(f"/submissions/{sub.id}/lock", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "already locked in" in resp.text

    # once ranking opens, everything stays blocked
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0110912"})
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    assert client.post(f"/admin/cycles/{cid}/open-ranking").status_code == 303
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    member_sub = db.scalars(select(Submission).where(Submission.user_id == 2)).first()
    assert client.post(f"/submissions/{member_sub.id}/delete").status_code == 400
    assert client.post(f"/submissions/{member_sub.id}/lock").status_code == 400


def test_team_page_shows_banner_but_no_pick_controls(client, db, omdb_mock):
    from app.models import Submission

    register(client, "admin@x.io", "Admin")
    create_team(client)
    client.get("/")
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id

    code = team_invite_code(db)
    register(client, "member@x.io", "Member")
    join_team(client, code)
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"}).status_code == 303
    sub = db.scalars(select(Submission).where(Submission.user_id == 1)).first()

    # banner shows on the team page, but pick/lock/remove controls live only on the cycle page
    team_page = client.get("/team").text
    assert "month-badge" in team_page
    assert "remove my film" not in team_page
    assert "/lock" not in team_page
    cycle_page = client.get("/").text
    assert "remove my film" in cycle_page

    # locked in: still nothing on the team page
    assert client.post(f"/submissions/{sub.id}/lock").status_code == 303
    team_page = client.get("/team").text
    assert "locked in" not in team_page


def test_full_cycle_flow(client, db, omdb_mock):
    # Admin registers first (becomes admin), creates the team; dashboard lazily creates the current cycle
    register(client, "admin@x.io", "Admin")
    create_team(client)
    assert client.get("/").status_code == 200
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0133093"}).status_code == 303
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt1375666"}).status_code == 400  # one per user

    # Member registers and joins via invite code, submits Pulp Fiction
    code = team_invite_code(db)
    register(client, "member@x.io", "Member")
    assert join_team(client, code).status_code == 303
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

    # 2-member team: everyone stays in, nobody is banned
    db.refresh(next_cycle)
    assert next_cycle.banned_users == []
    assert cycle.loser_submission_id is None

    # so members can still submit in the new cycle
    client.post("/logout")
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    resp = client.post(f"/cycles/{next_cycle.id}/submissions", data={"imdb_id": "tt1375666"})
    assert resp.status_code == 303

    lb = client.get("/leaderboard")
    assert lb.status_code == 200


def test_team_join_capped_at_six(client, db):
    from app.models import User

    register(client, "admin@x.io", "Admin")
    create_team(client)
    code = team_invite_code(db)

    for i in range(5):  # fills the team up to 6 members
        email = f"m{i}@x.io"
        register(client, email)
        assert join_team(client, code).status_code == 303

    member_count = db.scalar(select(func.count()).select_from(User))
    assert member_count == 6

    # 7th user gets bounced
    register(client, "late@x.io", "Late")
    resp = join_team(client, code)
    assert resp.status_code == 200
    assert "capped at 6" in resp.text
    late = db.scalar(select(User).where(User.email == "late@x.io"))
    assert late.team_id is None
