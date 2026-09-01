from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Cycle, CycleStatus, Ranking, Submission, User


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


def eviction_count(team_id: int, db: Session) -> int:
    """
    How many members sit out the next cycle: everyone stays in for teams of
    4 or fewer; 5-member teams evict 1, 6-member teams evict 2.
    """
    members = db.scalar(select(func.count()).select_from(User).where(User.team_id == team_id))
    return max(0, min(members - 4, 2))


def close_cycle(cycle: Cycle, db: Session) -> tuple[Submission | None, list[Submission]]:
    """
    Crown winner (most points) and the last-place submission(s). Sets
    status=closed and records the winner/loser. How many bottom submissions
    count as losers depends on team size (see eviction_count).
    Tie-break: fewest firsts, then latest submission wins the dishonour.
    """
    results = tally(cycle, db)
    if not results:
        cycle.status = CycleStatus.closed
        return None, []

    winner = results[0]["submission"]
    ordered = sorted(
        results,
        key=lambda r: (r["points"], r["firsts"], -r["submission"].created_at.timestamp()),
    )
    n_losers = min(eviction_count(cycle.team_id, db), len(ordered) - 1)
    losers = [row["submission"] for row in ordered[:n_losers]]

    cycle.status = CycleStatus.closed
    cycle.winner_submission_id = winner.id
    cycle.loser_submission_id = losers[0].id if losers else None
    db.execute(
        update(User)
        .where(User.id == winner.user_id)
        .values(wins=User.wins + 1)
    )
    return winner, losers
