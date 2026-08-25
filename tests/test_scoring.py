from app.models import Cycle, CycleStatus, Ranking, Submission, Team, User
from app.services.scoring import close_cycle, eviction_count, tally


def _mk(db, n_users=3, tag=""):
    users = [
        User(email=f"u{i}{tag}@x.io", name=f"u{i}", password_hash="h")
        for i in range(n_users)
    ]
    db.add_all(users)
    db.flush()
    team = Team(name="crew", invite_code=f"code123{tag}", created_by_id=users[0].id)
    db.add(team)
    db.flush()
    for u in users:
        u.team_id = team.id
    cycle = Cycle(team_id=team.id, period="2026-01")
    db.add(cycle)
    db.commit()

    subs = [
        Submission(cycle_id=cycle.id, user_id=u.id, imdb_id=f"tt{i}", title=f"Film {i}", year="2020")
        for i, u in enumerate(users)
    ]
    db.add_all(subs)
    db.commit()
    return cycle, users, subs


def test_borda_tally_orders_correctly(db):
    cycle, users, subs = _mk(db)
    # u0 ranks: film0 best; u1 ranks: film1 best; u2 ranks film1 1st too
    ballots = [
        (users[0], [subs[0], subs[1], subs[2]]),
        (users[1], [subs[1], subs[2], subs[0]]),
        (users[2], [subs[1], subs[0], subs[2]]),
    ]
    for user, order in ballots:
        for pos, sub in enumerate(order, start=1):
            db.add(Ranking(cycle_id=cycle.id, user_id=user.id, submission_id=sub.id, position=pos, ballot_active=True))
    db.commit()

    results = tally(cycle, db)
    # film1: film1: 1+2+2 = 5 pts pts, two #1s -> wins
    assert results[0]["submission"].title == "Film 1"
    assert results[0]["points"] == 5
    # film0: 2+0+1 = 3 pts
    assert results[1]["submission"].title == "Film 0"
    # film2: 0+1+0 = 1 pt -> loser
    assert results[2]["submission"].title == "Film 2"


def test_inactive_ballots_ignored(db):
    cycle, users, subs = _mk(db)
    db.add(Ranking(cycle_id=cycle.id, user_id=users[0].id, submission_id=subs[0].id, position=1, ballot_active=False))
    db.commit()
    results = tally(cycle, db)
    assert all(r["points"] == 0 for r in results)


def test_close_cycle_crowns_winner_and_loser(db):
    cycle, users, subs = _mk(db)
    for pos, sub in enumerate([subs[2], subs[1], subs[0]], start=1):
        db.add(Ranking(cycle_id=cycle.id, user_id=users[0].id, submission_id=sub.id, position=pos, ballot_active=True))
    db.commit()

    winner, losers = close_cycle(cycle, db)
    assert cycle.status == CycleStatus.closed
    assert winner is subs[2]
    # 3-member team: everyone stays in
    assert losers == []
    assert cycle.loser_submission_id is None


def test_five_member_team_evicts_one(db):
    cycle, users, subs = _mk(db, n_users=5)
    assert eviction_count(cycle.team_id, db) == 1

    # worst ballot for u4's film; u0 ranks their own best
    order = [subs[0], subs[1], subs[2], subs[3], subs[4]]
    for pos, sub in enumerate(order, start=1):
        db.add(Ranking(cycle_id=cycle.id, user_id=users[0].id, submission_id=sub.id, position=pos, ballot_active=True))
    db.commit()

    winner, losers = close_cycle(cycle, db)
    assert winner is subs[0]
    assert losers == [subs[4]]
    assert cycle.loser_submission_id == subs[4].id


def test_six_member_team_evicts_two(db):
    cycle, users, subs = _mk(db, n_users=6)
    assert eviction_count(cycle.team_id, db) == 2

    order = [subs[0], subs[1], subs[2], subs[3], subs[5], subs[4]]
    for pos, sub in enumerate(order, start=1):
        db.add(Ranking(cycle_id=cycle.id, user_id=users[0].id, submission_id=sub.id, position=pos, ballot_active=True))
    db.commit()

    winner, losers = close_cycle(cycle, db)
    assert winner is subs[0]
    # two bottom films sit out next cycle, worst first
    assert losers == [subs[4], subs[5]]


def test_eviction_count_by_team_size(db):
    for size, expected in [(1, 0), (3, 0), (4, 0), (5, 1), (6, 2)]:
        cycle, users, subs = _mk(db, n_users=size, tag=f"s{size}")
        assert eviction_count(cycle.team_id, db) == expected
