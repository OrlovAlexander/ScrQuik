# -*- coding: utf-8 -*-
"""Adjacent-TF pairing. Larger TF looks down at the next smaller TF only."""

from __future__ import annotations

from datetime import datetime, timedelta

# (larger, smaller) — snapshot walks H4→M30, M30→M10, M10→M1. M1 has no child.
NEIGHBOR_PAIRS = (("H4", "M30"), ("M30", "M10"), ("M10", "M1"))


def neighbor_tfs(tf: str) -> tuple[str, ...]:
    return tuple(child for parent, child in NEIGHBOR_PAIRS if parent == tf)


def last_closed_indices(
    event_times: list[datetime],
    src_times: list[datetime],
    period_minutes: int | None = None,
) -> list[int | None]:
    """Index of the last *closed* src bar at each event time.

    A src bar j is closed once src[j+1] has started (src[j+1].dt <= event).
    If period_minutes is set and a later src bar exists, bar j is also closed
    after its period elapses — so a session gap does not keep Friday open
    until Monday. The last (possibly forming) src bar is never returned.
    """
    n_src = len(src_times)
    closed: int | None = None
    j = 0
    delta = timedelta(minutes=period_minutes) if period_minutes else None
    out: list[int | None] = []
    for t in event_times:
        while j + 1 < n_src and src_times[j + 1] <= t:
            closed = j
            j += 1
        if delta is not None and j < n_src - 1 and src_times[j] <= t:
            if src_times[j] + delta <= t:
                closed = j
        out.append(closed)
    return out
