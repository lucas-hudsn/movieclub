from app.models import Cycle, CycleStatus, Ranking, Submission, User
from app.services.scoring import close_cycle, tally


def _mk(db):
    cycle = Cycle(period="2026-01")
    users = [User(email=f"u{i}@x.io", name=f"u{i}", password_hash="h") for i in range(3)]
    db.add_all([cycle, *users])
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

    winner, loser = close_cycle(cycle, db)
    assert cycle.status == CycleStatus.closed
    assert winner is subs[2]
    assert loser is subs[0]
