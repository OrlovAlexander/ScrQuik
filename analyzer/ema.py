# -*- coding: utf-8 -*-
"""EMA matching maLib F_EMA: (prev*(period-1) + 2*val)/(period+1)."""

from __future__ import annotations


class Ema:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.prev: float | None = None

    def reset(self) -> None:
        self.prev = None

    def update(self, val: float) -> float:
        if self.prev is None:
            self.prev = val
            return val
        self.prev = (self.prev * (self.period - 1) + 2.0 * val) / (self.period + 1)
        return self.prev
