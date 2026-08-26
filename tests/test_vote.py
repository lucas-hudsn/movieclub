from sqlalchemy import select

from app.models import Cycle, CycleStatus, Ranking, Submission
from tests.conftest import create_team, join_team, register, team_invite_code


def _setup_two_members(client, db):
    register(client, "admin@x.io", "Admin")
    create_team(client)
    client.get("/")
    code = team_invite_code(db)
    register(client, "member@x.io", "Member")
    join_team(client, code)


def _lock_pick(client, db, cycle_id, imdb_id):
    """Submit + lock in as whoever is logged in; returns the Submission."""
    assert client.post(f"/cycles/{cycle_id}/submissions", data={"imdb_id": imdb_id}).status_code == 303
    sub = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle_id, Submission.imdb_id == imdb_id)
    ).first()
    assert client.post(f"/submissions/{sub.id}/lock").status_code == 303
    return sub


def test_vote_page_available_before_ranking_opens(client, db, omdb_mock):
    _setup_two_members(client, db)

    # admin submits and locks in The Matrix
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id
    sub_matrix = _lock_pick(client, db, cid, "tt0133093")

    # member has an unlocked pick: votable list must exclude it
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    assert client.post(f"/cycles/{cid}/submissions", data={"imdb_id": "tt0110912"}).status_code == 303

    page = client.get("/vote")
    assert page.status_code == 200
    assert "The Matrix" in page.text
    assert "Pulp Fiction" not in page.text
    assert 'href="/vote"' in page.text  # nav link

    # member locks their own pick too, then votes before any admin opens ranking
    pulp = db.scalars(
        select(Submission).where(Submission.cycle_id == cid, Submission.imdb_id == "tt0110912")
    ).first()
    assert client.post(f"/submissions/{pulp.id}/lock").status_code == 303
    matrix_row = db.scalars(
        select(Ranking).where(
            Ranking.cycle_id == cid,
            Ranking.user_id == 2,
            Ranking.submission_id == sub_matrix.id,
        )
    ).first()
    resp = client.post(f"/cycles/{cid}/ranking/{matrix_row.submission_id}/move?dir=down")
    assert resp.status_code == 200
    db.refresh(matrix_row)
    # reordering alone does not count as a vote — ballot stays inactive
    assert matrix_row.ballot_active is False

    resp = client.post(f"/cycles/{cid}/submit-ballot")
    assert resp.status_code == 200
    assert "submitted" in resp.text
    db.refresh(matrix_row)
    assert matrix_row.ballot_active is True


def test_ballot_grows_as_films_lock_in(client, db, omdb_mock):
    _setup_two_members(client, db)
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id

    sub_a = _lock_pick(client, db, cid, "tt0133093")
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    page = client.get("/vote")
    assert "The Matrix" in page.text

    # second film locks in later: it joins the ballot at the bottom
    sub_b = _lock_pick(client, db, cid, "tt0110912")
    page = client.get("/vote")
    assert "Pulp Fiction" in page.text
    positions = {
        r.submission_id: r.position
        for r in db.scalars(select(Ranking).where(Ranking.cycle_id == cid, Ranking.user_id == 2))
    }
    assert positions[sub_a.id] < positions[sub_b.id]


def test_abstain_from_vote_page(client, db, omdb_mock):
    _setup_two_members(client, db)
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id
    _lock_pick(client, db, cid, "tt0133093")
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    _lock_pick(client, db, cid, "tt0110912")

    client.get("/vote")  # materializes default rows
    rows = db.scalars(select(Ranking).where(Ranking.user_id == 2)).all()
    assert len(rows) == 2

    resp = client.post(f"/cycles/{cid}/abstain")
    assert resp.status_code == 200
    assert "abstained" in resp.text
    assert all(not r.ballot_active for r in db.scalars(select(Ranking).where(Ranking.user_id == 2)))


def test_vote_blocked_after_close(client, db, omdb_mock):
    _setup_two_members(client, db)
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})
    cycle = db.scalars(select(Cycle)).first()
    cid = cycle.id
    _lock_pick(client, db, cid, "tt0133093")
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    _lock_pick(client, db, cid, "tt0110912")
    client.post("/login", data={"email": "admin@x.io", "password": "hunter2222"})

    assert client.post(f"/admin/cycles/{cid}/open-ranking").status_code == 303
    assert client.post(f"/admin/cycles/{cid}/close").status_code == 303
    db.refresh(cycle)
    assert cycle.status == CycleStatus.closed

    # closing auto-creates next month's cycle, so /vote now shows the fresh one
    cycles = db.scalars(select(Cycle).order_by(Cycle.period)).all()
    assert len(cycles) == 2
    page = client.get("/vote")
    assert "nothing to vote on yet" in page.text

    # ...but the closed cycle's ballot can no longer be touched
    target = db.scalars(select(Ranking).where(Ranking.cycle_id == cid)).first()
    assert client.post(f"/cycles/{cid}/ranking/{target.submission_id}/move?dir=up").status_code == 400
    resp = client.post(
        f"/cycles/{cid}/ranking/{target.submission_id}/move?dir=up",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "voting is over" in resp.text
