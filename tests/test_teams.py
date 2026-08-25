import datetime

from sqlalchemy import select

from app.models import Cycle, User
from tests.conftest import create_team, join_team, register, team_invite_code


def test_join_with_bad_code_rejected(client, db):
    register(client, "a@x.io")
    resp = join_team(client, "wrong-code")
    assert resp.status_code == 200
    assert "match any team" in resp.text
    assert db.scalars(select(User)).first().team_id is None


def test_invite_only_joining(client, db):
    register(client, "owner@x.io", "Owner")
    create_team(client)
    code = team_invite_code(db)

    # second user joins via code
    register(client, "member@x.io", "Member")
    assert join_team(client, code).status_code == 303
    client.get("/")
    assert "my team" in client.get("/").text

    # a third user without the code stays teamless
    client.post("/logout")
    register(client, "outsider@x.io", "Outsider")
    assert client.get("/").headers["location"] == "/teams/onboard"
    outsider = db.scalars(select(User).where(User.email == "outsider@x.io")).first()
    assert outsider.team_id is None

    # joining twice is a no-op redirect
    assert join_team(client, code).status_code == 303


def test_non_owner_cannot_manage_cycle_or_team(client, db, omdb_mock):
    register(client, "owner@x.io", "Owner")
    create_team(client)
    client.get("/")  # lazily create the team's first cycle
    cycle = db.scalars(select(Cycle)).first()
    code = team_invite_code(db)

    register(client, "member@x.io", "Member")
    join_team(client, code)
    assert client.post(f"/admin/cycles/{cycle.id}/open-ranking").status_code == 403
    assert client.post(f"/admin/cycles/{cycle.id}/close").status_code == 403
    assert client.post("/team/members/1/remove").status_code == 403
    assert client.post("/team/invite/regenerate").status_code == 403


def test_owner_sees_invite_code_and_can_regenerate(client, db):
    register(client, "owner@x.io", "Owner")
    create_team(client)
    old_code = team_invite_code(db)

    page = client.get("/team")
    assert page.status_code == 200
    assert old_code in page.text
    assert "regenerate" in page.text.lower()

    assert client.post("/team/invite/regenerate").status_code == 303
    new_code = team_invite_code(db)
    assert new_code != old_code


def test_owner_can_remove_member(client, db):
    register(client, "owner@x.io", "Owner")
    create_team(client)
    code = team_invite_code(db)
    register(client, "member@x.io", "Member")
    join_team(client, code)

    member = db.scalars(select(User).where(User.email == "member@x.io")).first()
    client.post("/login", data={"email": "owner@x.io", "password": "hunter2222"})
    assert client.post(f"/team/members/{member.id}/remove").status_code == 303

    db.expire_all()
    assert member.team_id is None

    # removed member can rejoin with the same code while it's still valid
    client.post("/logout")
    client.post("/login", data={"email": "member@x.io", "password": "hunter2222"})
    assert join_team(client, code).status_code == 303


def test_teams_are_isolated(client, db, omdb_mock):
    register(client, "a@x.io", "A")
    create_team(client, "team a")
    client.get("/")  # lazily create the team's first cycle
    cycle_a = db.scalars(select(Cycle)).first()
    client.post(f"/cycles/{cycle_a.id}/submissions", data={"imdb_id": "tt0133093"})

    # team b's creator sees their own empty cycle and cannot touch team a's
    client.post("/logout")
    register(client, "b@x.io", "B")
    create_team(client, "team b")
    client.get("/")  # lazily create team b's first cycle
    cycles = db.scalars(select(Cycle).order_by(Cycle.id)).all()
    assert len(cycles) == 2
    cycle_b = cycles[-1]
    assert cycle_b.period == f"{datetime.date.today():%Y-%m}"
    assert client.post(f"/cycles/{cycle_a.id}/submissions", data={"imdb_id": "tt0110912"}).status_code == 400
    assert client.post(f"/admin/cycles/{cycle_a.id}/open-ranking").status_code == 404

    # closing team b's ranking phase needs 2+ movies; with one submission it refuses
    client.post(f"/cycles/{cycle_b.id}/submissions", data={"imdb_id": "tt1375666"})
    assert client.post(f"/admin/cycles/{cycle_b.id}/open-ranking").status_code == 400
