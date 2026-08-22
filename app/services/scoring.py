from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cycle, CycleStatus, Ranking, Submission


def tally(cycle: Cycle, db: Session) -> list[dict]:
    """
    Borda count: each active ballot awards (N - position) points to the movie
    at that position. Returns submissions ordered best-first:
    [{submission, points, firsts}].
    """
    subs = db.scalars(
        select(Submission).where(Submission.cycle_id == cycle.id).order_by(Submission.created_at)
    ).all()
    n = len(subs)
    if n == 0:
        return []

    rankings = db.scalars(select(Ranking).where(Ranking.cycle_id == cycle.id)).all()
    by_user: dict[int, dict[int, int]] = {}
    for r in rankings:
        if r.ballot_active:
            by_user.setdefault(r.user_id, {})[r.submission_id] = r.position

    points = {s.id: 0 for s in subs}
    firsts = {s.id: 0 for s in subs}
    for positions in by_user.values():
        for sub_id, pos in positions.items():
            if sub_id in points and 1 <= pos <= n:
                points[sub_id] += n - pos
                if pos == 1:
                    firsts[sub_id] += 1

    results = [
        {"submission": s, "points": points[s.id], "firsts": firsts[s.id]}
        for s in subs
    ]
    # Best first; ties broken by most #1 ranks, then earliest submission.
    results.sort(key=lambda r: (-r["points"], -r["firsts"], r["submission"].created_at))
    return results


def close_cycle(cycle: Cycle, db: Session) -> tuple[Submission | None, Submission | None]:
    """
    Crown winner (most points) and loser (fewest points). Sets status=closed,
    records the winner, and returns (winner, loser).
    Tie-break for last place: fewest firsts, then latest submission wins the dishonour.
    """
    results = tally(cycle, db)
    if not results:
        cycle.status = CycleStatus.closed
        return None, None

    winner = results[0]["submission"]
    loser = min(
        results,
        key=lambda r: (r["points"], r["firsts"], -r["submission"].created_at.timestamp()),
    )["submission"]

    cycle.status = CycleStatus.closed
    cycle.winner_submission_id = winner.id
    if loser is not winner:
        cycle.loser_submission_id = loser.id
    else:
        cycle.loser_submission_id = None
    return winner, loser
