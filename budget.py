"""
budget.py — the attendance maths, and nothing else.

This is the single source of truth for "how many can I skip?". The FastAPI
app imports `compute_budget` from here; the frontend never re-implements the
maths, so there is exactly one place to get right.

WHY INTEGER ARITHMETIC?
The spec is written with floats (p/0.8, 0.2, etc.), but 0.8 and 0.2 are not
exactly representable in binary. For example `floor(4 / 0.8)` evaluates to 4
in Python (not 5!), because 4/0.8 comes out as 4.999999999999999. That single
rounding error would wrongly tell a student on exactly 80% that they are
*below* the line — the exact "dangerous advice" we must avoid.

So each float formula is rewritten as an algebraically identical integer form:

  current % >= 80%      <=>  p/t >= 0.8        <=>  5*p >= 4*t
  skips allowed         =    floor(p / 0.8) - t =    (5*p) // 4  - t
  attend-in-a-row       =    ceil((0.8*t - p)/0.2) =  4*t - 5*p

(The last one is exact because (0.8*t - p)/0.2 == 4*t - 5*p, an integer, so
the ceil is a no-op.) All three are exact for integer p and t.
"""


def compute_budget(present, total):
    """Given periods present/total for ONE row, return its verdict.

    Returns a dict with the current percentage, a status/colour, the numeric
    result, and a human-readable verdict string.
    """
    p = int(present)
    t = int(total)

    # Guard against garbage input (empty rows, OCR misreads).
    if t <= 0 or p < 0 or p > t:
        return {
            "present": p,
            "total": t,
            "percentage": 0.0,
            "status": "unknown",
            "color": "grey",
            "skips_allowed": None,
            "recover_needed": None,
            "verdict": "Check these numbers",
        }

    percentage = round(p / t * 100, 1)

    if 5 * p >= 4 * t:
        # SAFE: at or above 80%.
        skips = (5 * p) // 4 - t
        if skips <= 0:
            # Exactly on the line — one skip would drop below 80%.
            return _row(p, t, percentage, "online", "amber",
                        skips_allowed=0, verdict="Don't skip any")
        if skips == 1:
            return _row(p, t, percentage, "tight", "amber",
                        skips_allowed=1, verdict="You can skip 1 more")
        return _row(p, t, percentage, "safe", "green",
                    skips_allowed=skips, verdict=f"You can skip {skips} more")

    # BELOW 80%: work out how many consecutive attendances claw it back.
    recover = 4 * t - 5 * p  # always >= 1 here, since 5*p < 4*t
    unit = "class" if recover == 1 else "classes"
    return _row(p, t, percentage, "below", "red",
                recover_needed=recover,
                verdict=f"Attend {recover} {unit} in a row to recover")


def _row(p, t, percentage, status, color, *, skips_allowed=None,
         recover_needed=None, verdict=""):
    """Small helper so every branch returns the same shape."""
    return {
        "present": p,
        "total": t,
        "percentage": percentage,
        "status": status,
        "color": color,
        "skips_allowed": skips_allowed,
        "recover_needed": recover_needed,
        "verdict": verdict,
    }


# Ranking used to sort results worst-first. Lower rank = shown higher up.
_STATUS_RANK = {"below": 0, "online": 1, "tight": 2, "safe": 3, "unknown": 4}


def sort_worst_first(results):
    """Sort a list of computed rows so problem subjects float to the top.

    Order: below-80% first (lowest % = worst), then on-the-line, then tight
    (1 skip), then safe (fewest skips first). This is what makes the app
    useful — the portal buries these; we surface them.
    """
    def key(r):
        rank = _STATUS_RANK.get(r["status"], 5)
        # Tie-breakers within a rank: lowest % first, then fewest skips.
        return (rank, r["percentage"], r["skips_allowed"] if r["skips_allowed"] is not None else 0)

    return sorted(results, key=key)


if __name__ == "__main__":
    # Self-test against the spec's worked examples. Run: python budget.py
    # NOTE: the spec's annotation for (4, 8) says "attend 4 in a row", but that
    # is a typo — the spec's own formula gives 12, and (4+12)/(8+12) = 80%.
    # We assert the mathematically correct 12.
    cases = [
        # present, total, expected status, expected number
        (5, 5, "tight", 1),      # 100% -> can skip 1
        (22, 26, "tight", 1),    # 84.6% -> can skip 1
        (6, 6, "tight", 1),      # 100% -> can skip 1
        (4, 8, "below", 12),     # 50%  -> attend 12 in a row
        (4, 5, "online", 0),     # exactly 80% -> don't skip any
        (80, 100, "online", 0),  # exactly 80% -> don't skip any
        (90, 100, "safe", 12),   # 90% -> can skip 12  (floor(90/0.8)=112, -100)
    ]

    print(f"{'p':>4} {'t':>4} {'pct':>7}  {'status':<8} {'num':>4}  verdict")
    print("-" * 60)
    ok = True
    for p, t, exp_status, exp_num in cases:
        r = compute_budget(p, t)
        num = r["skips_allowed"] if r["skips_allowed"] is not None else r["recover_needed"]
        passed = (r["status"] == exp_status and num == exp_num)
        ok = ok and passed
        flag = "OK " if passed else "FAIL"
        print(f"{p:>4} {t:>4} {r['percentage']:>6.1f}%  {r['status']:<8} {str(num):>4}  {r['verdict']}   [{flag}]")

    print("-" * 60)
    print("ALL PASSED" if ok else "SOME FAILED")
    raise SystemExit(0 if ok else 1)
